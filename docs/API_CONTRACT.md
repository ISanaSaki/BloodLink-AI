# قرارداد API — نسخه اجرایی (هم‌راستا با سند v2.0)

این سند وضعیت **کدنویسی‌شده** API را ثبت می‌کند. تا زمانی که Change Log تصمیم جدیدی نیاورد،
هر تغییر در نام مسیر، نام فیلد یا مقدار enum باید هم‌زمان در این سند، در کد و در تست‌ها اعمال شود.

مالک سند: ثنا (Backend Lead). مشارکت: اسرا، شقایق (بخش ۴ سند تیمی).

## ۰. وضعیت پیاده‌سازی

| محدوده | وضعیت | مالک |
| --- | --- | --- |
| `auth`، `users/me`، `donors/me/profile`، `donors/me/location` | پیاده‌سازی و تست‌شده | ثنا |
| `dispatch`، `candidates`، `notifications`، پاسخ داوطلب | پیاده‌سازی و تست‌شده | ثنا |
| `centers`، `blood-requests` (CRUD/activate/cancel/responses)، `donors/me/availability` | **در انتظار پیاده‌سازی** (قرارداد همان بخش ۹ سند اصلی است) | اسرا |
| `frontend/**` | در انتظار پیاده‌سازی | شقایق |

فایل `backend/app/api/v1/router.py` محل دقیق ثبت routerهای اسرا را با کامنت نشان می‌دهد؛ آن سه خط را
بدون تغییر در فایل‌های دیگر باز کنید تا تضاد Git ایجاد نشود (بخش ۱۶.۲ سند تیمی).

## ۱. قواعد مشترک (بدون استثنا)

- Base URL توسعه: `http://localhost:8000`؛ همه مسیرها زیر `PREFIX` یعنی `/api/v1`.
- احراز هویت: `Authorization: Bearer <access_token>`؛ فقط `/auth/otp/*` و `/health` عمومی‌اند.
- پاسخ موفق: `{ "data": ..., "meta": { "request_id": "uuid", "page"?: int, "page_size"?: int, "total"?: int } }`
- پاسخ خطا: `{ "error": { "code", "message", "request_id", "details"?: [{ "field", "message" }] } }`
- `X-Request-Id`: اگر کلاینت بفرستد، همان مقدار در `meta.request_id`، `error.request_id` و هدر پاسخ برمی‌گردد؛
  اگر نفرستد، سرور یکی می‌سازد. برای گزارش خطا همین هدر را در اسکرین‌شات/تیکت بیاورید.
- نام فیلدها دقیقاً `snake_case`؛ زمان‌ها ISO-8601 UTC با پسوند `Z`؛ تاریخ بدون ساعت `YYYY-MM-DD`.
- enum‌ها با حرف کوچک و underscore (مثلاً `awaiting` وجود ندارد؛ `available` / `queued` / `red_cells`).
- Pagination: `page` از ۱، `page_size` پیش‌فرض ۲۰ و حداکثر ۱۰۰؛ `page_size=101` → `422`.
- بدنه‌های `PATCH` روی `extra="forbid"` هستند: فیلد ناشناخته → `422` (نه نادیده‌گرفته‌شدن).

کدهای خطا (بخش ۷.۲): `INVALID_REQUEST` 400، `UNAUTHENTICATED` 401، `FORBIDDEN` 403،
`RESOURCE_NOT_FOUND` 404، `CONFLICT` 409، `VALIDATION_ERROR` 422، `RATE_LIMITED` 429، `INTERNAL_ERROR` 500.
بدنه ۵۰ هرگز جزئیات داخلی/stack trace را نشان نمی‌دهد؛ فقط `request_id` برای تطبیق با لاگ.

## ۲. Auth

### `POST /api/v1/auth/otp/request` — عمومی → 202

```json
{ "phone": "+989121234567", "purpose": "register" }
```

```json
{ "data": { "challenge_id": "uuid", "expires_in_seconds": 120, "resend_after_seconds": 60 },
  "meta": { "request_id": "uuid" } }
```

- `purpose` فقط `register` یا `login`؛ شماره باید E.164 باشد (`PHONE_PATTERN` در `app/schemas/common.py`).
- ارسال مجدد زودهنگام → `429 RATE_LIMITED` با هدر `Retry-After`.
- سقف پنجره‌ای: `OTP_MAX_REQUESTS_PER_PHONE` / `OTP_MAX_REQUESTS_PER_IP` (تصمیم ۰۰۰۲).
- خود OTP فقط به‌صورت HMAC ذخیره می‌شود؛ در هیچ پاسخ یا لاگی ظاهر نمی‌شود.

### `POST /api/v1/auth/otp/verify` — عمومی → 200

