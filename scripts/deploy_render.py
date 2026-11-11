"""Deploy a Docker Hub image tagged with the tested commit SHA to Render."""

import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


API_ROOT = "https://api.render.com/v1"
IMAGE_REPOSITORY = "docker.io/khanhptit09/sentiment-app"

FAILED = {
    "build_failed",
    "update_failed",
    "pre_deploy_failed",
    "canceled",
    "deactivated",
}


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing configuration: {name}")
    return value


def api_request(path, token, payload=None):
    request = Request(
        API_ROOT + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Không in response có thể chứa thông tin nhạy cảm.
        raise RuntimeError(
            f"Render API returned HTTP {exc.code}; check Render configuration"
        ) from None
    except (URLError, TimeoutError):
        raise RuntimeError("Render API connection failed") from None
    except ValueError:
        raise RuntimeError("Render API returned invalid JSON") from None


def wait_for_live(service_id, deploy_id, token, commit_sha, timeout=1200):
    # Giữ tham số commit_sha để tương thích với các lời gọi hiện có.
    # Phiên bản image đã được chọn bằng tag SHA khi tạo deploy.
    deadline = time.monotonic() + timeout
    last_status = None

    while time.monotonic() < deadline:
        deploy = api_request(
            f"/services/{service_id}/deploys/{deploy_id}",
            token,
        )
        status = deploy.get("status")

        if status != last_status:
            print(f"Render deploy status: {status}", flush=True)
            last_status = status

        if status == "live":
            print(
                f"Render deployment is live for image tag: {commit_sha}",
                flush=True,
            )
            return

        if status in FAILED:
            raise RuntimeError(
                f"Render deploy failed: {status}. Open Render Events/Logs"
            )

        time.sleep(10)

    raise RuntimeError(
        "Timed out waiting for Render to become live; "
        "check Render Events/Logs"
    )


def smoke_test(base_url, timeout=180):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            with urlopen(base_url + "/health", timeout=20) as response:
                health = json.load(response)
                if response.status != 200 or health != {
                    "status": "ok",
                    "database": "ok",
                }:
                    raise ValueError("Unhealthy database")

            with urlopen(base_url + "/", timeout=20) as response:
                page = response.read().decode("utf-8")
                if response.status != 200 or "Review Insights" not in page:
                    raise ValueError("Unexpected home page")

            with urlopen(base_url + "/api/products", timeout=20) as response:
                products = json.load(response)
                if response.status != 200 or not isinstance(products, list):
                    raise ValueError("Unexpected products response")

            print(
                "HTTPS smoke test passed: home page, "
                "PostgreSQL health and products API",
                flush=True,
            )
            return

        except (URLError, TimeoutError, ValueError):
            time.sleep(10)

    raise RuntimeError(
        "HTTPS smoke test timed out; check app URL, "
        "runtime logs and Neon connectivity"
    )


def main():
    token = required("RENDER_API_KEY")
    service_id = required("RENDER_SERVICE_ID")
    base_url = required("RENDER_APP_URL").rstrip("/")
    commit_sha = required("GITHUB_SHA")

    url = urlsplit(base_url)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path
    ):
        raise RuntimeError(
            "RENDER_APP_URL must be an HTTPS origin "
            "without credentials, path or query"
        )

    if not re.fullmatch(r"srv-[a-zA-Z0-9]+", service_id):
        raise RuntimeError("Invalid RENDER_SERVICE_ID")

    if not re.fullmatch(r"[a-f0-9]{40}", commit_sha):
        raise RuntimeError("Invalid GITHUB_SHA")

    # Workflow phải push tag này lên Docker Hub trước khi chạy script.
    image_url = f"{IMAGE_REPOSITORY}:{commit_sha}"
    print(f"Deploying Docker image: {image_url}", flush=True)

    # Không tự retry POST để tránh tạo hai deployment khi bị timeout.
    deploy = api_request(
        f"/services/{service_id}/deploys",
        token,
        {"imageUrl": image_url},
    )

    deploy_id = deploy.get("id", "")
    if not re.fullmatch(r"dep-[a-zA-Z0-9]+", deploy_id):
        raise RuntimeError("Render did not return a valid deployment ID")

    # Theo dõi đúng deployment vừa tạo.
    wait_for_live(service_id, deploy_id, token, commit_sha)
    smoke_test(base_url)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
