import requests
from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import aliased

from Service.book_lookup import normalize_isbn, query_shumaidata_by_isbn
from Service.inventory_service import (
    ServiceError,
    ensure_stock_for_outbound,
    get_book_and_inventory_by_isbn,
    get_or_create_book_by_isbn,
    to_book_info,
)
from Service.models import Book, Inventory, InventoryLog
from Service.schemas import (
    ConfirmRequest,
    ConfirmResponse,
    InventoryItem,
    IsbnQueryResponse,
    LogItem,
    ReturnRequest,
    ScanRequest,
)
from db.database import SessionLocal

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")


def _error(detail: str, status_code: int):
    return jsonify({"detail": detail}), status_code


def _validate_json(schema_cls):
    payload = request.get_json(silent=True) or {}
    return schema_cls.model_validate(payload)


@inventory_bp.post("/scan")
def scan_inventory():
    try:
        req = _validate_json(ScanRequest)
        isbn = normalize_isbn(req.isbn)
    except ValidationError as exc:
        return _error(exc.errors()[0]["msg"], 400)
    except ValueError as exc:
        return _error(str(exc), 400)

    with SessionLocal() as db:
        try:
            book, inventory = get_or_create_book_by_isbn(db, isbn)
            db.commit()
            db.refresh(book)
            db.refresh(inventory)
        except ServiceError as exc:
            db.rollback()
            return _error(exc.detail, exc.status_code)
        except Exception as exc:
            db.rollback()
            return _error(f"扫码失败: {exc}", 500)

    return jsonify(to_book_info(book, inventory).model_dump(mode="json"))


@inventory_bp.post("/isbn-query")
def isbn_query():
    try:
        req = _validate_json(ScanRequest)
        result = query_shumaidata_by_isbn(req.isbn)
        return jsonify(IsbnQueryResponse(**result).model_dump(mode="json"))
    except ValidationError as exc:
        return _error(exc.errors()[0]["msg"], 400)
    except ValueError as exc:
        return _error(str(exc), 400)
    except requests.RequestException as exc:
        return _error(f"第三方图书接口请求失败: {exc}", 502)


@inventory_bp.post("/confirm")
def confirm_inventory():
    try:
        req = _validate_json(ConfirmRequest)
        isbn = normalize_isbn(req.isbn)
    except ValidationError as exc:
        return _error(exc.errors()[0]["msg"], 400)
    except ValueError as exc:
        return _error(str(exc), 400)

    title = (req.title or "").strip()
    borrower_name = (req.borrower_name or "").strip()
    borrower_class = (req.borrower_class or "").strip()
    if req.action == "in" and not title:
        return _error("入库时书名必填", 400)
    if req.action == "out":
        if not borrower_name:
            return _error("借阅时借阅人必填", 400)
        if not borrower_class:
            return _error("借阅时班级必填", 400)

    with SessionLocal() as db:
        try:
            if req.action == "out":
                book, inventory = get_book_and_inventory_by_isbn(db, isbn)
                ensure_stock_for_outbound(inventory.quantity, req.quantity)
                inventory.quantity -= req.quantity
            else:
                book, inventory = get_or_create_book_by_isbn(
                    db,
                    isbn,
                    title=title,
                    author=req.author,
                    publisher=req.publisher,
                    pubdate=req.pubdate,
                    gist=req.gist,
                    price=req.price,
                    page=req.page,
                )
                inventory.quantity += req.quantity

            log = InventoryLog(
                book_id=book.id,
                action=req.action,
                quantity=req.quantity,
                related_log_id=None,
                operator_name=req.operator_name,
                borrower_name=borrower_name or None,
                borrower_class=borrower_class or None,
                remark=req.remark,
            )
            db.add(log)
            db.commit()
            db.refresh(book)
            db.refresh(inventory)
        except ServiceError as exc:
            db.rollback()
            return _error(exc.detail, exc.status_code)
        except Exception as exc:
            db.rollback()
            return _error(f"操作失败: {exc}", 500)

    result = ConfirmResponse(message="操作成功", book=to_book_info(book, inventory))
    return jsonify(result.model_dump(mode="json"))


@inventory_bp.get("")
def list_inventory():
    with SessionLocal() as db:
        rows = db.execute(
            select(Inventory, Book).join(Book, Book.id == Inventory.book_id).order_by(Inventory.updated_at.desc())
        ).all()
        data = [
            InventoryItem(
                book_id=book.id,
                isbn=book.isbn,
                title=book.title,
                quantity=inventory.quantity,
                updated_at=inventory.updated_at,
            ).model_dump(mode="json")
            for inventory, book in rows
        ]
    return jsonify(data)


