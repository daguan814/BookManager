from sqlalchemy import select
from sqlalchemy.orm import Session

from Service.book_lookup import lookup_book_by_isbn
from Service.models import Book, Inventory
from Service.schemas import BookInfo


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def get_or_create_book_by_isbn(
    db: Session,
    isbn: str,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    pubdate: str | None = None,
    gist: str | None = None,
    price: str | None = None,
    page: str | None = None,
) -> tuple[Book, Inventory]:
    book = db.scalar(select(Book).where(Book.isbn == isbn))
    if book is None:
        external = lookup_book_by_isbn(isbn)
        book = Book(
            isbn=isbn,
            title=(title or "").strip() or external["title"],
            author=(author or "").strip() or external.get("author"),
            publisher=(publisher or "").strip() or external.get("publisher"),
            pubdate=(pubdate or "").strip() or external.get("pubdate"),
            gist=(gist or "").strip() or external.get("gist"),
            price=(price or "").strip() or external.get("price"),
            page=(page or "").strip() or external.get("page"),
            publish_year=external.get("publish_year"),
            cover_url=external.get("cover_url"),
        )
        db.add(book)
        db.flush()

        inventory = Inventory(book_id=book.id, quantity=0)
        db.add(inventory)
        db.flush()
        return book, inventory

    manual_title = (title or "").strip()
    manual_author = (author or "").strip()
    manual_publisher = (publisher or "").strip()
    manual_pubdate = (pubdate or "").strip()
    manual_gist = (gist or "").strip()
    manual_price = (price or "").strip()
    manual_page = (page or "").strip()
    if manual_title:
        book.title = manual_title
    if manual_author:
        book.author = manual_author
    if manual_publisher:
        book.publisher = manual_publisher
    if manual_pubdate:
        book.pubdate = manual_pubdate
        book.publish_year = manual_pubdate
    if manual_gist:
        book.gist = manual_gist
    if manual_price:
        book.price = manual_price
    if manual_page:
        book.page = manual_page

    inventory = db.scalar(select(Inventory).where(Inventory.book_id == book.id))
    if inventory is None:
        inventory = Inventory(book_id=book.id, quantity=0)
        db.add(inventory)
        db.flush()
    return book, inventory


def get_book_and_inventory_by_isbn(db: Session, isbn: str) -> tuple[Book, Inventory]:
    book = db.scalar(select(Book).where(Book.isbn == isbn))
    if book is None:
        raise ServiceError(404, "图书不存在，请先入库后再借阅")

    inventory = db.scalar(select(Inventory).where(Inventory.book_id == book.id))
    if inventory is None:
        raise ServiceError(404, "图书库存记录不存在，请先入库")
    return book, inventory


def to_book_info(book: Book, inventory: Inventory) -> BookInfo:
    return BookInfo(
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
        current_quantity=inventory.quantity,
    )


def ensure_stock_for_outbound(current_quantity: int, outbound_quantity: int) -> None:
    if current_quantity < outbound_quantity:
        raise ServiceError(
            400,
            f"库存不足，当前库存 {current_quantity}，借阅 {outbound_quantity}",
        )
