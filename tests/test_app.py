import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app as application
from ai_service import AIServiceError, ReviewAnalysis
from database import Product, Review, get_engine
from seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
    )
    monkeypatch.delenv("DEMO_ACCESS_TOKEN", raising=False)
    get_engine.cache_clear()

    with TestClient(application.app) as test_client:
        with Session(get_engine()) as db:
            db.add(Product(name="Sản phẩm thử"))
            db.commit()
        yield test_client

    get_engine().dispose()
    get_engine.cache_clear()


def test_page_and_health(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Review Insights" in page.text
    assert client.get("/health").json() == {
        "status": "ok",
        "database": "ok",
    }


def test_analysis_is_saved_and_summary_updates(client, monkeypatch):
    monkeypatch.setattr(
        application,
        "analyze_review",
        lambda _text: ReviewAnalysis(
            sentiment="mixed",
            aspects=["chất lượng", "giao hàng"],
            reason="Tốt nhưng giao chậm",
        ),
    )

    response = client.post(
        "/api/reviews/analyze",
        json={
            "product_id": 1,
            "review_text": "Chất lượng tốt nhưng giao hàng chậm",
            "rating": 3,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "analyzed"
    assert response.json()["sentiment"] == "mixed"

    reviews = client.get("/api/products/1/reviews").json()
    assert reviews[0]["aspects"] == ["chất lượng", "giao hàng"]
    assert client.get("/api/products/1/summary").json()["sentiments"]["mixed"] == 1


def test_invalid_input_does_not_call_ai(client, monkeypatch):
    def unexpected_call(_text):
        pytest.fail("Không được gọi AI khi input không hợp lệ")

    monkeypatch.setattr(application, "analyze_review", unexpected_call)

    assert client.post(
        "/api/reviews/analyze",
        json={"product_id": 1, "review_text": "  "},
    ).status_code == 422

    assert client.post(
        "/api/reviews/analyze",
        json={"product_id": 999, "review_text": "Sản phẩm tốt"},
    ).status_code == 404


def test_ai_failure_is_recorded(client, monkeypatch):
    def fail(_text):
        raise AIServiceError("Dịch vụ AI không sẵn sàng")

    monkeypatch.setattr(application, "analyze_review", fail)

    response = client.post(
        "/api/reviews/analyze",
        json={"product_id": 1, "review_text": "Giao hàng chậm"},
    )

    assert response.status_code == 502
    reviews = client.get("/api/products/1/reviews").json()
    assert reviews[0]["status"] == "failed"


def test_demo_access_token(client, monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "private-demo-value")

    response = client.post(
        "/api/reviews/analyze",
        json={"product_id": 1, "review_text": "Sản phẩm tốt"},
    )

    assert response.status_code == 403
    assert client.get("/api/products/1/reviews").json() == []

def test_create_product_and_reject_duplicates(client):
    response = client.post("/api/products", json={"name": "  Bàn phím cơ  "})
    assert response.status_code == 201
    product = response.json()
    assert product["name"] == "Bàn phím cơ"
    assert product in client.get("/api/products").json()
    assert client.get(f"/api/products/{product['id']}/reviews").json() == []
    assert client.post("/api/products", json={"name": "bàn phím cơ"}).status_code == 409
    assert client.post("/api/products", json={"name": "   "}).status_code == 422


def test_create_product_requires_demo_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "private-demo-value")
    payload = {"name": "Chuột không dây"}
    assert client.post("/api/products", json=payload).status_code == 403
    response = client.post(
        "/api/products", json=payload, headers={"X-Demo-Token": "private-demo-value"}
    )
    assert response.status_code == 201


def test_seed_is_idempotent(client):
    csv_path = Path(__file__).resolve().parents[1] / "data" / "sample_reviews.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    with Session(get_engine()) as db:
        first_added = seed(db)
        assert first_added == len(rows)
        assert seed(db) == 0
        assert db.scalar(select(func.count(Review.id))) == len(rows)

    # Có thêm "Sản phẩm thử" do fixture tạo trước khi chạy seed.
    expected_products = 1 + len({row["product_name"].strip() for row in rows})
    assert len(client.get("/api/products").json()) == expected_products