Markdown

# Customer Review Insights - Backend (Giai đoạn 1)

Phiên bản backend chạy độc lập phục vụ lưu trữ đánh giá, nạp dữ liệu mẫu và kiểm thử tự động, tách biệt hoàn toàn với giao diện HTML và dịch vụ Gemini AI.

1. Yêu cầu môi trường

    Python 3.10 trở lên

    Cơ sở dữ liệu PostgreSQL (Neon DB)

2. Hướng dẫn cài đặt & Khởi động
Bước 1: Kích hoạt môi trường ảo

Mở terminal tại thư mục gốc của project:
Tạo môi trường ảo (nếu chưa có)

python3 -m venv .venv
Kích hoạt trên Linux/macOS:

source .venv/bin/activate
Kích hoạt trên Windows PowerShell:
..venv\Scripts\Activate.ps1
Bước 2: Cài đặt thư viện phụ thuộc

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Bước 3: Cấu hình biến môi trường

Tạo file .env từ .env.example và điền chuỗi kết nối Neon PostgreSQL của bạn:
cp .env.example .env

Nội dung file .env mẫu:
DATABASE_URL=postgresql://:@/?sslmode=require
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
DEMO_TOKEN=
3. Kiểm thử tự động (Unit Test)

Bộ test chạy trên cơ sở dữ liệu SQLite tạm thời (tmp_path), hoạt động độc lập không cần mạng và không ghi đè dữ liệu trên Neon DB:

python -m pytest -q

    Kết quả mong đợi: 4 passed (hoặc 6 passed nếu có thêm test biên).

4. Nạp dữ liệu mẫu (Seed Data)

Nạp dữ liệu mẫu từ data/sample_reviews.csv vào Neon PostgreSQL. Lệnh có tính chất lũy thừa (chạy nhiều lần không gây trùng lặp dữ liệu):

python seed.py


    Lần chạy đầu tiên: Thêm 3 sản phẩm và 24 đánh giá mẫu.

    Lần chạy tiếp theo: Thêm 0 bản ghi.

5. Khởi chạy Server

Khởi động backend server:

python -m uvicorn app:app --reload

Server chạy tại địa chỉ: http://127.0.0.1:8000
6. Danh sách API Endpoint (Giai đoạn 1)

Lưu ý: Với các endpoint có chứa {product_id}, phải thay bằng số ID thực tế (ví dụ: 1, 2), không giữ nguyên ngoặc nhọn {} trên Postman.

    GET /

        Mô tả: Kiểm tra trạng thái sẵn sàng của backend.

        Mã HTTP: 200 OK

        Response mẫu: {"status": "backend_ready"}

    GET /health

        Mô tả: Kiểm tra tình trạng kết nối ứng dụng và Neon database.

        Mã HTTP: 200 OK

        Response mẫu: {"status": "ok", "database": "ok"}

    GET /api/products

        Mô tả: Lấy toàn bộ danh sách sản phẩm hiện có trong database.

        Mã HTTP: 200 OK

        Response mẫu: [{"id": 1, "name": "..."}, ...]

    GET /api/products/{product_id}/reviews

        Mô tả: Lấy danh sách các đánh giá của sản phẩm theo ID (ví dụ: /api/products/1/reviews).

        Mã HTTP: 200 OK (hoặc 404 Not Found nếu product_id không tồn tại)

        Response mẫu: Danh sách review kèm status "pending" hoặc "seed".

    GET /api/products/{product_id}/summary

        Mô tả: Thống kê đánh giá của sản phẩm (ví dụ: /api/products/1/summary).

        Mã HTTP: 200 OK (hoặc 404 Not Found nếu product_id không tồn tại)

        Response mẫu: {"product_id": 1, "total_analyzed": 0, "sentiments": {"positive": 0, "neutral": 0, "negative": 0, "mixed": 0}}

        Lưu ý: Giai đoạn 1 chưa chạy AI nên total_analyzed luôn bằng 0.

    POST /api/reviews/analyze

        Mô tả: Tiếp nhận và lưu đánh giá của người dùng vào DB ở trạng thái chờ AI xử lý.

        Mã HTTP: 202 Accepted (Giai đoạn 1 không trả 201 và chưa gọi AI)

        Headers: Content-Type: application/json

        Body mẫu (JSON):
        {
        "product_id": 1,
        "review_text": "Tai nghe bass chắc, đeo lâu không bị đau tai.",
        "rating": 5
        }

        Response mẫu: Trả về review vừa lưu với status: "pending", source: "user", các trường AI (sentiment, aspects, reason) là null/rỗng.

        Các mã lỗi bắt buộc:

            422 Unprocessable Entity: Nếu review_text để trống, chỉ chứa khoảng trắng, hoặc rating không từ 1 đến 5.

            404 Not Found: Nếu product_id gửi lên không tồn tại trong DB.

7. Tài liệu tương tác API

    Swagger UI: http://127.0.0.1:8000/docs

    ReDoc: http://127.0.0.1:8000/redoc