"""Kết nối và schema PostgreSQL cho ứng dụng demo."""

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

load_dotenv()


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="user")
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    aspects: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _database_url(name: str) -> str:
    # `neon env pull` ghi URL trong dấu nháy và dạng postgresql://; docker --env-file giữ nguyên dấu nháy.
    url = os.getenv(name, "").strip().strip("\"'")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache(maxsize=1)
def get_engine():
    # DATABASE_URL của Neon là kết nối pooled (-pooler), phù hợp cho truy vấn của app.
    url = _database_url("DATABASE_URL")
    if not url or "YOUR-NEON-HOST" in url or "ep-sample" in url:
        raise RuntimeError("Chưa cấu hình DATABASE_URL trong .env")
    return create_engine(url, pool_pre_ping=True)


def init_db() -> None:
    # Phù hợp bản demo khởi tạo lần đầu; schema thay đổi về sau cần migration.
    # Với Postgres, DDL chạy qua kết nối trực tiếp (DATABASE_URL_UNPOOLED) nếu có, theo khuyến nghị của Neon.
    engine = get_engine()
    direct_url = _database_url("DATABASE_URL_UNPOOLED")
    if engine.dialect.name != "postgresql" or not direct_url:
        Base.metadata.create_all(engine)
        return
    direct_engine = create_engine(direct_url, pool_pre_ping=True)
    try:
        Base.metadata.create_all(direct_engine)
    finally:
        direct_engine.dispose()


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