```json
{ "challenge_id": "uuid", "phone": "+989121234567", "code": "123456", "purpose": "register" }
```

```json
{ "data": { "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600,
            "user": { "id": "uuid", "phone": "+989121234567", "role": "donor", "is_profile_complete": false } },
  "meta": { "request_id": "uuid" } }
```

- `code` دقیقاً ۶ رقم؛ کد اشتباه/منقضی → `401 UNAUTHENTICATED`. پس از `OTP_MAX_ATTEMPTS` (پیش‌فرض ۵) تلاش ناموفق،
  چالش قفل و پاسخ `429 RATE_LIMITED` است؛ برای ادامه، کد جدید بگیرید.
- `purpose=login` برای شماره‌ای که کاربر فعال ندارد → `404 RESOURCE_NOT_FOUND`.
- کاربر غیرفعال → `401 UNAUTHENTICATED`. چالش یک‌بارمصرف است؛ verify دوم روی همان چالش موفق نمی‌شود.
- نقش کاربر جدید همیشه `donor` است؛ نقش‌های دیگر را فقط admin می‌سازد.

## ۳. کاربر جاری

### `GET /api/v1/users/me` — هر نقش → 200

```json
{ "data": { "id": "uuid", "phone": "+989121234567", "role": "donor",
            "is_active": true, "is_profile_complete": true },
  "meta": { "request_id": "uuid" } }
```

`is_profile_complete` یعنی گروه خونی + Rh ثبت شده باشد (فقط برای نقش `donor`؛ برای بقیه `false` نیست مگر پروفایل داوطلب داشته باشند).

## ۴. خودخدمات داوطلب

### `PATCH /api/v1/donors/me/profile` — نقش `donor` → 200

```json
{ "blood_group": "O", "rh_factor": "positive", "last_donation_date": "2026-05-10",
  "sms_consent": true, "location_consent": true }
```

```json
{ "data": { "donor_id": "uuid", "blood_group": "O", "rh_factor": "positive",
            "blood_type_verified": false, "last_donation_date": "2026-05-10",
            "sms_consent": true, "location_consent": true },
  "meta": { "request_id": "uuid" } }
```

- `blood_type_verified` در ورودی وجود ندارد؛ ارسال آن → `422` (بخش ۹.۴ سند).
- بدنه خالی (`{}`) → `422`.
- لغو `location_consent` باعث **حذف** رکورد موقعیت می‌شود (نه فقط غیرفعال‌سازی).
- تغییرات در `audit_logs` با نام فیلدها ثبت می‌شود، بدون مقدار حساس.

### `PATCH /api/v1/donors/me/location` — نقش `donor` با `location_consent=true` → 200

```json
{ "latitude": 35.7050, "longitude": 51.4050 }
```

```json
{ "data": { "donor_id": "uuid", "latitude": 35.7050, "longitude": 51.4050,
            "updated_at": "2026-11-04T10:30:00Z", "location_consent": true },
  "meta": { "request_id": "uuid" } }
```

- بدون رضایت → `403 FORBIDDEN`. مختصات خارج از بازه → `422`.
- مختصات هیچ‌وقت در لاگ، پاسخ‌های دیگر کاربران یا `/candidates` ظاهر نمی‌شود.

### `PATCH /api/v1/donors/me/availability` — نقش `donor` (اسرا)

قرارداد بخش ۹.۵ بدون تغییر: `{ "status": "available", "available_from": "...Z", "available_until": "...Z" }`
و پاسخ `{ donor_id, status, available_from, available_until, updated_at }`.
مدل `DonorAvailability` و قید `window_is_ordered` آماده است؛ فقط endpoint و schema آن باقی مانده.
نکته: Matching این جدول را می‌خواند؛ اگر `status` یا بازه زمانی را تغییر می‌دهید،
`app/services/matching_service.py::_candidate_query` را با تست بازبینی کنید.

## ۵. فراخوان (Dispatch)

### `POST /api/v1/blood-requests/{request_id}/dispatch` — `center_operator` مالک یا `admin` → 202

بدنه ندارد.

```json
{ "data": { "dispatch_id": "uuid", "request_id": "uuid", "status": "queued",
            "candidate_count": 3, "first_batch_size": 3 },
  "meta": { "request_id": "uuid" } }
```

- فقط درخواست `active` و مرکز تأییدشده/فعال؛ در غیر این صورت `403` (مرکز تأییدنشده) یا `409` (وضعیت/کاندیدای-empty).
- درخواست از قبل منقضی‌شده: پاسخ همان `202` است ولی وضعیت به `expired` می‌رود و صف لغو می‌شود (بدون پیامک).
- ارسال مکرر فراخوان تکراری نمی‌سازد: کلید `idempotency_key = sms:{request}:{donor}:b{batch}`.
- `candidate_count` فقط کاندیداهای کاملاً تأییدشده (داده/رضایت/آمادگی) است.

