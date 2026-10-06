"""Ứng dụng FastAPI: giao diện, API và luồng lưu kết quả."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from database import Product, Review, get_db, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Review Insights", lifespan=lifespan)


class ReviewInput(BaseModel):
    product_id: int = Field(gt=0)
    review_text: str = Field(min_length=3, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)


def review_dict(review: Review) -> dict:
    return {
        "id": review.id,
        "product_id": review.product_id,
        "review_text": review.review_text,
        "rating": review.rating,
        "source": review.source,
        "sentiment": review.sentiment,
        "aspects": review.aspects or [],
        "reason": review.reason,
        "status": review.status,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


@app.get("/")
def home():
    return {"status": "backend_ready"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database chưa sẵn sàng") from exc
    return {"status": "ok", "database": "ok"}


@app.get("/api/products")
def products(db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).order_by(Product.id)).all()
    return [{"id": row.id, "name": row.name} for row in rows]


@app.get("/api/products/{product_id}/reviews")
def reviews(product_id: int, db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    rows = db.scalars(
        select(Review)
        .where(Review.product_id == product_id)
        .order_by(Review.id.desc())
        .limit(100)
    ).all()
    return [review_dict(row) for row in rows]


@app.get("/api/products/{product_id}/summary")
def summary(product_id: int, db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    counts = {label: 0 for label in ("positive", "neutral", "negative", "mixed")}
    rows = db.execute(
        select(Review.sentiment, func.count(Review.id))
        .where(Review.product_id == product_id, Review.status == "analyzed")
        .group_by(Review.sentiment)
    ).all()
    for sentiment, count in rows:
        if sentiment in counts:
            counts[sentiment] = count
    return {"product_id": product_id, "total_analyzed": sum(counts.values()), "sentiments": counts}


@app.post("/api/reviews/analyze", status_code=202)
def create_review(payload: ReviewInput, db: Session = Depends(get_db)):
    if not payload.review_text.strip():
        raise HTTPException(status_code=422, detail="Đánh giá không được để trống")
    if not db.get(Product, payload.product_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")

    review = Review(
        product_id=payload.product_id,
        review_text=payload.review_text.strip(),
        rating=payload.rating,
        source="user",
        status="pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review_dict(review)