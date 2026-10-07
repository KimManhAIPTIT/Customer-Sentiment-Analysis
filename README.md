# Customer Review Insights

Ứng dụng phân tích đánh giá sản phẩm: người dùng chọn sản phẩm, nhập feedback và tùy chọn số sao; FastAPI gọi Gemini để xác định **cảm xúc**, **khía cạnh được nhắc đến** và **lý do ngắn**. Đánh giá cùng kết quả được lưu trong PostgreSQL trên Neon. Trang web hiển thị lịch sử và thống kê theo sản phẩm.

## 1. Cấu trúc project

| Đường dẫn | Vai trò |
| --- | --- |
| `app.py` | FastAPI, trang chủ, các endpoint, kiểm tra dữ liệu, điều phối AI và lưu review |
| `ai_service.py` | Gọi Gemini, kiểm tra định dạng và nhãn của kết quả |
| `database.py` | Kết nối PostgreSQL và định nghĩa bảng `products`, `reviews` |
| `templates/index.html` | Giao diện, CSS và JavaScript gọi API |
| `seed.py`, `data/sample_reviews.csv` | Nạp dữ liệu minh họa, tránh nạp trùng |
| `tests/test_app.py` | Test trang, API, database và xử lý lỗi AI |
| `tests/test_ai_service.py` | Test Gemini bằng phản hồi giả lập, không gọi API thật |
| `.env.example`, `requirements.txt` | Cấu hình mẫu và thư viện Python |

Luồng xử lý: **Trình duyệt → FastAPI → Gemini API → PostgreSQL (Neon)**. Ứng dụng lưu review ở trạng thái `pending` trước khi gọi AI; sau đó đổi sang `analyzed` nếu thành công, hoặc `failed` nếu AI lỗi.

## 2. Yêu cầu

- Python 3.12 (khuyến nghị để khớp môi trường phát triển của nhóm).
- PostgreSQL trên Neon và chuỗi kết nối của project này.
- Gemini API key để phân tích đánh giá thật. Test tự động không cần key và không kết nối Neon.

## 3. Cài đặt và cấu hình

Mở terminal tại **thư mục gốc của repo**. Chọn một trong hai cách dùng môi trường Python:

**Conda (Windows / Anaconda Prompt / Terminal PyCharm):**

```powershell
conda create -n customer_sentiment_analysis python=3.12 -y
conda activate customer_sentiment_analysis
python -m pip install -r requirements.txt
```

Nếu môi trường Conda đã có, chỉ cần `conda activate customer_sentiment_analysis` và cài requirements nếu chưa cài.

