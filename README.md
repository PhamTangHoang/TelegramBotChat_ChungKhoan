# VN Stock Analyst Bot

Bot Telegram hỗ trợ báo cáo PP10Ulti 2.0 bằng AI theo prompt mẫu. Lệnh
`/analyze SYMBOL` lấy OHLCV cơ bản rồi gửi trực tiếp cho AI, không cào dữ liệu
phân tích chuyên biệt;
`/chart`, `/market` và `/news` là các tính năng dữ liệu riêng.

Luồng `/analyze` là AI-generated từ OHLCV. Điểm, xếp hạng, vùng giá và kịch bản
trong báo cáo là nhận định tham khảo của AI; các mục ngoài OHLCV không được
xem là số liệu đã xác minh hay khuyến nghị đầu tư. Tin tức là module riêng.

> Đây là công cụ tham khảo/kỹ thuật, không phải dịch vụ tư vấn đầu tư. Điểm số
> không phải xác suất dự đoán.

## Bắt đầu nhanh bằng Docker

### Yêu cầu

- Docker Desktop hoặc Docker Engine có Docker Compose.
- Telegram bot token nếu muốn chạy bot Telegram.
- Cần ít nhất một trong `GEMINI_API_KEY` hoặc `OPENROUTER_API_KEY` cho `/analyze`.
- Kết nối Internet để lấy OHLCV, gọi Gemini/OpenRouter, `/chart`, `/market` và RSS.

### Cài đặt

~~~powershell
Copy-Item .env.example .env
~~~

Mở file .env và bổ sung các biến cần thiết, tối thiểu khi chạy Telegram:

~~~dotenv
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_PUBLIC_ACCESS=true
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_PROVIDER=hybrid
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
| GEMINI_API_KEY | Có cho /analyze | rỗng | Key của Gemini để tạo báo cáo AI và chat tự nhiên. |
| GEMINI_MODEL | Không | gemini-3.1-flash-lite | Model dùng để tạo báo cáo PP10 structured JSON. |
| GEMINI_TIMEOUT_SECONDS | Không | 20 | Timeout HTTP cho Gemini; không đặt dưới 10 giây. |

Lệnh `/analyze` lấy OHLCV một lần rồi gửi dữ liệu đó cho provider AI. Khi dùng
OpenRouter, ba analyst chạy song song và một Judge tổng hợp; khi dùng Gemini chỉ
có một lượt tạo báo cáo. Luồng này không gọi fundamentals, VN-Index, RSS hoặc
chart. Prompt yêu cầu AI không bịa giá/chỉ báo ngoài dữ liệu OHLCV, tin tức, link hay vùng giá;
phần thiếu dữ liệu phải ghi rõ. Điểm số và nhận định vẫn là nội dung AI tạo để
tham khảo, không phải signal đã xác minh.

### OpenRouter và hội đồng AI

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| LLM_PROVIDER | Không | hybrid | `gemini`, `openrouter` hoặc `hybrid`. `hybrid` ưu tiên hội đồng OpenRouter và fallback Gemini. |
| OPENROUTER_API_KEY | Có nếu dùng OpenRouter | rỗng | API key tạo tại OpenRouter. |
| OPENROUTER_ANALYST_MODELS | Không | `openrouter/free` x 3 | Ba model analyst; nên khai báo 3 model khác nhau nếu muốn tranh luận đa dạng. |
| OPENROUTER_JUDGE_MODEL | Không | `openrouter/free` | Model Judge dự phòng khi không có Gemini Judge. |
| OPENROUTER_FALLBACK_MODELS | Không | rỗng | Các model dự phòng cho lượt Judge, cách nhau bằng dấu phẩy. |
| OPENROUTER_TIMEOUT_SECONDS | Không | 45 | Timeout cho từng request OpenRouter. |
| OPENROUTER_MAX_PARALLEL | Không | 3 | Số analyst chạy song song, tối đa 3. |
| OPENROUTER_DATA_COLLECTION | Không | deny | Chính sách dữ liệu gửi tới provider; `deny` ưu tiên riêng tư hơn. |

Khi chạy `/analyze` với `LLM_PROVIDER=hybrid` và có cả hai API key, ba analyst
OpenRouter được gọi song song theo các vai trò kỹ thuật, cấu trúc/mẫu hình và
rủi ro/phản biện. Gemini nhận các bản nháp đó làm Judge, đối chiếu với OHLCV rồi
trả đúng schema PP10Ulti 2.0. Như vậy mỗi lượt dùng 3 request OpenRouter và 1
request Gemini. Các analyst thất bại vẫn được bỏ qua nếu còn ít nhất một bản nháp;
nếu OpenRouter analyst lỗi hoàn toàn thì bot fallback sang báo cáo Gemini trực tiếp.

Nếu không có `GEMINI_API_KEY`, OpenRouter sẽ tự dùng `OPENROUTER_JUDGE_MODEL` làm
Judge. Nếu không có `OPENROUTER_API_KEY`, luồng hybrid dùng Gemini trực tiếp.

OpenRouter dùng endpoint tương thích OpenAI và structured JSON cho báo cáo. Với
`openrouter/free`, model thực tế có thể thay đổi theo availability và giới hạn
của tài khoản; muốn kết quả ổn định hơn hãy khai báo model ID cụ thể trong
`OPENROUTER_ANALYST_MODELS` và `OPENROUTER_JUDGE_MODEL`.

