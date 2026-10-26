"""Deployment safety checks without contacting Render, Neon or Gemini."""

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from scripts import deploy_render as deploy


SHA = "a" * 40


def test_deploy_pins_commit_before_smoke_test(monkeypatch):
    for name, value in {
        "RENDER_API_KEY": "fake-key",
        "RENDER_SERVICE_ID": "srv-example",
        "RENDER_APP_URL": "https://example.onrender.com/",
        "GITHUB_SHA": SHA,
    }.items():
        monkeypatch.setenv(name, value)
    calls = []
    monkeypatch.setattr(deploy, "api_request", lambda *args: calls.append(args) or {"id": "dep-example"})
    monkeypatch.setattr(deploy, "wait_for_live", lambda *args: calls.append(("wait", *args)))
    monkeypatch.setattr(deploy, "smoke_test", lambda *args: calls.append(("smoke", *args)))
    deploy.main()
    assert calls == [
        ("/services/srv-example/deploys", "fake-key", {"commitId": SHA}),
        ("wait", "srv-example", "dep-example", "fake-key", SHA),
        ("smoke", "https://example.onrender.com"),
    ]


@pytest.mark.parametrize("status", sorted(deploy.FAILED))
def test_failed_deploy_is_not_reported_as_live(monkeypatch, status):
    monkeypatch.setattr(deploy, "api_request", lambda *args: {"status": status})
    with pytest.raises(RuntimeError, match="deploy failed"):
        deploy.wait_for_live("srv-example", "dep-example", "fake-key", SHA)


def test_old_live_commit_is_rejected(monkeypatch):
    monkeypatch.setattr(deploy, "api_request", lambda *args: {"status": "live", "commit": {"id": "b" * 40}})
    with pytest.raises(RuntimeError, match="different commit"):
        deploy.wait_for_live("srv-example", "dep-example", "fake-key", SHA)


def test_building_deploy_waits_for_correct_commit(monkeypatch):
    responses = iter([{"status": "build_in_progress"}, {"status": "live", "commit": {"id": SHA}}])
    monkeypatch.setattr(deploy, "api_request", lambda *args: next(responses))
    monkeypatch.setattr(deploy.time, "sleep", lambda _seconds: None)
    deploy.wait_for_live("srv-example", "dep-example", "fake-key", SHA)


def test_poll_timeout_fails(monkeypatch):
    clock = iter([0, 1201])
    monkeypatch.setattr(deploy.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="Timed out"):
        deploy.wait_for_live("srv-example", "dep-example", "fake-key", SHA)


def test_api_error_does_not_leak_response_body(monkeypatch):
    def reject(*args, **kwargs):
        raise HTTPError("https://api.render.com", 401, "private-key", {}, BytesIO(b"private-key"))
    monkeypatch.setattr(deploy, "urlopen", reject)
    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        deploy.api_request("/services/srv-example/deploys", "private-key")
    assert "private-key" not in str(error.value)


@pytest.mark.parametrize("database_ok", [True, False])
def test_smoke_test_checks_database_and_public_endpoints(monkeypatch, database_ok):
    paths = []

    class Response(BytesIO):
        status = 200

    def respond(url, **kwargs):
        paths.append(url)
        if url.endswith("/health"):
            return Response(json.dumps({"status": "ok", "database": "ok" if database_ok else "failed"}).encode())
        if url.endswith("/api/products"):
            return Response(b"[]")
        return Response(b"<title>Review Insights</title>")

    monkeypatch.setattr(deploy, "urlopen", respond)
    monkeypatch.setattr(deploy.time, "sleep", lambda _seconds: None)
    # One attempt, then timeout if health is bad.
    clock = iter([0, 0, 181])
    monkeypatch.setattr(deploy.time, "monotonic", lambda: next(clock))
    if database_ok:
        deploy.smoke_test("https://example.onrender.com")
        assert len(paths) == 3
    else:
        with pytest.raises(RuntimeError, match="smoke test timed out"):
            deploy.smoke_test("https://example.onrender.com")
        assert paths == ["https://example.onrender.com/health"]
