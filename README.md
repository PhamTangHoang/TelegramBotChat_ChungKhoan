# VN Stock Analyst Bot

Bot Telegram phân tích kỹ thuật cổ phiếu Việt Nam. Bot lấy dữ liệu OHLCV, tính
chỉ báo tất định, chấm điểm Rule Engine và PP10Ulti, lưu đầu vào để audit, sau
đó có thể dùng Gemini để giải thích kết quả.

Rule Engine là nguồn duy nhất quyết định signal, score và risk. Gemini chỉ là
lớp giải thích, không được thay đổi tín hiệu. Tin tức là module riêng và không
được cộng vào điểm PP10Ulti.

> Đây là công cụ tham khảo/kỹ thuật, không phải dịch vụ tư vấn đầu tư. Điểm số
> không phải xác suất dự đoán.

## Bắt đầu nhanh bằng Docker

### Yêu cầu

- Docker Desktop hoặc Docker Engine có Docker Compose.
- Telegram bot token nếu muốn chạy bot Telegram.
- Gemini API key là tùy chọn; bot vẫn phân tích kỹ thuật khi không có key.
- Kết nối Internet để lấy dữ liệu thị trường, RSS và Gemini.

### Cài đặt

~~~powershell
Copy-Item .env.example .env
~~~

Mở file .env và bổ sung các biến cần thiết, tối thiểu khi chạy Telegram:

~~~dotenv
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_PUBLIC_ACCESS=true
GEMINI_API_KEY=your_gemini_api_key
NEWS_FEED_URLS=https://cafef.vn/thi-truong-chung-khoan.rss,https://thanhnien.vn/rss/kinh-te/chung-khoan.rss
NEWS_ALLOWED_DOMAINS=cafef.vn,thanhnien.vn
~~~

Không commit .env, không gửi token Telegram hoặc API key vào chat/log.

Khởi động app và database:

~~~powershell
docker compose up -d --build
docker compose exec app alembic upgrade head
~~~

Kiểm tra service:

