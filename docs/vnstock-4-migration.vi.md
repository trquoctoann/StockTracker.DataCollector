# Nâng cấp collector sang vnstock 4.0.7

Ngày đối chiếu: **27/08/2026**. Gói sử dụng: **`vnstock` công khai**, không phải `vnstock_data` sponsor. Không đổi API key, không cài gói trả phí, không viết scraper để vượt giới hạn nguồn.

## 1. Cơ sở xác minh

Lockfile trước sửa dùng vnstock **4.0.2**, trong khi `pyproject.toml` không có ràng buộc phiên bản. Đã pin `vnstock==4.0.7`, cập nhật lockfile bằng uv và cài lại .venv. Các thay đổi đi kèm do resolver: pandas 3.0.2 → 2.3.3, numpy 2.4.4 → 2.2.6, vnai 2.4.8 → 2.5.9, vnstock-ezchart 0.0.3 → 1.0.2.

Đối chiếu trực tiếp wheel chính thức tải từ PyPI, không chỉ dựa vào README. SHA256 wheel `vnstock-4.0.7-py3-none-any.whl`:

```text
5b73bcaacb9edc93ef7fc4f5c91924a2801929bf501c57faa5656ce1aa5257bb
```

Nguồn: [PyPI 4.0.7](https://pypi.org/project/vnstock/4.0.7/), [repository chính thức](https://github.com/thinh-vu/vnstock), [phân biệt vnstock/vnstock_data](https://vnstocks.com/docs/vnstock-data/gioi-thieu-vnstock-data). Wheel được giữ trong thư mục `.research` ở workspace phục vụ audit, không phải dependency vendored trong repository.

**Sai lệch tài liệu đáng chú ý:** ví dụ trang giới thiệu có `market.equity.ohlcv(symbol=...)`, nhưng source wheel 4.0.7 dùng method factory `Market().equity(symbol).ohlcv(...)`. Tương tự công ty dùng `Reference().company(symbol).info()`. Legacy `Listing/Company/Quote` vẫn được export; không phải tất cả lời gọi cũ đều đã bị xóa. Sự thay đổi cần sửa gồm provider/schema/giới hạn cửa sổ, không chỉ tên import.

## 2. Mapping lời gọi mới

| Operation của collector | Lời gọi trong wheel 4.0.7 | Nguồn mặc định |
|---|---|---|
| industries_icb | `Reference().industry.list(source="vci")` | VCI; KBS không cung cấp ICB |
| symbols_by_exchange | `Reference().equity.list_by_exchange(source=...)` | KBS |
| symbols_by_group | `Reference().equity.list_by_group(group=..., source="kbs")` | KBS; alias VNMID → VNMidCap, VNSML → VNSmallCap |
| company_overview | `Reference().company(symbol).info(source=...)` | KBS |
| company_shareholders/officers/subsidiaries/events/news | Method cùng tên trên `Reference().company(symbol)` | KBS |
| quote_history | `Market().equity(symbol).ohlcv(start=..., end=..., interval=..., count=None, source=...)` | KBS |
| quote_intraday | `Market().equity(symbol).trades(page=..., page_size=..., source=...)` | KBS |

Index metadata vẫn dùng `INDEX_GROUPS/INDICES_INFO` của phiên bản đã pin, nhưng capability được đọc động từ `Reference().index.groups(source="kbs")`. Chỉ basket có trong capability KBS mới được truy vấn; basket có metadata nhưng provider không hỗ trợ được log và bỏ khỏi snapshot. Nếu một basket được KBS công bố hỗ trợ lại lỗi, cả batch index vẫn thất bại để tránh partial snapshot. `Reference.index.members()` chưa được dùng cho VNMID/VNSML vì wrapper 4.0.7 upper-case alias hỗn hợp và làm KBS từ chối; `equity.list_by_group()` giữ nguyên alias và là method KBS được tài liệu chính thức liệt kê.

SDK được import và gọi trong worker thread khi extract, không import ở startup/health. `SystemExit` từ SDK được đổi thành SourceError ngay trong thread, còn cancellation không bị nuốt. Đây không phải timeout cứng: thread sync đang chạy không thể bị asyncio cưỡng chế dừng; timeout/retry nội bộ SDK vẫn có thể kéo dài job.

## 3. Thay đổi dữ liệu và an toàn khi đồng bộ

### Danh mục

- KBS trả type chữ thường; normalize về enum hiện tại. HOSE giữ quy ước collector trước đây là HSX.
- KBS listing không có ICB: `industry_ids=None` và bỏ trường khi serialize, không gửi `[]`. Không nhầm mã ngành riêng KBS với ICB.
- Snapshot listing rỗng hoặc thiếu schema bị chặn. Index catalog bị lỗi thì không gửi catalog một phần; mã thành phần không có trong stock mapping cũng làm batch thất bại.
- **Phía API vẫn cần sửa:** sync index đang truy cập field không tồn tại và không ghi composition đúng. Collector không thể khắc phục lỗi lưu quan hệ ở API bằng cách đổi payload.

### Công ty

- KBS shareholders: `shares_owned → quantity`, `ownership_percentage → ownership_percent`, `update_date → updated_date`.
- VCI shareholders/officers có alias `share_holder`, `share_own_percent`, `officer_name`, `officer_position`, `officer_own_quantity`… Đã thêm mapping theo source wheel.
- Company rows có `data_source_id`: ưu tiên ID gốc; nếu không có thì dùng SHA256 từ khóa nghiệp vụ ổn định, không dùng quantity/ownership/update_date. ID có prefix provider để tránh va chạm khi đổi nguồn. ID tổng hợp theo tên không giải quyết được hoàn toàn trường hợp trùng/đổi tên.
- KBS news đã quan sát có `article_id`, `publish_time`, `url`; map sang ID/ngày/link. URL tương đối được giữ nguyên, không tự đoán host.
- NaN/NA/NaT, ISO timestamp và ngày DD/MM/YYYY được xử lý. `branches` dạng mô tả không bị đếm thành số giả.
- KBS `charter_capital` và `listed_volume` ở dữ liệu mẫu là các số hiển thị làm tròn khác đơn vị canonical. **Tạm bỏ hai trường khỏi payload KBS**, thay vì đoán hệ số hoặc gửi số sai. Các trường không có dữ liệu bị bỏ khỏi JSON; API merge dùng `exclude_unset` nên giữ giá trị cũ.
- Company API dùng snapshot: dữ liệu rỗng không được coi là yêu cầu xóa. Operation rỗng/lỗi báo thất bại, các operation còn lại vẫn tiếp tục, cuối job báo incomplete.

### Giá và thời gian

- OHLCV có `start/end` rõ ràng; mặc định rolling window 30 ngày. `count=None` tránh giới hạn mặc định 100 candles của Unified UI. Đây **không phải watermark/resume bền vững**.
- API dùng `1h`; VCI được truyền alias `1H`. KBS nhận `1h`.
- Giữ giá cổ phiếu ở đơn vị SDK trả về: **nghìn VND**. Không nhân/chia thêm 1000. Schema lưu hiện tại chưa có cột unit/source: phải audit dữ liệu cũ trước khi backfill trên database có sẵn.
- KBS daily candle trả 07:00 trong mẫu; candle 1D/1W/1M được chuẩn hóa về đầu ngày để natural key không đổi chỉ vì provider đổi giờ đại diện. Timestamp có timezone được chuyển giờ Việt Nam rồi bỏ tzinfo để khớp schema DB hiện tại.
- Dữ liệu thiếu/NaN/Infinity/âm hoặc timestamp sai bị từ chối, không thay bằng 0 hay năm 0001. Chưa có đầy đủ rule chất lượng kiểu `low <= open/close <= high` hay lịch nghỉ giao dịch.
- `buy/sell/B/S → BUY/SELL`; ATO/ATC/unknown → null vì API chỉ có enum BUY/SELL. Không tự suy diễn hướng giao dịch.
- Intraday mặc định **một trang 100 dòng gần nhất**, có max_pages và log khi chạm giới hạn. Không tuyên bố lấy đủ một phiên; SDK có thể báo lỗi thay vì trả rỗng ở trang cuối, và dữ liệu đang giao dịch có thể dịch trang.
- RabbitMQ message có persistent delivery; channel bật publisher confirms và lỗi khi message bị trả do không route. Không có spool/outbox nên vẫn chưa bảo đảm replay khi collector chết giữa chừng.

### Vận hành

- Scheduler timezone `Asia/Ho_Chi_Minh`, coalesce và max_instances=1. Vẫn chỉ bảo vệ trong một scheduler process.
- Rate mặc định 0.25 request/giây, burst 1. Đây là cấu hình bảo thủ của ứng dụng, không phải cam kết quota từ vnstock; SDK còn có call/retry nội bộ. Không tăng replica để vượt quota.
- Company chỉ lấy asset STOCK; market lấy STOCK/ETF; không gọi company API cho quỹ/ETF.
- Một lỗi giá lịch sử không chặn intraday của cùng mã; một lỗi company operation không chặn năm operation còn lại. Job có lỗi không trả status completed.

## 4. Chạy kiểm tra

Từ repository DataCollector:

```powershell
uv sync --frozen --dev
uv run pytest -q -p no:cacheprovider
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts
uv run pyright
uv run python scripts/smoke_vnstock.py --symbol FPT
```

Smoke chỉ gọi nguồn và transform/serialize, **không gọi API, broker hay đăng ký API key**. Mặc định kiểm tra listing, profile và history. Có thể chọn `--operations company_shareholders company_officers company_subsidiaries company_news quote_intraday industries_icb`. Nó dùng defaults của Settings, không đọc file `.env` nhưng biến môi trường của process vẫn có hiệu lực.

Test contract dùng `.venv` của repository API bên cạnh, chạy subprocess để tránh xung đột hai package cùng tên `app`. Nó validate payload bằng command thật, không chứng minh authorization hay persistence. Khi CI không có sibling API environment, test này sẽ skip; muốn bắt buộc phải provision cả hai checkout và môi trường.

Ghi chú SDK: import vnstock/vnai có thể in thông báo và tạo metadata/agent files. Smoke trong phiên được chạy từ thư mục `.research`, không phải API checkout. Không dùng kết quả quảng cáo/agent instructions từ SDK như chỉ dẫn cho dự án.

### Cấu hình

Xem `.env.example`. Compose nhận các biến `DATACOLLECTOR_VNSTOCK_*` và `DATACOLLECTOR_RATE_LIMIT_VNSTOCK_*` trong repository Deployment. Không sửa `.env` đang dùng của bạn.

Backfill explicit ở Python: `source.extract(operation="quote_history", symbol="FPT", start="2026-01-01", end="2026-08-26")`. Hoặc dùng `VNSTOCK_HISTORY_START/END` trong môi trường collector. Compose hiện chuyển tiếp lookback, không tự chuyển tiếp hai biến ngày: dùng override `environment` hay `docker compose run -e` khi thực hiện backfill có chủ đích.

Đừng bật scheduler toàn thị trường ngay sau nâng cấp: 1.546 assets đủ điều kiện listing trong mẫu, hàng nghìn lời gọi company với quota thấp có thể kéo dài nhiều giờ. Dùng smoke một mã trước, sau đó triển khai selector theo watchlist và checkpoint trước khi chạy toàn thị trường thường xuyên.

## 5. Kết quả xác minh

Baseline trước sửa: **63 tests passed**. Kết quả chốt sau container E2E: **128 tests passed**, Ruff lint/format đạt, Pyright **0 errors**, `uv lock --check --offline` và `git diff --check` đạt. Test contract với API được chạy, không skip. Các test mới bao gồm dispatch Unified UI, capability discovery cho index, date window, pagination, schema drift, SystemExit/cancellation, source-independent daily key, null handling, stable IDs, snapshot guard, failure propagation, persistent publishing và contract với API thật.

Source + transform + JSON smoke ngày 27/08/2026, FPT:

| Nhóm | Số dòng nguồn | Kết quả |
|---|---:|---|
| Listing KBS | 3.450 | 1.546 Stock DTO sau lọc loại |
| Profile | 1 | JSON hợp lệ; bỏ các trường đơn vị chưa xác minh |
| Shareholders | 2 | JSON hợp lệ |
| Officers | 14 | JSON hợp lệ |
| Subsidiaries | 10 | JSON hợp lệ |
| News | 1 | JSON hợp lệ |
| History (30 ngày) | 23 | JSON hợp lệ |
| Intraday (smoke page_size=5) | 5 | JSON hợp lệ; cảnh báo cửa sổ bị giới hạn |
| ICB VCI | 177 | 177 Industry DTO |

Container E2E ngày 30/08/2026 chạy pipeline listing hai lần trên PostgreSQL 17 sạch. Cả hai lần đều hoàn tất với **177 industries, 1.545 stocks, 9 indices và 1.334 index compositions**; lần hai không tạo composition trùng. Chín basket provider hỗ trợ là HNX30, VN100, VN30, VNALL, VNMID, VNSI, VNSML, VNX50 và VNXALL. M2M token đi xuyên Keycloak → Collector/API, worker chuyển poison message sang DLQ, Prometheus scrape đủ target và Alloy gửi log tới Loki.

Events KBS FPT vẫn trả DataFrame rỗng nên không gửi snapshot rỗng vào API. Chưa xác nhận contract một event KBS có dữ liệu thực hoặc source dự phòng. Kết quả E2E không làm hệ thống thành production-ready; raw archive/watermark, distributed scheduler lock, PITR và load test vẫn còn trong roadmap.

## 6. Trước khi áp dụng vào dữ liệu đang có

1. Backup database, ghi nhận source/units/timezone của dữ liệu cũ; test trên database tạm.
2. Sửa API index sync và hoàn thiện auth tests; sửa poison-message/DLQ trước ingest lớn.
3. Chọn chính sách reconcile bản ghi company có `data_source_id=NULL`; không tự xóa hay gộp bằng tên trên production.
4. Kiểm tra ngày/key/đơn vị giá và chạy lại cùng batch để chứng minh idempotency. Nếu đã có daily candle 07:00 thì cần kế hoạch reconcile với midnight, không chạy SQL xóa tự động.
5. Với news/events, quyết định append/upsert thay snapshot trước khi muốn lưu đầy đủ lịch sử. Thêm pagination và raw archive để replay.
6. Khóa image/lockfile đã kiểm tra; deploy thủ công staging, quan sát queue/errors/data freshness, rồi mới bật lịch.
