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


@lru_cache(maxsize=1)
def get_engine():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url or "YOUR-NEON-HOST" in url:
        raise RuntimeError("Chưa cấu hình DATABASE_URL trong .env")
    return create_engine(url, pool_pre_ping=True)


def init_db() -> None:
    # Phù hợp bản demo khởi tạo lần đầu; schema thay đổi về sau cần migration.
    Base.metadata.create_all(get_engine())


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
