# StockTracker.DataCollector

Collector ETL cho StockTracker: vnstock → chuẩn hóa → REST (danh mục/công ty) hoặc RabbitMQ (giá).

## Phát triển

```powershell
uv sync --frozen --dev
uv run alembic upgrade head
uv run pytest -q -p no:cacheprovider
uv run ruff check app tests scripts
uv run pyright
uv run python scripts/smoke_vnstock.py --symbol FPT
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Copy `.env.example` sang `.env` và điền thông tin M2M trước khi chạy pipeline ghi dữ liệu. Smoke chỉ đọc nguồn, không gửi đến API/RabbitMQ. Các endpoint `/run/*` và `/run/jobs/*` yêu cầu Bearer token có realm role `pipeline_operator`.

Khi bật `CONTROL_PLANE_ENABLED`, collector ghi run, step, heartbeat và watermark vào schema PostgreSQL `collector`. Chạy Alembic của collector trước khi khởi động service. Khi bật `RAW_ARCHIVE_ENABLED`, mọi phản hồi hợp lệ từ nguồn được nén gzip, gắn checksum SHA-256 và lưu vào S3 trước khi transform. Có thể resume run lỗi bằng body `{"resume_from":"<run-id>"}`; các step đã hoàn tất của run cha sẽ được ghi `skipped` và không chạy lại.

Xem [hướng dẫn nâng cấp vnstock 4.0.7](docs/vnstock-4-migration.vi.md) để biết API mapping, giới hạn dữ liệu, kiểm thử và các bước áp dụng an toàn. Báo cáo kiến trúc/lộ trình chứng chỉ nằm trong repository Deployment: `docs/architecture-review.vi.md`.
