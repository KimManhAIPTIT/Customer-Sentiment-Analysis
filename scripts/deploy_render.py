"""Deploy the tested Git commit to Render, wait for live, then smoke-test HTTPS.

Uses only Python's standard library. Credentials come from GitHub secrets.
Render builds the same commit with the repository Dockerfile; it does not pull
the separately published Docker Hub image.
"""

import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


API_ROOT = "https://api.render.com/v1"
FAILED = {"build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated"}


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing configuration: {name}")
    return value


def api_request(path, token, payload=None):
    request = Request(
        API_ROOT + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not dump responses, headers, API keys or connection strings to CI.
        raise RuntimeError(f"Render API returned HTTP {exc.code}; check Render configuration") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Render API connection failed") from None


def wait_for_live(service_id, deploy_id, token, commit_sha, timeout=1200):
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        deploy = api_request(f"/services/{service_id}/deploys/{deploy_id}", token)
        status = deploy.get("status")
        if status != last_status:
            print(f"Render deploy status: {status}", flush=True)
            last_status = status
        if status == "live":
            if deploy.get("commit", {}).get("id") != commit_sha:
                raise RuntimeError("Render reports a different commit; refusing to mark deployment successful")
            return
        if status in FAILED:
            raise RuntimeError(f"Render deploy failed: {status}. Open Render Events/Logs")
        time.sleep(10)
    raise RuntimeError("Timed out waiting for Render to become live; check Render Events/Logs")


def smoke_test(base_url, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(base_url + "/health", timeout=20) as response:
                health = json.load(response)
                if response.status != 200 or health != {"status": "ok", "database": "ok"}:
                    raise ValueError("Unhealthy database")
            with urlopen(base_url + "/", timeout=20) as response:
                if response.status != 200 or "Review Insights" not in response.read().decode():
                    raise ValueError("Unexpected home page")
            with urlopen(base_url + "/api/products", timeout=20) as response:
                if response.status != 200 or not isinstance(json.load(response), list):
                    raise ValueError("Unexpected products response")
            print("HTTPS smoke test passed: home page, PostgreSQL health and products API", flush=True)
            return
        except (URLError, TimeoutError, ValueError):
            time.sleep(10)
    raise RuntimeError("HTTPS smoke test timed out; check app URL, runtime logs and Neon connectivity")


def main():
    token = required("RENDER_API_KEY")
    service_id = required("RENDER_SERVICE_ID")
    base_url = required("RENDER_APP_URL").rstrip("/")
    commit_sha = required("GITHUB_SHA")
    url = urlsplit(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path:
        raise RuntimeError("RENDER_APP_URL must be an HTTPS origin without credentials, path or query")
    if not re.fullmatch(r"srv-[a-zA-Z0-9]+", service_id):
        raise RuntimeError("Invalid RENDER_SERVICE_ID")
    if not re.fullmatch(r"[a-f0-9]{40}", commit_sha):
        raise RuntimeError("Invalid GITHUB_SHA")

    # POST is deliberately not retried: a network timeout could already have
    # created a deployment. Inspect Render before manually rerunning the job.
    deploy = api_request(f"/services/{service_id}/deploys", token, {"commitId": commit_sha})
    deploy_id = deploy.get("id", "")
    if not re.fullmatch(r"dep-[a-zA-Z0-9]+", deploy_id):
        raise RuntimeError("Render did not return a valid deployment ID")
    wait_for_live(service_id, deploy_id, token, commit_sha)
    smoke_test(base_url)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
