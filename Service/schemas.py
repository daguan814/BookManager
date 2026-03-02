from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    isbn: str = Field(min_length=10, max_length=20)


class BookInfo(BaseModel):
    isbn: str
    title: str
    author: str | None = None
    publisher: str | None = None
    pubdate: str | None = None
    gist: str | None = None
    price: str | None = None
    page: str | None = None
    publish_year: str | None = None
    cover_url: str | None = None
    current_quantity: int

    class Config:
        from_attributes = True


class IsbnQueryResponse(BaseModel):
    success: bool
    source: str
    code: int | None = None
    msg: str | None = None
    isbn: str
    title: str
    author: str | None = None
    publisher: str | None = None
    pubdate: str | None = None
    gist: str | None = None
    price: str | None = None
    page: str | None = None
    publish_year: str | None = None
    cover_url: str | None = None
    raw: dict | None = None


class ConfirmRequest(BaseModel):
    isbn: str = Field(min_length=10, max_length=20)
    action: Literal["in", "out"]
    quantity: int = Field(ge=1, le=10000)
    title: str | None = Field(default=None, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    pubdate: str | None = Field(default=None, max_length=20)
    gist: str | None = Field(default=None, max_length=5000)
    price: str | None = Field(default=None, max_length=50)
    page: str | None = Field(default=None, max_length=50)
    operator_name: str | None = Field(default="admin", max_length=100)
    remark: str | None = Field(default=None, max_length=500)


class ConfirmResponse(BaseModel):
    message: str
    book: BookInfo


class BookListItem(BaseModel):
    id: int
    isbn: str
    title: str
    author: str | None
    publisher: str | None
    pubdate: str | None
    gist: str | None
    price: str | None
    page: str | None
    publish_year: str | None
    cover_url: str | None = None
    quantity: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BookListResponse(BaseModel):
    total: int
    items: list[BookListItem]


class BookUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    pubdate: str | None = Field(default=None, max_length=20)
    gist: str | None = Field(default=None, max_length=5000)
    price: str | None = Field(default=None, max_length=50)
    page: str | None = Field(default=None, max_length=50)
    publish_year: str | None = Field(default=None, max_length=20)
    cover_url: str | None = Field(default=None, max_length=500)


class InventoryItem(BaseModel):
    book_id: int
    isbn: str
    title: str
    quantity: int
    updated_at: datetime | None = None


class LogItem(BaseModel):
    id: int
    book_id: int
    isbn: str
    title: str
    action: str
    quantity: int
    operator_name: str | None = None
    remark: str | None = None
    created_at: datetime