~~~powershell
(Invoke-WebRequest -UseBasicParsing http://localhost:8000/health).Content
~~~

Kết quả đúng:

~~~json
{"status":"ok"}
~~~

Xem log:

~~~powershell
docker compose logs -f app
~~~

Tắt app nhưng giữ database:

~~~powershell
docker compose down
~~~

Lệnh docker compose down -v sẽ xóa volume PostgreSQL và toàn bộ dữ liệu đã
lưu; chỉ dùng khi muốn reset database.

## Cấu hình .env

### Telegram và quyền truy cập

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| TELEGRAM_BOT_TOKEN | Có khi chạy bot | rỗng | Token lấy từ BotFather. Rỗng thì app chỉ chạy health API. |
| TELEGRAM_PUBLIC_ACCESS | Không | false | true cho phép mọi chat dùng bot; false chỉ cho các ID trong whitelist. |
| TELEGRAM_ALLOWED_CHAT_IDS | Khi public access tắt | rỗng | Danh sách chat ID, cách nhau bằng dấu phẩy, ví dụ 123456789,-1001234567890. |
| TELEGRAM_RATE_LIMIT_PER_MIN | Không | 5 | Số yêu cầu tối đa mỗi chat trong một phút. |

BotFather dùng để tạo bot và lấy token. Khi test nhanh có thể bật
TELEGRAM_PUBLIC_ACCESS=true; khi dùng riêng nên để false và khai báo chat ID
cụ thể.

### Dữ liệu thị trường

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| DATABASE_URL | PostgreSQL trong Compose | Chuỗi kết nối SQLAlchemy. Nếu đổi POSTGRES_* thì phải cập nhật cho khớp. |
| VNSTOCK_SOURCE | kbs | Nguồn vnstock, chỉ nhận kbs hoặc vci. |
| WATCHLIST_SYMBOLS | FPT,VNM,HPG | Các mã được scheduler cập nhật định kỳ. |
| WATCHLIST_EXCHANGES | HOSE,HOSE,HOSE | Sàn tương ứng theo đúng thứ tự với WATCHLIST_SYMBOLS. |
| DATA_CACHE_MAX_AGE_MINUTES | 60 | Tuổi tối đa của dữ liệu cache trước khi xem là cũ. |
| ALLOW_STALE_SIGNAL | false | Có cho phép dùng dữ liệu cũ để tạo tín hiệu hay không. Nên giữ false. |
| CALENDAR_VERSION | HOSE_2026 | Lịch giao dịch được dùng để xác định phiên regular. |
| TELEGRAM_TIMEZONE | Asia/Ho_Chi_Minh | Múi giờ hiển thị và scheduler. |

Giá cổ phiếu từ vnstock được xử lý nội bộ theo đơn vị nghìn VND. Khi gửi
Telegram, bot quy đổi thành dạng dễ đọc như 22.250 VND/cổ phiếu. VN-Index vẫn
hiển thị theo điểm chỉ số, không phải VND.

### Gemini

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| GEMINI_API_KEY | Không | rỗng | Key của Gemini. Không có key thì bỏ qua phần giải thích Gemini. |
| GEMINI_MODEL | Không | gemini-3.1-flash-lite | Model dùng để giải thích structured JSON. |
| GEMINI_TIMEOUT_SECONDS | Không | 20 | Timeout HTTP cho Gemini; không đặt dưới 10 giây. |

Gemini không tính lại chỉ báo, không sửa score/signal/risk và không tự biến dữ
liệu thiếu thành tín hiệu. Nếu Gemini lỗi, technical report vẫn được lưu và
trả về không có phần giải thích Gemini.

### Tin tức RSS

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| NEWS_FEED_URLS | rỗng | Danh sách URL RSS, cách nhau bằng dấu phẩy. Phải là RSS feed, không phải link bài đơn lẻ. |
| NEWS_LOOKBACK_HOURS | 24 | Chỉ lấy tin trong số giờ gần nhất. |
| NEWS_MAX_ITEMS | 10 | Số bài tối đa hiển thị. |
| NEWS_ALLOWED_DOMAINS | rỗng | Domain được phép; rỗng nghĩa là chấp nhận mọi domain HTTP/HTTPS hợp lệ. |
| NEWS_JOB_INTERVAL_MINUTES | 45 | Chu kỳ scheduler refresh RSS. |

News hiển thị tiêu đề, nguồn, thời gian đăng, thời gian bot lấy, tóm tắt và link
bài gốc. /news SYMBOL lọc theo mã xuất hiện trong tiêu đề hoặc tóm tắt; nếu bài
chỉ viết tên doanh nghiệp mà không có ticker thì có thể không được nhận diện.
RSS là dữ liệu tổng hợp, bot không xác minh độc lập nội dung bài viết.

### Scheduler, chỉ báo và phiên bản

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| MARKET_JOB_INTERVAL_MINUTES | 60 | Chu kỳ cập nhật watchlist trong giờ giao dịch. |
| EOD_SETTLE_JOB_TIME | 15:20 | Thời điểm chạy phân tích final cuối ngày. |
| VOLUME_LOOKBACK_DAYS | 20 | Số phiên dùng cho các tính toán volume. |
| VOLUME_RATIO_THRESHOLD | 1.5 | Ngưỡng volume ratio của Rule Engine. |
| VOLUME_MIN_ELAPSED_MINUTES | 15 | Số phút tối thiểu trước khi đánh giá volume trong phiên. |
| RS_LOOKBACK_DAYS | 20 | Khoảng nhìn lại cho relative performance. |
| RULE_VERSION | 1.5.0 | Phiên bản Rule Engine. |
| PP10_VERSION | 1.1.0 | Phiên bản bộ chấm PP10Ulti. |
| PROMPT_VERSION | 1.1.0 | Phiên bản prompt Gemini. |
| DATA_SCHEMA_VERSION | 1.0.0 | Phiên bản snapshot/audit. |
| LOG_LEVEL | INFO | Mức log: DEBUG, INFO, WARNING, ERROR hoặc CRITICAL. |

PostgreSQL Compose còn nhận POSTGRES_DB, POSTGRES_USER và POSTGRES_PASSWORD.
Nếu không khai báo, các giá trị mặc định chỉ phù hợp cho local; khi deploy nên
đặt mật khẩu riêng trong .env.

## Sử dụng trên Telegram

Các lệnh public:

| Lệnh | Tác dụng |
| --- | --- |
| /start | Khởi động và xem hướng dẫn nhanh. |
| /help | Xem toàn bộ lệnh. |
| /analyze FPT | Technical Analysis + Rule Engine + PP10Ulti + Gemini nếu có. |
| /chart FPT | Tạo và gửi biểu đồ kỹ thuật. |
| /news FPT | Xem tin liên quan đến FPT, kèm link bài gốc. |
| /news | Xem tin thị trường chung. |
| /market | Xem trạng thái phiên HOSE và snapshot VN-Index. |

/pt là lệnh cũ và không còn là lệnh public; dùng /analyze cho mọi phân tích
cổ phiếu.

Bot cũng nhận một số câu tự nhiên:

~~~text
phân tích FPT
vẽ biểu đồ VNM
tin tức ACB
thị trường hôm nay thế nào
xin chào
~~~

Tin nhắn hội thoại thông thường được chuyển cho Gemini khi có GEMINI_API_KEY.
Nếu không có key, bot trả thông báo chưa thể trả lời hội thoại; các lệnh kỹ
thuật vẫn hoạt động.

## Nội dung báo cáo /analyze

Một báo cáo gồm các phần chính:

1. Price, trạng thái dữ liệu, phiên FINAL hoặc NOT FINAL.
2. TREND: các rule về giá và MA20/MA50.
3. MOMENTUM: RSI14, MACD Histogram và ATR14.
4. VOLUME: volume ratio và thời gian đã trôi qua trong phiên.
5. RELATIVE STRENGTH: relative performance so với VN-Index.
6. RULE ENGINE: score, signal và risk chính thức.
7. PP10ULTI: chấm từng tiêu chí, tổng điểm, grade, confidence và lý do thiếu dữ liệu.
8. POSITION PLAN: vùng mua tham chiếu, vùng gia tăng, stop-loss, mục tiêu và R:R.
9. GEMINI ANALYSIS: chỉ xuất hiện khi Gemini trả về hợp lệ.

### PP10Ulti

PP10 chấm các nhóm tiêu chí xu hướng MA, Wyckoff heuristic, mẫu hình, pattern
quality, volume, VPVR xấp xỉ, CPR, OBV/CMF, MACD, RSI/ADX, Stochastic RSI,
fundamental, valuation, thị trường chung và quản trị vị thế.

Tiêu chí chỉ được cộng vào mẫu số khi dữ liệu đã đủ. Những phần chưa có nguồn
đáng tin cậy sẽ hiện DATA_UNAVAILABLE, không bị đoán giả và không làm sai điểm.
Đặc biệt, RS Rating toàn universe và so sánh P/E/P/B ngành/lịch sử cần provider
chuyên biệt; hiện có thể chưa đánh giá được.

### News không nằm trong điểm

News được gọi riêng bằng /news, không được đưa vào score PP10Ulti. Điều này giúp
phân biệt rõ:

- Phân tích định lượng: OHLCV, chỉ báo, Rule Engine và PP10Ulti.
- Thông tin sự kiện: tiêu đề/tóm tắt RSS và link bài gốc.
- Gemini: giải thích các dữ liệu đã có, không dùng tin chưa được truyền vào
  report để tự suy diễn.

## Chạy test và phát triển

### Test bằng Docker

~~~powershell
docker compose exec app python -m pytest -q
docker compose exec app ruff check .
~~~

Test không cần gọi API thật. Có test unit cho indicator, Rule Engine, PP10Ulti,
RSS, Gemini parser, Telegram formatter và test integration cho database/pipeline.

### Chạy trực tiếp trên máy

Docker là cách khuyến nghị vì đã bao gồm PostgreSQL. Nếu muốn chạy Python trực
tiếp, vẫn cần một PostgreSQL đang chạy và DATABASE_URL hợp lệ.

~~~powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

Chạy kiểm tra local:

~~~powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q app tests
~~~

### Các lệnh Docker hữu ích

~~~powershell
docker compose ps
docker compose logs --tail=200 app
docker compose restart app
docker compose up -d --build
~~~

Sau khi sửa .env, dùng docker compose up -d để nạp lại biến môi trường; sau khi
sửa source, dùng docker compose up -d --build để build image mới.

## Deploy miễn phí lên Oracle Cloud

Với kiến trúc hiện tại, Oracle Cloud Always Free VM phù hợp hơn nền tảng web free
có cơ chế sleep: bot dùng Telegram long polling, scheduler cần process chạy
liên tục và PostgreSQL cần volume bền vững.

Cấu hình nên dùng:

~~~text
VM.Standard.A1.Flex
2 OCPU
8–12 GB RAM
Ubuntu
Docker Compose
~~~

Oracle có giới hạn tài nguyên và có thể hết capacity ở home region. Tài khoản
thường cần xác minh điện thoại/thẻ; kiểm tra điều kiện hiện hành tại [Oracle
Cloud Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Quy trình tổng quát trên VM:

~~~bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker

# Đưa source project lên VM bằng git clone hoặc SCP, sau đó đi vào thư mục project:
cd TelegramChungKhoan
cp .env.example .env
nano .env

docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose ps
~~~

Bot đang dùng polling nên không cần mở public port cho Telegram; chỉ cần VM có
outbound Internet. Giữ SSH firewall giới hạn theo IP của bạn. Port 8000 chỉ cần
public nếu muốn truy cập health endpoint từ bên ngoài.

Trước khi bảo trì hoặc xóa VM, backup database:

~~~bash
docker compose exec -T postgres pg_dump -U postgres -d vn_stock > backup.sql
~~~

Không dùng Render Free cho bot chạy 24/7: free web service có thể sleep khi
không có inbound traffic và database free có thời hạn. Render phù hợp hơn cho
demo ngắn hạn hoặc khi đổi kiến trúc sang webhook/database bên ngoài.

## Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| /start trả Yêu cầu bị từ chối | Đang whitelist nhưng chat ID chưa được khai báo. | Test bằng TELEGRAM_PUBLIC_ACCESS=true, hoặc thêm ID vào TELEGRAM_ALLOWED_CHAT_IDS, rồi docker compose up -d. |
| Bot không phản hồi tin nhắn thường | Không có GEMINI_API_KEY hoặc Gemini lỗi. | Dùng các lệnh kỹ thuật; xem docker compose logs -f app. |
| Gemini 400 deadline too short | Timeout thấp hơn giới hạn API. | Đặt GEMINI_TIMEOUT_SECONDS=20 hoặc cao hơn. |
| Gemini 504 DEADLINE_EXCEEDED | Model quá chậm hoặc API tạm thời quá tải. | Dùng gemini-3.1-flash-lite, timeout 20, rebuild container; technical report vẫn được trả nếu Gemini thất bại. |
| /news ACB rỗng | Feed chưa cấu hình, bài nằm ngoài lookback, hoặc bài không nhắc chính xác ticker. | Kiểm tra NEWS_FEED_URLS, NEWS_LOOKBACK_HOURS và log RSS; /news dùng để xem tin chung. |
| News có tiêu đề nhưng không có bài liên quan | Đang gọi /news nên bot trả tin thị trường chung. | Gọi /news SYMBOL, ví dụ /news FPT. |
| /market báo không ở regular trading session | Gọi ngoài giờ HOSE. | Giờ regular mặc định: 09:00–11:30 và 13:00–14:45; ngày nghỉ vẫn không có phiên. |
| Một số PP10 hiện DATA_UNAVAILABLE | Provider chưa cung cấp dữ liệu chuyên biệt hoặc chưa đủ lịch sử. | Đây là trạng thái an toàn; không tự thay bằng giá trị ước đoán. |
| /analyze chạy lâu | vnstock, chart hoặc Gemini là các boundary bên ngoài. | Xem log thời lượng; Gemini có timeout riêng, technical result vẫn được bảo toàn khi Gemini lỗi. |
| Mã cổ phiếu không có dữ liệu | Provider không trả OHLCV hợp lệ hoặc mã/sàn chưa được hỗ trợ. | Thử FPT, ACB, REE hoặc VCB; xem log provider. |

## Cấu trúc project

~~~text
app/
├── analysis/       # Indicator, Rule Engine, PP10 và heuristic cấu trúc giá
├── audit/          # Snapshot đầu vào và kết quả để tái dựng
├── chart/          # Render biểu đồ PNG
├── config/         # Settings đọc từ .env
├── data/providers/ # vnstock, fundamentals và RSS adapters
├── database/       # SQLAlchemy models, connection và repositories
├── domain/         # Enum và Pydantic schemas
├── llm/            # Gemini client, prompt và schema
├── market/         # Lịch giao dịch HOSE
├── scheduler/      # Job market, news và EOD settle
├── services/       # AnalysisService và NewsService
└── telegram/       # Commands, handlers, access control và formatter

alembic/            # Database migrations
tests/              # Unit và integration tests
docker-compose.yml  # App + PostgreSQL
Dockerfile          # Image production
.env.example        # Mẫu cấu hình, không chứa secret
~~~

## Tài liệu liên quan

- [Implementation specification](docs/SPEC.md): ranh giới dữ liệu, signal,
  audit và các tiêu chí nghiệm thu.
- [Implementation notes](IMPLEMENTATION_NOTES.md): các quyết định đã triển khai.
- [ADR-001: stack and boundaries](docs/decisions/ADR-001-stack-and-boundaries.md).
- [ADR-002: Telegram public access](docs/decisions/ADR-002-telegram-public-access.md).

## Giới hạn và trách nhiệm

- Dữ liệu market/news/Gemini đến từ dịch vụ bên ngoài và có thể lỗi, trễ hoặc
  thay đổi schema.
- Báo cáo không phải khuyến nghị mua, bán hoặc nắm giữ.
- Không đặt secret vào source code, README, test fixture hoặc commit.
- Khi thay đổi công thức, prompt hoặc schema, phải cập nhật version tương ứng và
  chạy lại toàn bộ test suite.
