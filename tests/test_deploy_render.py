"""Test image deployment without contacting Render, Neon or Gemini."""

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from scripts import deploy_render as deploy


SHA = "a" * 40
IMAGE_URL = f"docker.io/khanhptit09/sentiment-app:{SHA}"


def test_deploy_pins_image_before_smoke_test(monkeypatch):
    for name, value in {
        "RENDER_API_KEY": "fake-key",
        "RENDER_SERVICE_ID": "srv-example",
        "RENDER_APP_URL": "https://example.onrender.com/",
        "GITHUB_SHA": SHA,
    }.items():
        monkeypatch.setenv(name, value)

    calls = []

    def fake_api(*args):
        calls.append(args)
        return {"id": "dep-example"}

    monkeypatch.setattr(deploy, "api_request", fake_api)
    monkeypatch.setattr(
        deploy,
        "wait_for_live",
        lambda *args: calls.append(("wait", *args)),
    )
    monkeypatch.setattr(
        deploy,
        "smoke_test",
        lambda *args: calls.append(("smoke", *args)),
    )

    deploy.main()

    assert calls == [
        (
            "/services/srv-example/deploys",
            "fake-key",
            {"imageUrl": IMAGE_URL},
        ),
        ("wait", "srv-example", "dep-example", "fake-key", SHA),
        ("smoke", "https://example.onrender.com"),
    ]


@pytest.mark.parametrize("status", sorted(deploy.FAILED))
def test_failed_deploy_is_not_reported_as_live(monkeypatch, status):
    monkeypatch.setattr(
        deploy,
        "api_request",
        lambda *args: {"status": status},
    )

    with pytest.raises(RuntimeError, match="deploy failed"):
        deploy.wait_for_live(
            "srv-example", "dep-example", "fake-key", SHA
        )


def test_live_image_deploy_does_not_require_git_commit(monkeypatch):
    calls = []

    def fake_api(path, token):
        calls.append((path, token))
        return {"status": "live"}

    monkeypatch.setattr(deploy, "api_request", fake_api)

    deploy.wait_for_live(
        "srv-example", "dep-example", "fake-key", SHA
    )

    assert calls == [
        (
            "/services/srv-example/deploys/dep-example",
            "fake-key",
        )
    ]


def test_deploy_waits_until_live(monkeypatch):
    responses = iter([
        {"status": "update_in_progress"},
        {"status": "live"},
    ])
    calls = []
    sleeps = []

    def fake_api(path, token):
        calls.append((path, token))
        return next(responses)

    monkeypatch.setattr(deploy, "api_request", fake_api)
    monkeypatch.setattr(
        deploy.time,
        "sleep",
        lambda seconds: sleeps.append(seconds),
    )

    deploy.wait_for_live(
        "srv-example", "dep-example", "fake-key", SHA
    )

    assert calls == [
        ("/services/srv-example/deploys/dep-example", "fake-key"),
        ("/services/srv-example/deploys/dep-example", "fake-key"),
    ]
    assert sleeps == [10]


def test_poll_timeout_fails(monkeypatch):
    clock = iter([0, 1201])
    monkeypatch.setattr(
        deploy.time, "monotonic", lambda: next(clock)
    )

    with pytest.raises(RuntimeError, match="Timed out"):
        deploy.wait_for_live(
            "srv-example", "dep-example", "fake-key", SHA
        )


def test_api_error_does_not_leak_response_body(monkeypatch):
    def reject(*args, **kwargs):
        raise HTTPError(
            "https://api.render.com",
            401,
            "private-key",
            {},
            BytesIO(b"private-key"),
        )

    monkeypatch.setattr(deploy, "urlopen", reject)

    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        deploy.api_request(
            "/services/srv-example/deploys", "private-key"
        )

    assert "private-key" not in str(error.value)


@pytest.mark.parametrize("database_ok", [True, False])
def test_smoke_test_checks_database_and_public_endpoints(
    monkeypatch, database_ok
):
    paths = []

    class Response(BytesIO):
        status = 200

    def respond(url, **kwargs):
        paths.append(url)

        if url.endswith("/health"):
            body = {
                "status": "ok",
                "database": "ok" if database_ok else "failed",
            }
            return Response(json.dumps(body).encode())

        if url.endswith("/api/products"):
            return Response(b"[]")

        return Response(b"<title>Review Insights</title>")

    monkeypatch.setattr(deploy, "urlopen", respond)
    monkeypatch.setattr(
        deploy.time, "sleep", lambda _seconds: None
    )

    # Một lần thử; hết thời gian nếu database chưa sẵn sàng.
    clock = iter([0, 0, 181])
    monkeypatch.setattr(
        deploy.time, "monotonic", lambda: next(clock)
    )

    if database_ok:
        deploy.smoke_test("https://example.onrender.com")
        assert paths == [
            "https://example.onrender.com/health",
            "https://example.onrender.com/",
            "https://example.onrender.com/api/products",
        ]
    else:
        with pytest.raises(
            RuntimeError, match="smoke test timed out"
        ):
            deploy.smoke_test("https://example.onrender.com")

        assert paths == [
            "https://example.onrender.com/health"
        ]
