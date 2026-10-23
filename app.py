"""Ứng dụng FastAPI: giao diện, API và luồng lưu kết quả."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ai_service import AIServiceError, analyze_review
from database import Product, Review, get_db, init_db



@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Review Insights", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


class ReviewInput(BaseModel):
    product_id: int = Field(gt=0)
    review_text: str = Field(min_length=3, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)

class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


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

@app.post("/api/products", status_code=201)
def create_product(
    payload: ProductInput,
    x_demo_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    configured_token = os.getenv("DEMO_ACCESS_TOKEN", "").strip()
    if (
        configured_token
        and configured_token != "YOUR_PRIVATE_DEMO_TOKEN"
        and x_demo_token != configured_token
    ):
        raise HTTPException(status_code=403, detail="Mã truy cập demo không đúng")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tên sản phẩm không được để trống")
    if db.scalar(select(Product.id).where(func.lower(Product.name) == name.lower())):
        raise HTTPException(status_code=409, detail="Sản phẩm đã tồn tại")

    product = Product(name=name)
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Sản phẩm đã tồn tại") from exc
    db.refresh(product)
    return {"id": product.id, "name": product.name}


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


@app.post("/api/reviews/analyze", status_code=201)
def create_review(
    payload: ReviewInput,
    x_demo_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    configured_token = os.getenv("DEMO_ACCESS_TOKEN", "").strip()
    if (
        configured_token
        and configured_token != "YOUR_PRIVATE_DEMO_TOKEN"
        and x_demo_token != configured_token
    ):
        raise HTTPException(status_code=403, detail="Mã truy cập demo không đúng")

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

    try:
        result = analyze_review(review.review_text)
    except AIServiceError as exc:
        review.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    review.sentiment = result.sentiment
    review.aspects = result.aspects
    review.reason = result.reason
    review.status = "analyzed"
    review.analyzed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)
    return review_dict(review)