# Hướng dẫn Docker hoá dự án Customer-Sentiment-Analysis

Nhánh làm việc: `feature/dockerization` · Mục tiêu: đóng gói app thành Docker image và đẩy lên Docker Hub.

## 0. Lưu ý quan trọng: mẫu hướng dẫn KHÔNG khớp với dự án

Mẫu Dockerfile được giao viết cho **Streamlit** (`streamlit run app.py`, cổng 8501, health `/_stcore/health`).
Dự án này thực tế là **FastAPI + Uvicorn**:

| Mục | Mẫu được giao | Dự án thực tế |
|---|---|---|
| Framework | Streamlit | FastAPI (`app = FastAPI(...)` trong `app.py`) |
| Lệnh chạy | `streamlit run app.py` | `uvicorn app:app` |
| Cổng | 8501 | 8000 (mặc định uvicorn) |
| Health check | `/_stcore/health` | `/health` (có sẵn, có truy vấn DB) |
| Biến môi trường | `DATABASE_URL` | `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `DEMO_ACCESS_TOKEN` |
| Thư viện hệ thống | `build-essential`, `libpq-dev` | Không cần: `psycopg[binary]` đã kèm libpq |

Nếu copy nguyên mẫu, container sẽ crash ngay (`streamlit: not found`). Dùng các file dưới đây.

---

## 1. Chuẩn bị

1. Cài Docker (Fedora): `sudo dnf install docker-ce` hoặc `podman-docker`; bật `sudo systemctl enable --now docker`.
2. Cài git (máy hiện **chưa có git**): `sudo dnf install git`.
3. Tạo tài khoản Docker Hub và một **Access Token** (Account Settings → Personal access tokens), dùng thay mật khẩu.
4. Tạo nhánh:

```bash
cd Customer-Sentiment-Analysis
git checkout main && git pull
git checkout -b feature/dockerization
```

## 2. Tạo `.dockerignore`

Mở rộng so với mẫu để image nhỏ và không lọt secret (dự án dùng `.venv`, không phải `venv`):

```
__pycache__
*.pyc
.git
.github
.env
.venv
venv
.pytest_cache
.idea
*.db
*.sqlite3
tests
khoitao.md
DOCKER_SETUP_GUIDE.md
```

> Không ignore `templates/` và `data/` — app cần `templates/index.html`, còn `seed.py` đọc `data/sample_reviews.csv`.

Commit: `git add .dockerignore && git commit -m "chore: add .dockerignore"`

## 3. Viết `Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Chạy bằng user không phải root
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Giải thích:
- Copy `requirements.txt` trước để tận dụng cache layer — đổi code không phải cài lại thư viện.
- Health check dùng Python có sẵn nên không cần cài `curl`/`apt-get`.
- `--host 0.0.0.0` bắt buộc, nếu không sẽ không truy cập được từ ngoài container.
- Tuỳ chọn: tách `pytest`, `httpx` ra `requirements-dev.txt` để image gọn hơn.

Commit: `git commit -m "feat: add Dockerfile for FastAPI app"`

## 4. Build và chạy thử tại máy

```bash
docker build -t sentiment-app:latest .
```

Chạy bằng file `.env` (không gõ secret trên dòng lệnh, tránh lưu vào shell history):

```bash
cp .env.example .env   # rồi điền DATABASE_URL Neon, GEMINI_API_KEY, DEMO_ACCESS_TOKEN thật
docker run --rm -p 8000:8000 --env-file .env --name sentiment sentiment-app:latest
```

Kiểm tra:

```bash
curl http://localhost:8000/health
docker ps                      # cột STATUS phải chuyển sang (healthy)
docker logs sentiment
```

Mở trình duyệt `http://localhost:8000` để xem giao diện, `http://localhost:8000/docs` để thử API.

(Tuỳ chọn) chạy seed dữ liệu trong container:

```bash
docker exec -it sentiment python seed.py
```

Lỗi thường gặp:
- `RuntimeError: Chưa cấu hình DATABASE_URL` → thiếu `--env-file .env`.
- `/health` lỗi 500 → chuỗi Neon sai hoặc thiếu `?sslmode=require`.
- `TemplateNotFound` → đã lỡ ignore `templates/`.

## 5. (Khuyến nghị) Thêm `docker-compose.yml`

```yaml
services:
  app:
    build: .
    image: sentiment-app:latest
    ports:
      - "8000:8000"
    env_file: .env
    restart: unless-stopped
```

Chạy: `docker compose up --build`. Commit: `git commit -m "chore: add docker-compose for local run"`

## 6. Đẩy image lên Docker Hub

Mẫu bị thiếu username (`/sentiment-app` là sai cú pháp). Thay `<DOCKERHUB_USERNAME>`:

```bash
docker login -u <DOCKERHUB_USERNAME>        # nhập Access Token khi được hỏi
docker tag sentiment-app:latest <DOCKERHUB_USERNAME>/sentiment-app:latest
docker tag sentiment-app:latest <DOCKERHUB_USERNAME>/sentiment-app:v1.0.0
docker push <DOCKERHUB_USERNAME>/sentiment-app:latest
docker push <DOCKERHUB_USERNAME>/sentiment-app:v1.0.0
```

Vào hub.docker.com → repository `sentiment-app` → Settings → đặt **Public**.
Link bàn giao: `https://hub.docker.com/r/<DOCKERHUB_USERNAME>/sentiment-app`

Kiểm chứng image public chạy được:

```bash
docker rmi <DOCKERHUB_USERNAME>/sentiment-app:latest
docker run --rm -p 8000:8000 --env-file .env <DOCKERHUB_USERNAME>/sentiment-app:latest
```

## 7. CI/CD đã có sẵn

`.github/workflows/deploy.yml` đã build và push lên `${DOCKER_USERNAME}/sentiment-app:latest` khi merge vào `main` (PR chỉ build, không push). Cần:
- GitHub repo → Settings → Secrets and variables → Actions: thêm `DOCKER_USERNAME` và `DOCKER_PASSWORD` (dán Access Token).
- (Tuỳ chọn) thêm bước `pytest` trước bước build, và tag thêm `${{ github.sha }}`.

Workflow này chỉ chạy được khi đã có `Dockerfile` ở thư mục gốc — nên hiện tại nó đang fail.

## 8. Commit (6–8 commit) và Pull Request

Gợi ý chuỗi commit:

1. `chore: add .dockerignore`
2. `feat: add Dockerfile for FastAPI app`
3. `feat: add container healthcheck using /health endpoint`
4. `chore: run container as non-root user`
5. `chore: add docker-compose for local run`
6. `ci: add DockerHub secrets usage and test step to deploy workflow`
7. `docs: add Docker build/run/push instructions to README`
8. `docs: add Docker Hub image link`

```bash
git push -u origin feature/dockerization
gh pr create --base main --title "Dockerize FastAPI app and publish to Docker Hub" \
  --body "Thêm Dockerfile, .dockerignore, docker-compose; image public: https://hub.docker.com/r/<DOCKERHUB_USERNAME>/sentiment-app"
```

## 9. Checklist bàn giao

- [ ] `.dockerignore` không loại `templates/`, `data/`; có loại `.env`
- [ ] `Dockerfile` chạy `uvicorn` cổng 8000, container báo `(healthy)`
- [ ] Không có secret nào trong image (`docker history` / `.env` bị ignore)
- [ ] Image public trên Docker Hub, pull về chạy được
- [ ] Secrets `DOCKER_USERNAME`, `DOCKER_PASSWORD` đã thêm trên GitHub, workflow xanh
- [ ] 6–8 commit trên `feature/dockerization`, PR về `main` có link image