### `GET /api/v1/blood-requests/{request_id}/candidates` — `center_operator` مالک یا `admin` → 200

```json
{ "data": [ { "donor_reference": "donor-9f2c1a7b3e4d", "eta_minutes": 18, "distance_km": 9.0,
              "eligibility_check_status": "verified_data", "dispatch_stage": 1 } ],
  "meta": { "request_id": "uuid", "page": 1, "page_size": 20, "total": 1 } }
```

- `donor_reference` یک HMAC بی‌نام است؛ برای تطبیق با `/responses` استفاده می‌شود، قابل تبدیل به شماره/نام نیست.
- `eligibility_check_status` مقادیر `verified_data` / `needs_review` دارد؛ فقط `verified_data` فراخوان می‌شود.
- `dispatch_stage` شماره مرحله‌ای است که داوطلب در آن پیامک می‌گیرد (قبل از ارسال، مرحله برنامه‌ریزی‌شده نمایش داده می‌شود).

### `GET /api/v1/notifications` — نقش `donor` → 200

```json
{ "data": [ { "id": "uuid", "request_id": "uuid", "channel": "sms", "status": "sent",
              "created_at": "2026-11-04T10:31:00Z", "center_id": "uuid",
              "center_name": "مرکز اهدای خون نمونه - تهران", "component_type": "red_cells",
              "blood_group": "O", "rh_factor": "positive", "urgency": "urgent",
              "expires_at": "2026-11-04T16:00:00Z", "response": null } ],
  "meta": { "request_id": "uuid", "page": 1, "page_size": 20, "total": 1 } }
```

- مرتب‌سازی: جدیدترین ابتدا. فقط اعلان‌های خود داوطلب.
- `response` بعد از ثبت پاسخ: `{ "response": "interested", "responded_at": "...Z" }`.
- لینک امن پاسخ در پیامک، `?token=` دارد؛ آن توکن در هیچ پاسخ JSON برنمی‌گردد.

### `POST /api/v1/notifications/{notification_id}/response` — نقش `donor` → 201

```json
{ "response": "interested", "eta_minutes": 18 }
```

```json
{ "data": { "notification_id": "uuid", "response": "interested", "responded_at": "2026-11-04T10:35:00Z" },
  "meta": { "request_id": "uuid" } }
```

- `response` فقط `interested` یا `unavailable`؛ `eta_minutes` اختیاری و `0..1440`.
- پاسخ دوم روی همان اعلان → `409 CONFLICT` (`details[].message = already_answered`).
- اعلانِ داوطلب دیگر → `403`؛ اعلان ناموجود → `404`.
- اثر جانبی: اگر تعداد `interested` به `units_needed` برسد، درخواست `fulfilled` و صف باقی‌مانده `cancelled` می‌شود.

### `GET /api/v1/blood-requests/{request_id}/responses` — اسرا

قرارداد بخش ۹.۱۳ بدون تغییر. داده لازم در جدول `donor_responses` آماده است
(`notification_id` منحصربه‌فرد، `response`، `responded_at`، `eta_minutes`، `donor_id`).
برای `donor_reference` از `app.api.v1.endpoints.dispatch.donor_reference(donor_id)` استفاده کنید تا
نام‌گذاری با `/candidates` یکی بماند. شماره تماس و مختصات را برنگردانید.

## ۶. سامانه

- `GET /api/v1/health` → `{ "data": { "status": "ok", "environment", "api_version", "sms_provider", "maps_provider", "compatibility_policy" }, "meta": ... }`
  نام adapter را نشان می‌دهد، نه مقدار راز. در دمو `mock` انتظار می‌رود.

## ۷. Integration notes برای فرانت‌اند (شقایق)

- `frontend/js/config.js` باید `API_BASE_URL` را به `http://localhost:8000/api/v1` تنظیم کند
  (پیش‌فرض `PUBLIC_APP_BASE_URL` روی `http://localhost:5500` است؛ CORS همان Origin را می‌پذیرد).
- توکن را در `sessionStorage` با کلید `blood_access_token` نگه دارید و `X-Request-Id` (uuid ساخته‌شده در مرورگر)
  را بفرستید تا لاگ سرور و UI قابل تطبیق باشند.
- روی `error.code` سوئیچ کنید نه روی متن پیام؛ متن‌ها فارسی‌اند و ممکن است تغییر کنند.
- `401` → هدایت به لاگین، `409` → پیام وضعیت، `429` → غیرفعال‌سازی دکمه تا پایان `Retry-After`.
- فیلدهای `PATCH` را بدون تغییر نام مصرف کنید؛ هیچ تبدیل camelCase در سمت سرور انجام نمی‌شود.