@inventory_bp.get("/logs")
def list_inventory_logs():
    raw_limit = request.args.get("limit", "100")
    try:
        limit = int(raw_limit)
    except ValueError:
        return _error("limit 必须是整数", 400)
    if limit < 1 or limit > 500:
        return _error("limit 必须在 1 到 500 之间", 400)
    view = (request.args.get("view", "all") or "all").strip().lower()
    if view not in {"all", "borrowed", "unreturned"}:
        return _error("view 仅支持 all / borrowed / unreturned", 400)

    with SessionLocal() as db:
        if view == "all":
            rows = db.execute(
                select(InventoryLog, Book)
                .join(Book, Book.id == InventoryLog.book_id)
                .order_by(InventoryLog.id.desc())
                .limit(limit)
            ).all()
        elif view == "borrowed":
            rows = db.execute(
                select(InventoryLog, Book)
                .join(Book, Book.id == InventoryLog.book_id)
                .where(InventoryLog.action == "out")
                .order_by(InventoryLog.id.desc())
                .limit(limit)
            ).all()
        else:
            returned_log = aliased(InventoryLog)
            rows = db.execute(
                select(InventoryLog, Book)
                .join(Book, Book.id == InventoryLog.book_id)
                .where(InventoryLog.action == "out")
                .where(
                    ~select(returned_log.id)
                    .where(returned_log.action == "return")
                    .where(returned_log.related_log_id == InventoryLog.id)
                    .exists()
                )
                .order_by(InventoryLog.id.desc())
                .limit(limit)
            ).all()

        borrow_log_ids = [log.id for log, _ in rows if log.action == "out"]
        returned_ids: set[int] = set()
        if borrow_log_ids:
            returned_ids = {
                related_id
                for (related_id,) in db.execute(
                    select(InventoryLog.related_log_id).where(
                        InventoryLog.action == "return",
                        InventoryLog.related_log_id.in_(borrow_log_ids),
                    )
                ).all()
                if related_id is not None
            }

        data = [
            LogItem(
                id=log.id,
                book_id=book.id,
                isbn=book.isbn,
                title=book.title,
                action=log.action,
                quantity=log.quantity,
                related_log_id=log.related_log_id,
                is_returned=(log.id in returned_ids) if log.action == "out" else None,
                can_return=(log.action == "out" and log.id not in returned_ids),
                operator_name=log.operator_name,
                borrower_name=log.borrower_name,
                borrower_class=log.borrower_class,
                remark=log.remark,
                created_at=log.created_at,
            ).model_dump(mode="json")
            for log, book in rows
        ]
    return jsonify(data)


@inventory_bp.post("/return")
def return_inventory():
    try:
        req = _validate_json(ReturnRequest)
    except ValidationError as exc:
        return _error(exc.errors()[0]["msg"], 400)

    with SessionLocal() as db:
        try:
            borrow_log = db.scalar(select(InventoryLog).where(InventoryLog.id == req.log_id))
            if borrow_log is None:
                return _error("借阅记录不存在", 404)
            if borrow_log.action != "out":
                return _error("只能对借阅记录执行还书", 400)

            returned = db.scalar(
                select(InventoryLog.id).where(
                    InventoryLog.action == "return",
                    InventoryLog.related_log_id == borrow_log.id,
                )
            )
            if returned is not None:
                return _error("该借阅记录已还书", 400)

            book = db.scalar(select(Book).where(Book.id == borrow_log.book_id))
            if book is None:
                return _error("图书不存在", 404)
            inventory = db.scalar(select(Inventory).where(Inventory.book_id == book.id))
            if inventory is None:
                return _error("图书库存记录不存在", 404)

            inventory.quantity += borrow_log.quantity
            return_log = InventoryLog(
                book_id=book.id,
                action="return",
                quantity=borrow_log.quantity,
                related_log_id=borrow_log.id,
                operator_name=req.operator_name,
                borrower_name=borrow_log.borrower_name,
                borrower_class=borrow_log.borrower_class,
                remark=(req.remark or "").strip() or f"归还借阅记录#{borrow_log.id}",
            )
            db.add(return_log)
            db.commit()
            db.refresh(book)
            db.refresh(inventory)
        except Exception as exc:
            db.rollback()
            return _error(f"还书失败: {exc}", 500)

    result = ConfirmResponse(message="还书成功", book=to_book_info(book, inventory))
    return jsonify(result.model_dump(mode="json"))
