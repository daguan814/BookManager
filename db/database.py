from sqlalchemy import create_engine, inspect, text
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


def ensure_runtime_schema() -> None:
    required_book_columns = {
        "pubdate": "ALTER TABLE books ADD COLUMN pubdate VARCHAR(20) NULL",
        "gist": "ALTER TABLE books ADD COLUMN gist TEXT NULL",
        "price": "ALTER TABLE books ADD COLUMN price VARCHAR(50) NULL",
        "page": "ALTER TABLE books ADD COLUMN page VARCHAR(50) NULL",
    }

    with engine.begin() as conn:
        existing = {col["name"] for col in inspect(conn).get_columns("books")}
        for col_name, alter_sql in required_book_columns.items():
            if col_name not in existing:
                conn.execute(text(alter_sql))
