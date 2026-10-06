import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import app
from database import Product, get_engine
from seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file}")
    get_engine.cache_clear()
    with TestClient(app) as test_client:
        # Tạo trước 1 sản phẩm mẫu theo đúng thiết kế của bộ test
        with Session(get_engine()) as db:
            db.add(Product(name="Sản phẩm thử"))
            db.commit()
        yield test_client
    get_engine().dispose()
    get_engine.cache_clear()


def test_root_and_health(client):
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json() == {"status": "backend_ready"}

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok", "database": "ok"}


def test_create_review_success_and_summary(client):
    payload = {
        "product_id": 1,
        "review_text": "Sản phẩm dùng rất tốt, hài lòng!",
        "rating": 5,
    }
    response = client.post("/api/reviews/analyze", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["review_text"] == payload["review_text"]

    # GET reviews có chứa review vừa tạo
    res_reviews = client.get("/api/products/1/reviews")
    assert res_reviews.status_code == 200
    review_ids = [r["id"] for r in res_reviews.json()]
    assert data["id"] in review_ids

    # summary total_analyzed vẫn là 0 vì chưa chạy AI
    res_summary = client.get("/api/products/1/summary")
    assert res_summary.status_code == 200
    assert res_summary.json()["total_analyzed"] == 0


def test_create_review_validation_errors(client):
    # Review chỉ có khoảng trắng -> 422
    res_whitespace = client.post(
        "/api/reviews/analyze",
        json={"product_id": 1, "review_text": "   ", "rating": 5},
    )
    assert res_whitespace.status_code == 422

    # Product không tồn tại -> 404
    res_not_found = client.post(
        "/api/reviews/analyze",
        json={"product_id": 999999, "review_text": "Đánh giá hợp lệ", "rating": 5},
    )
    assert res_not_found.status_code == 404


def test_seed_idempotency(client):
    with Session(get_engine()) as db:
        first_added = seed(db)
        assert first_added == 24

        second_added = seed(db)
        assert second_added == 0

    # 1 sản phẩm tạo từ fixture + 3 sản phẩm nạp từ CSV = 4 sản phẩm
    res_products = client.get("/api/products")
    assert res_products.status_code == 200
    assert len(res_products.json()) == 4