Ứng dụng giới hạn lượt analyst ở 1.200 token và báo cáo PP10 ở 6.000 token để
tránh response bị kéo dài vô hạn. Nếu báo cáo JSON vi phạm schema hoặc vượt trần
điểm từng tiêu chí, bot sẽ tự gửi một lượt yêu cầu sửa toàn bộ JSON; nếu vẫn lỗi,
log sẽ ghi rõ provider, mã HTTP và nguyên nhân để dễ kiểm tra trên Render.

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
| PP10_VERSION | 2.0.0 | Phiên bản bộ chấm và format báo cáo PP10Ulti. |
| PROMPT_VERSION | 2.0.0 | Phiên bản prompt báo cáo PP10 AI. |
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
| /analyze FPT | Lấy OHLCV cơ bản và nhờ AI hoặc hội đồng OpenRouter tạo báo cáo PP10Ulti. |
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

Một báo cáo PP10Ulti 2.0 do AI tạo gồm các phần chính:

1. Giá OHLCV mới nhất, thời điểm tạo và trạng thái nguồn dữ liệu.
2. Điểm AI tham khảo, xếp hạng, mức độ tin cậy và kết luận sơ bộ.
3. Chi tiết từng tiêu chí theo nhóm kỹ thuật, dòng tiền, động lượng, cơ bản,
   định giá/vĩ mô và quản trị vị thế.
4. Kế hoạch hành động tham khảo với ba kịch bản, vùng giá, stop-loss, mục tiêu
   và R:R.
5. Kết luận và lưu ý rằng AI chỉ nhận OHLCV cùng các dữ liệu được cung cấp.

### PP10Ulti

Prompt PP10 yêu cầu AI nhận xét các nhóm xu hướng MA, Wyckoff, mẫu hình,
volume, VPVR, CPR, OBV/CMF, MACD, RSI/ADX, Stochastic RSI, cơ bản, định giá,
thị trường chung và quản trị vị thế.

Do `/analyze` chỉ truyền OHLCV, prompt yêu cầu các tiêu chí ngoài nguồn này hiển
thị “chưa có dữ liệu” hoặc “AI suy luận”. Điểm số không phải điểm định lượng đã
xác minh.

### News không nằm trong điểm

News được gọi riêng bằng /news, không được đưa vào score PP10Ulti. Điều này giúp
phân biệt rõ:

- Báo cáo AI: nội dung do Gemini hoặc OpenRouter tạo từ OHLCV, không dùng news để chấm điểm.
- Thông tin sự kiện: tiêu đề/tóm tắt RSS và link bài gốc.
- AI không được dùng tin tức vì news vẫn là module `/news` riêng.

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
| Bot không phản hồi tin nhắn thường | Không có GEMINI_API_KEY hoặc Gemini lỗi; OpenRouter hiện chỉ dùng cho `/analyze`. | Dùng các lệnh kỹ thuật; xem docker compose logs -f app. |
| Gemini 400 deadline too short | Timeout thấp hơn giới hạn API. | Đặt GEMINI_TIMEOUT_SECONDS=20 hoặc cao hơn. |
| Gemini 504 DEADLINE_EXCEEDED | Model quá chậm hoặc API tạm thời quá tải. | Dùng gemini-3.1-flash-lite, timeout 20, rebuild container; technical report vẫn được trả nếu Gemini thất bại. |
| /news ACB rỗng | Feed chưa cấu hình, bài nằm ngoài lookback, hoặc bài không nhắc chính xác ticker. | Kiểm tra NEWS_FEED_URLS, NEWS_LOOKBACK_HOURS và log RSS; /news dùng để xem tin chung. |
| News có tiêu đề nhưng không có bài liên quan | Đang gọi /news nên bot trả tin thị trường chung. | Gọi /news SYMBOL, ví dụ /news FPT. |
| /market báo không ở regular trading session | Gọi ngoài giờ HOSE. | Giờ regular mặc định: 09:00–11:30 và 13:00–14:45; ngày nghỉ vẫn không có phiên. |
| Một số PP10 hiện DATA_UNAVAILABLE | Provider chưa cung cấp dữ liệu chuyên biệt hoặc chưa đủ lịch sử. | Đây là trạng thái an toàn; không tự thay bằng giá trị ước đoán. |
| /analyze chạy lâu | OpenRouter đang chạy analyst song song rồi chờ Judge, hoặc instance đang khởi động. | Xem các log `AI-only OHLCV ready`, `OpenRouter request completed`, `Gemini PP10 request completed`; giảm số analyst nếu cần. |
| /analyze trả AI chưa trả báo cáo | Provider trả JSON sai schema, hết quota/rate limit hoặc request timeout. | Xem log `AI-only PP10 analysis failed`; log mới có model, mã HTTP, thời gian và lý do provider. |
| Bot báo mã không có dữ liệu sau khi nhập câu tự nhiên | Câu có thể chứa từ như “cho”, “cổ phiếu”, “mã”; parser cũ có thể lấy nhầm một từ làm ticker. | Dùng dạng `/analyze REE` hoặc “phân tích mã REE”; parser hiện ưu tiên mã sau nhãn `mã`/`cổ phiếu` và preflight mã lạ. |
| /analyze báo thiếu API key | Chưa có provider AI khả dụng. | Bổ sung `GEMINI_API_KEY` hoặc `OPENROUTER_API_KEY`; dùng `/chart`, `/market` hoặc `/news` cho tính năng dữ liệu riêng. |

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
├── llm/            # Gemini/OpenRouter clients, debate prompt và schema
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
