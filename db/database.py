from time import sleep

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_database() -> None:
    attempts = max(1, settings.db_connect_retries)
    delay = max(0.0, settings.db_connect_retry_delay)
    last_error: OperationalError | None = None

    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleep(delay)

    if last_error is not None:
        raise last_error


def ensure_runtime_schema() -> None:
    from Service import models  # noqa: F401

    required_book_columns = {
        "pubdate": "ALTER TABLE books ADD COLUMN pubdate VARCHAR(20) NULL",
        "gist": "ALTER TABLE books ADD COLUMN gist TEXT NULL",
        "price": "ALTER TABLE books ADD COLUMN price VARCHAR(50) NULL",
        "page": "ALTER TABLE books ADD COLUMN page VARCHAR(50) NULL",
    }
    required_inventory_log_columns = {
        "borrower_name": "ALTER TABLE inventory_logs ADD COLUMN borrower_name VARCHAR(100) NULL",
        "borrower_class": "ALTER TABLE inventory_logs ADD COLUMN borrower_class VARCHAR(100) NULL",
        "related_log_id": "ALTER TABLE inventory_logs ADD COLUMN related_log_id INT NULL",
    }

    wait_for_database()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        inspector = inspect(conn)

        book_existing = {col["name"] for col in inspector.get_columns("books")}
        for col_name, alter_sql in required_book_columns.items():
            if col_name not in book_existing:
                conn.execute(text(alter_sql))

        logs_existing = {col["name"] for col in inspector.get_columns("inventory_logs")}
        for col_name, alter_sql in required_inventory_log_columns.items():
            if col_name not in logs_existing:
                conn.execute(text(alter_sql))
