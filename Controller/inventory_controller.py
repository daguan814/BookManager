import requests
from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from sqlalchemy import select

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
    if req.action == "in" and not title:
        return _error("入库时书名必填", 400)

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
                operator_name=req.operator_name,
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

    result = ConfirmResponse(message="库存更新成功", book=to_book_info(book, inventory))
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

    with SessionLocal() as db:
        rows = db.execute(
            select(InventoryLog, Book)
            .join(Book, Book.id == InventoryLog.book_id)
            .order_by(InventoryLog.id.desc())
            .limit(limit)
        ).all()
        data = [
            LogItem(
                id=log.id,
                book_id=book.id,
                isbn=book.isbn,
                title=book.title,
                action=log.action,
                quantity=log.quantity,
                operator_name=log.operator_name,
                remark=log.remark,
                created_at=log.created_at,
            ).model_dump(mode="json")
            for log, book in rows
        ]
    return jsonify(data)