**venv (Windows PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Trên macOS/Linux, dùng `source .venv/bin/activate` sau khi tạo venv. Có thể kiểm tra phiên bản bằng `python --version`.

Tạo `.env` từ `.env.example`:

```powershell
Copy-Item .env.example .env
```

Trên macOS/Linux có thể dùng `cp .env.example .env`. Điền các giá trị thật **chỉ trong `.env` trên máy bạn**:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
DEMO_ACCESS_TOKEN=
```

Trong Neon, lấy connection string tại trang **Connect**. Nếu Neon cung cấp URL bắt đầu bằng `postgresql://`, đổi riêng tiền tố thành `postgresql+psycopg://` để SQLAlchemy dùng driver `psycopg`; giữ nguyên host, user, password, database và các tham số URL còn lại. `DEMO_ACCESS_TOKEN` là tùy chọn ở local; nếu đặt một giá trị khác rỗng, giao diện phải gửi đúng mã khi phân tích. File `.env` phải được `.gitignore` bỏ qua; không commit key hay URL chứa mật khẩu.

> Model thực tế đã được nhóm thử thành công là `gemini-3.5-flash-lite`. Nếu `.env.example` trong repo còn ghi model cũ, hãy đồng bộ giá trị mẫu đó khi nhóm cập nhật cấu hình, rồi dùng tên model được API key cho phép.

## 4. Kiểm thử tự động

```powershell
python -m pytest -q
```

Test dùng SQLite tạm và Gemini giả lập. Chúng **không ghi vào Neon và không cần API key thật**. Các test app kiểm tra HTML, tạo và lưu review, thống kê, validation, lỗi AI, demo token và nạp seed; test AI kiểm tra phản hồi hợp lệ, dữ liệu sai và lỗi dịch vụ. Số lượng test có thể thay đổi khi nhóm bổ sung ca kiểm thử; điều kiện đạt là toàn bộ test `passed`. Warning từ thư viện phụ thuộc không đồng nghĩa test thất bại.

## 5. Nạp dữ liệu mẫu

```powershell
python seed.py
```

Theo dữ liệu backend của nhóm, lần chạy đầu tạo **3 sản phẩm và 24 đánh giá mẫu** (nếu Neon database đang trống). Đánh giá mới nạp có trạng thái `pending`, chưa có cảm xúc và khía cạnh. Chạy lại seed sẽ không tạo bản ghi trùng; tổng số thêm phụ thuộc dữ liệu đã có trước đó.

Để tùy chọn phân tích tối đa hai đánh giá mẫu đang `pending` bằng Gemini thật:

```powershell
python seed.py --analyze 2
```

Lệnh `--analyze` cần Gemini key/model hợp lệ và sẽ dùng lượt gọi API. Không bắt buộc chạy lệnh này: gửi một đánh giá mới trên giao diện cũng sẽ tạo kết quả phân tích.

## 6. Chạy ứng dụng và thử trên trình duyệt

```powershell
python -m uvicorn app:app --reload
```

Mở [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Kiểm tra [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) trả `{"status":"ok","database":"ok"}`. Trong giao diện:

1. Chọn sản phẩm có sẵn. Lịch sử và thống kê chỉ thuộc sản phẩm đang chọn.
2. Nhập nội dung feedback, tùy chọn rating từ 1 đến 5; nhập demo token nếu đã cấu hình.
3. Bấm **Phân tích và lưu**. Gemini phân tích nội dung feedback; rating được lưu nhưng hiện không đưa vào lời gọi AI.
4. Xem cảm xúc, khía cạnh và giải thích trong lịch sử; tải lại trang để xác nhận dữ liệu vẫn có trong PostgreSQL.

Giao diện hiện chưa có chức năng tạo sản phẩm. Sản phẩm được nạp từ CSV qua `seed.py` hoặc được tạo bởi người quản trị database. Lịch sử API hiện trả tối đa **100 đánh giá mới nhất của mỗi sản phẩm**.

## 7. API

Tài liệu tương tác: [Swagger UI](http://127.0.0.1:8000/docs) và [ReDoc](http://127.0.0.1:8000/redoc). Thay `{product_id}` bằng ID số thực tế lấy từ `GET /api/products`.

| Phương thức và đường dẫn | Chức năng | Kết quả chính |
| --- | --- | --- |
| `GET /` | Trang giao diện Review Insights | `200`, HTML |
| `GET /health` | Kiểm tra kết nối DB | `200` với `database: ok`; `503` nếu DB không sẵn sàng |
| `GET /api/products` | Danh sách sản phẩm | `200`, mảng `{id, name}` |
| `GET /api/products/{product_id}/reviews` | Lịch sử của một sản phẩm | `200`, tối đa 100 review; `404` nếu không có sản phẩm |
| `GET /api/products/{product_id}/summary` | Đếm các nhãn đã phân tích | `200`, `total_analyzed` và các nhãn; `404` nếu không có sản phẩm |
| `POST /api/reviews/analyze` | Gọi Gemini, lưu review và kết quả | `201` và review `analyzed`; `502` và review `failed` nếu AI lỗi |

Ví dụ body của `POST /api/reviews/analyze`:

```json
{
  "product_id": 1,
  "review_text": "Chất lượng tốt nhưng giao hàng chậm",
  "rating": 3
}
```

`rating` có thể là `null`. Nội dung chỉ gồm khoảng trắng hoặc rating ngoài 1–5 trả `422`; sản phẩm không tồn tại trả `404`. Nếu đã đặt `DEMO_ACCESS_TOKEN` trong môi trường, request cần header `X-Demo-Token` tương ứng; sai hoặc thiếu mã trả `403` và không lưu review. Khi AI thất bại, app đã lưu review rồi nên lịch sử có thể hiển thị trạng thái `failed`.

## 8. Database và bàn giao

- `products`: `id`, `name` (tên duy nhất).
- `reviews`: `product_id`, `review_text`, `rating`, `source`, `sentiment`, `aspects`, `reason`, `status`, `created_at`, `analyzed_at`.
- Thống kê trong giao diện được tính từ các review có `status="analyzed"`, không có bảng thống kê riêng.
- `init_db()` dùng `create_all()` để tạo các bảng còn thiếu lần đầu; khi thay schema đã triển khai cần migration riêng.

Phiên bản README này mô tả phần ứng dụng AI/frontend và backend/database đã ghép trên nhánh `feature/ai-frontend`. Các thành viên phụ trách Docker, GitHub Actions và triển khai sẽ bổ sung hướng dẫn build image, pipeline và URL HTTPS sau khi PR ứng dụng được gộp vào `main`.