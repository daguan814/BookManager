from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select

from Service.models import Book, Inventory, InventoryLog
from Service.schemas import BookListItem, BookListResponse, BookUpdateRequest
from db.database import SessionLocal

book_bp = Blueprint("books", __name__, url_prefix="/api/books")


def _error(detail: str, status_code: int):
    return jsonify({"detail": detail}), status_code


def _parse_positive_int(raw: str | None, default: int, min_value: int, max_value: int | None = None) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("分页参数必须为整数") from exc
    if value < min_value:
        raise ValueError(f"分页参数必须大于等于 {min_value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"分页参数必须小于等于 {max_value}")
    return value


@book_bp.get("")
def list_books():
    keyword = request.args.get("keyword")
    try:
        page = _parse_positive_int(request.args.get("page"), 1, 1)
        page_size = _parse_positive_int(request.args.get("page_size"), 20, 1, 100)
    except ValueError as exc:
        return _error(str(exc), 400)

    with SessionLocal() as db:
        stmt = select(Book, Inventory).join(Inventory, Inventory.book_id == Book.id, isouter=True)
        count_stmt = select(func.count(Book.id))

        if keyword:
            search = f"%{keyword}%"
            condition = or_(Book.title.like(search), Book.isbn.like(search), Book.author.like(search))
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = db.scalar(count_stmt) or 0
        rows = db.execute(stmt.order_by(Book.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()

        items = [
            BookListItem(
                id=book.id,
                isbn=book.isbn,
                title=book.title,
                author=book.author,
                publisher=book.publisher,
                pubdate=book.pubdate,
                gist=book.gist,
                price=book.price,
                page=book.page,
                publish_year=book.publish_year,
                cover_url=book.cover_url,
                quantity=inventory.quantity if inventory else 0,
                created_at=book.created_at,
                updated_at=inventory.updated_at if inventory else None,
            )
            for book, inventory in rows
        ]

    return jsonify(BookListResponse(total=total, items=items).model_dump(mode="json"))


@book_bp.put("/<int:book_id>")
def update_book(book_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        req = BookUpdateRequest.model_validate(payload)
    except ValidationError as exc:
        return _error(exc.errors()[0]["msg"], 400)

    with SessionLocal() as db:
        book = db.scalar(select(Book).where(Book.id == book_id))
        if book is None:
            return _error("图书不存在", 404)

        book.title = req.title
        book.author = req.author
        book.publisher = req.publisher
        book.pubdate = req.pubdate
        book.gist = req.gist
        book.price = req.price
        book.page = req.page
        book.publish_year = req.publish_year
        book.cover_url = req.cover_url
        db.commit()
        db.refresh(book)

        inventory = db.scalar(select(Inventory).where(Inventory.book_id == book_id))
        result = BookListItem(
            id=book.id,
            isbn=book.isbn,
            title=book.title,
            author=book.author,
            publisher=book.publisher,
            pubdate=book.pubdate,
            gist=book.gist,
            price=book.price,
            page=book.page,
            publish_year=book.publish_year,
            cover_url=book.cover_url,
            quantity=inventory.quantity if inventory else 0,
            created_at=book.created_at,
            updated_at=inventory.updated_at if inventory else None,
        )

    return jsonify(result.model_dump(mode="json"))


@book_bp.delete("/<int:book_id>")
def delete_book(book_id: int):
    with SessionLocal() as db:
        book = db.scalar(select(Book).where(Book.id == book_id))
        if book is None:
            return _error("图书不存在", 404)
        try:
            db.execute(delete(InventoryLog).where(InventoryLog.book_id == book_id))
            db.execute(delete(Inventory).where(Inventory.book_id == book_id))
            db.delete(book)
            db.commit()
        except Exception as exc:
            db.rollback()
            return _error(f"删除失败: {exc}", 500)

    return jsonify({"message": "删除成功"})
