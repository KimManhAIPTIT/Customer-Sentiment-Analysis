"""Nạp dữ liệu mẫu vào PostgreSQL; có thể phân tích trước tối đa N đánh giá."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Product, Review, get_engine, init_db

DATA_FILE = Path(__file__).parent / "data" / "sample_reviews.csv"


def seed(session: Session, path: Path = DATA_FILE) -> int:
    added = 0
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name = row["product_name"].strip()
            content = row["review_text"].strip()
            product = session.scalar(select(Product).where(Product.name == name))
            if product is None:
                product = Product(name=name)
                session.add(product)
                session.flush()
            duplicate = session.scalar(
                select(Review.id).where(Review.product_id == product.id, Review.review_text == content)
            )
            if duplicate is None:
                session.add(
                    Review(
                        product_id=product.id,
                        review_text=content,
                        rating=int(row["rating"]),
                        source=row["source"],
                        status="pending",
                    )
                )
                added += 1
    session.commit()
    return added


def analyze_pending(session: Session, limit: int) -> tuple[int, int]:
    # Lazy import chỉ dùng khi gọi phân tích AI ở Giai đoạn 2
    from ai_service import AIServiceError, analyze_review

    rows = session.scalars(
        select(Review).where(Review.status == "pending").order_by(Review.id).limit(limit)
    ).all()
    success = failed = 0
    for row in rows:
        try:
            result = analyze_review(row.review_text)
            row.sentiment, row.aspects, row.reason = result.sentiment, result.aspects, result.reason
            row.status, row.analyzed_at = "analyzed", datetime.now(timezone.utc)
            success += 1
        except AIServiceError:
            row.status = "failed"
            failed += 1
        session.commit()
    return success, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nạp đánh giá mẫu vào database")
    parser.add_argument(
        "--analyze",
        type=int,
        default=0,
        metavar="N",
        help="Gọi AI để phân tích trước tối đa N đánh giá chưa phân tích",
    )
    args = parser.parse_args()
    if args.analyze < 0:
        parser.error("--analyze phải >= 0")
    init_db()
    with Session(get_engine()) as db:
        print(f"Đã thêm {seed(db)} đánh giá mẫu.")
        if args.analyze:
            ok, error = analyze_pending(db, args.analyze)
            print(f"AI: thành công {ok}; thất bại {error}.")