# سامانه هوشمند فراخوان و مسیریابی داوطلبان اهدای خون — MVP

پیاده‌سازی سهم **ثنا (Backend Lead)** از سند تیمی v2.0.
اسرا و شقایق بر پایه همین contract کار می‌کنند؛ فایل‌های سهم آن‌ها ساخته نشده و در
[`docs/decisions/0005-scope-and-handoff.md`](docs/decisions/0005-scope-and-handoff.md) نقطه اتصال دقیق‌شان آمده است.

- قرارداد API (وضعیت اجراشده): [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)
- مدل داده: [`docs/ERD.md`](docs/ERD.md)
- تصمیم‌های فنی و انحراف‌های مستند: [`docs/decisions/`](docs/decisions/)

## ۱. پیش‌نیاز

- Python 3.12+، Docker (برای PostgreSQL و Redis)، و یک پورت آزاد برای Postgres.
- در این ماشین Postgres روی ۵۴۳۲ سرویس لوکال است؛ کانتینر پروژه پورت **۵۴۳۳** را می‌گیرد تا سرویس شما دست‌نخورده بماند.
- اگر سیستم‌تان proxy ویندوزی دارد (مثل `127.0.0.1:10809`)، برای `pip`/`pytest`/`alembic` از `NO_PROXY='*'` استفاده کنید،
  وگرنه درخواست‌های localhost timeout می‌خورند.

## ۲. راه‌اندازی

```bash
cd "D:/Blood Donation/blood-donation-system"

# 1) دیتابیس و Redis
docker compose up -d db redis                 # postgres روی host:5433، redis روی host:6380

# 2) محیط پایتون
cd backend
python -m venv .venv && source .venv/Scripts/activate
NO_PROXY='*' pip install -e ".[dev]"

# 3) تنظیمات (فایل واقعی .env هرگز commit نمی‌شود)
cp ../.env.example .env                       # بعد SECRET_KEY را عوض کنید
# مقدارهای پیش‌فرض برای اجرای روی host ساخته شده‌اند (۵۴۳۳ و ۶۳۸۰)

# 4) مهاجرت و داده نمایشی
NO_PROXY='*' python -m alembic upgrade head
NO_PROXY='*' python -m scripts.seed_demo

# 5) API
NO_PROXY='*' uvicorn app.main:app --reload --port 8000
```

Swagger: `http://localhost:8000/docs` — سلامت: `GET /api/v1/health`.

### Worker و Beat (اختیاری در دمو)

```bash
celery -A app.tasks.celery_app worker --loglevel=INFO --pool=solo -Q notifications,default
celery -A app.tasks.celery_app beat   --loglevel=INFO
```

`--pool=solo` مخصوص ویندوز است؛ API، worker و beat باید هر سه همان broker را ببینند
(`.env.example` به Redis کانتینر روی پورت ۶۳۸۰ اشاره می‌کند).

Beat تسک `check-dispatch-timeout` را هر ۶۰ ثانیه اجرا می‌کند: درخواست‌های گذشته را `expired` می‌کند و
**مرحله بعدی فراخوان را آزاد می‌کند**. اگر Beat خاموش باشد، فقط مرحله اول ارسال می‌شود — این رفتار عمدی است
(تصمیم ۰۰۰۳) و ارسال بی‌رویه مرحله‌های بعدی جایگزین آن نیست.

Redis باید ۶ یا بالاتر باشد. اگر روی ماشین از قبل Redis 5 روی ۶۳۷۹ اجراست، کارگر موقع start با
`Error running script ... ERR syntax error` می‌ایستد — آن اسکریپت Lua خود kombu است، نه کد پروژه؛
همین دلیل پورت ۶۳۸۰ در compose است.

سنجش زنده با `DISPATCH_BATCH_SIZE=1` و `DISPATCH_RESPONSE_WINDOW_MINUTES=1`: مرحله ۱ در لحظه dispatch به
`sent` رسید (mock-000000)، مرحله ۲ در تیک Beat بعدی و مرحله ۳ در تیک پس از آن — سه پیامک، هر کدام با لینک پاسخ.

## ۳. تست

```bash
cd backend
NO_PROXY='*' python -m pytest app/tests -q
```

