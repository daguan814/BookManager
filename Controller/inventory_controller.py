from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import get_db
import requests

from Service.book_lookup import normalize_isbn, query_shumaidata_by_isbn
from Service.inventory_service import (
    ensure_stock_for_outbound,
    get_book_and_inventory_by_isbn,
    get_or_create_book_by_isbn,
    to_book_info,
)
from Service.models import Book, Inventory, InventoryLog
from Service.schemas import (
    BookInfo,
    ConfirmRequest,
    ConfirmResponse,
    InventoryItem,
    IsbnQueryResponse,
    LogItem,
    ScanRequest,
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.post("/scan", response_model=BookInfo, summary="图书ISBN查询")
def scan_inventory(req: ScanRequest, db: Session = Depends(get_db)):
    try:
        isbn = normalize_isbn(req.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        book, inventory = get_or_create_book_by_isbn(db, isbn)
        db.commit()
        db.refresh(book)
        db.refresh(inventory)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"扫码失败: {exc}") from exc

    return to_book_info(book, inventory)


@router.post("/isbn-query", response_model=IsbnQueryResponse, summary="图书ISBN查询")
def isbn_query(req: ScanRequest):
    try:
        result = query_shumaidata_by_isbn(req.isbn)
        return IsbnQueryResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"第三方图书接口请求失败: {exc}") from exc


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_inventory(req: ConfirmRequest, db: Session = Depends(get_db)):
    try:
        isbn = normalize_isbn(req.isbn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        if req.action == "out":
            book, inventory = get_book_and_inventory_by_isbn(db, isbn)
            ensure_stock_for_outbound(inventory.quantity, req.quantity)
            inventory.quantity -= req.quantity
        else:
            book, inventory = get_or_create_book_by_isbn(
                db,
                isbn,
                title=req.title,
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
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"操作失败: {exc}") from exc

    return ConfirmResponse(message="库存更新成功", book=to_book_info(book, inventory))


@router.get("", response_model=list[InventoryItem])
def list_inventory(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Inventory, Book).join(Book, Book.id == Inventory.book_id).order_by(Inventory.updated_at.desc())
    ).all()
    return [
        InventoryItem(
            book_id=book.id,
            isbn=book.isbn,
            title=book.title,
            quantity=inventory.quantity,
            updated_at=inventory.updated_at,
        )
        for inventory, book in rows
    ]


@router.get("/logs", response_model=list[LogItem])
def list_inventory_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(InventoryLog, Book)
        .join(Book, Book.id == InventoryLog.book_id)
        .order_by(InventoryLog.id.desc())
        .limit(limit)
    ).all()
    return [
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
        )
        for log, book in rows
    ]
