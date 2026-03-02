from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.database import get_db
from Service.models import Book, Inventory
from Service.schemas import BookListItem, BookListResponse, BookUpdateRequest

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=BookListResponse)
def list_books(
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Book, Inventory).join(Inventory, Inventory.book_id == Book.id, isouter=True)
    count_stmt = select(func.count(Book.id))

    if keyword:
        search = f"%{keyword}%"
        condition = or_(Book.title.like(search), Book.isbn.like(search), Book.author.like(search))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Book.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

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
            updated_at=inventory.updated_at if inventory else None,
        )
        for book, inventory in rows
    ]
    return BookListResponse(total=total, items=items)


@router.put("/{book_id}", response_model=BookListItem)
def update_book(book_id: int, req: BookUpdateRequest, db: Session = Depends(get_db)):
    book = db.scalar(select(Book).where(Book.id == book_id))
    if book is None:
        raise HTTPException(status_code=404, detail="图书不存在")

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
    return BookListItem(
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
        updated_at=inventory.updated_at if inventory else None,
    )
