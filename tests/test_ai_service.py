"""Kiểm tra xử lý phản hồi Gemini mà không gọi API thật."""

import pytest

import ai_service
from ai_service import AIServiceError, ReviewAnalysis


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")

    def install(response_text=None, error=None):
        class FakeModels:
            def generate_content(self, **kwargs):
                assert kwargs["model"] == "test-model"
                assert "Đánh giá cần phân tích:" in kwargs["contents"]
                assert kwargs["config"].response_mime_type == "application/json"
                if error is not None:
                    raise error
                return type("Response", (), {"text": response_text})()

        class FakeClient:
            def __init__(self, **kwargs):
                assert kwargs["api_key"] == "test-key"
                self.models = FakeModels()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        monkeypatch.setattr(ai_service.genai, "Client", FakeClient)

    return install


def test_valid_response_returns_review_analysis(fake_gemini):
    fake_gemini('{"sentiment":"mixed","aspects":["chất lượng","giao hàng"],'
                '"reason":"Hàng tốt nhưng giao chậm"}')

    result = ai_service.analyze_review("Chất lượng tốt nhưng giao hàng chậm")

    assert isinstance(result, ReviewAnalysis)
    assert result.sentiment == "mixed"
    assert result.aspects == ["chất lượng", "giao hàng"]
    assert result.reason == "Hàng tốt nhưng giao chậm"


@pytest.mark.parametrize("response_text", [
    '{"sentiment":"maybe","aspects":["giá"],"reason":"Ổn"}',
    '{"sentiment":"positive","aspects":["giá","giá"],"reason":"Ổn"}',
    '{"sentiment":"positive","reason":"Thiếu aspects"}',
])
def test_invalid_response_is_rejected(fake_gemini, response_text):
    fake_gemini(response_text)

    with pytest.raises(AIServiceError, match="không hợp lệ"):
        ai_service.analyze_review("Sản phẩm ổn")


def test_gemini_error_becomes_service_error(fake_gemini):
    fake_gemini(error=RuntimeError("private SDK error"))

    with pytest.raises(AIServiceError, match="Không thể kết nối Gemini API") as exc:
        ai_service.analyze_review("Giao hàng chậm")
    assert "private SDK error" not in str(exc.value)


def test_missing_key_fails_before_calling_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(AIServiceError, match="Chưa cấu hình"):
        ai_service.analyze_review("Sản phẩm tốt")