- تست‌ها روی **PostgreSQL واقعی** (`blood_donation_test` روی پورت ۵۴۳۳) اجرا می‌شوند و
  اسکیمای test را با همان زنجیره مهاجرت Alembic می‌سازند، پس هر اجرای تست `alembic upgrade head` را هم اثبات می‌کند.
- Redis لازم نیست:OTP store درون‌حافظه‌ای و Celery در حالت eager است.
- بررسی drift مدل/مهاجرت: `NO_PROXY='*' python -m alembic check` (باید `No new upgrade operations detected` بدهد).

## ۴. جریان دمو (INT-01)

کد OTP و لینک پاسخ در لاگ چاپ **نمی‌شوند** (بخش ۱۴ سند). در حالت توسعه، mock provider آن‌ها را در
`backend/.dev-outbox.log` می‌نویسد:

```bash
# 1) دریافت کد برای اپراتور مرکز نمونه
curl -s -X POST localhost:8000/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+989120000002","purpose":"login"}'
tail -1 .dev-outbox.log                        # کد شش‌رقمی اینجا است

# 2) تأیید و توکن
curl -s -X POST localhost:8000/api/v1/auth/otp/verify \
  -H 'Content-Type: application/json' \
  -d '{"challenge_id":"<id>","phone":"+989120000002","code":"<code>","purpose":"login"}'

# 3) فعال‌سازی درخواست (این endpoint سهم اسرا است؛ فعلاً در DB)
#    UPDATE blood_requests SET status='active', activated_at=now() WHERE id='<uuid>';

# 4) فراخوان مرحله‌ای
curl -s -X POST localhost:8000/api/v1/blood-requests/<request_id>/dispatch -H "Authorization: Bearer <token>"
curl -s localhost:8000/api/v1/blood-requests/<request_id>/candidates -H "Authorization: Bearer <token>"

# 5) پاسخ داوطلب (لینک امن در پیامک، یا با توکن داوطلب)
curl -s -X POST localhost:8000/api/v1/notifications/<notification_id>/response \
  -H "Authorization: Bearer <donor_token>" -H 'Content-Type: application/json' \
  -d '{"response":"interested","eta_minutes":18}'
```

پیش‌نیاز فعال‌سازی دمو: `COMPATIBILITY_POLICY=demo` و `SMS_PROVIDER=mock` (پیش‌فرض `.env.example`).

## ۵. قوانین سقف‌دار (همه در کد و تست قفل شده‌اند)

- شماره تماس، کد OTP، توکن و مختصات در هیچ لاگی ظاهر نمی‌شوند؛ کد OTP فقط hash می‌شود و از broker رد نمی‌شود.
- پنل مرکز هیچ‌وقت شماره، نام یا مختصات داوطلب نمی‌گیرد؛ فقط `donor_reference` بی‌نام.
- لغو رضایت مکان، رکورد موقعیت را حذف می‌کند.
- هیچ قواعد بالینی ساخته نمی‌شود؛ تطابق نوع، اعلامی و برچسب‌خورده `demo` است.
- فراخوان مرحله‌ای با کلید idempotency؛ پاسخ داوطلب یک‌بارمصرف؛ توقف روی fulfilled/cancelled/expired.

## ۶. ساختار

```
backend/app/core        تنظیمات، امنیت، خطاها، لاگ، dependencyها
backend/app/db/models   مدل‌ها + ماشین‌وضعیت‌ها (Alembic autogenerate از همین‌جا)
backend/app/schemas     پوشش {data,meta} و shapes بخش ۹
backend/app/services    OTP، Matching، Dispatch، پیامک، نقشه، audit، donor
backend/app/tasks       Celery worker/beat
backend/app/api/v1      endpointهای ثنا + بلاک ثبت routerهای اسرا
backend/scripts         seed_demo.py (داده نمایشی)
```

## ۷. گیت (بخش ۱۶ سند)

- `main` نسخه پایدار، `develop` محل یکپارچه‌سازی — **اسرا و شقایق از `develop` شاخه می‌زنند**.
- کار هر نفر روی `feature/<name>` و merge با `--no-ff` به `develop`.
- پیام commitها Conventional Commits است: `feat|fix|test|docs|chore(scope): چرا این تغییر`.
- remote تنظیم نشده و چیزی push نشده؛ `.env`، `.dev-outbox.log` و فایل‌های runtime Celery در
  `.gitignore` هستند و فقط `.env.example` با placeholder commit می‌شود.
