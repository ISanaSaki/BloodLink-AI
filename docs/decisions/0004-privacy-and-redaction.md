# ۰۰۰۴ — حریم خصوصی: ماسک، هش و حذف؛ نه «فقط نمایش»

- وضعیت: پذیرفته‌شده (۲۰۲۶-۱۱-۰۴) — مالک: ثنا
- زمینه: بخش ۱۴ سند می‌گوید شماره تماس، کد OTP، توکن و موقعیت دقیق هرگز نباید در لاگ یا پاسخ‌های غیرضروری ظاهر شود،
  و بخش ۱.۲ ذخیره موقعیت بدون رضایت صریح را ممنوع می‌کند. این قاعده با «در UI نشان نده» تضمین نمی‌شود؛
  باید در لایه ذخیره، لاگ و قرارداد API اعمال شود.
- تصمیم (هر یک یک مکانیزم کد + یک تست دارد):
  1. **OTP**: فقط `hash_otp(code)` (HMAC-SHA256 با `SECRET_KEY`) ذخیره می‌شود؛ مقایسه با
     `hmac.compare_digest`. کد خام هیچ‌جا نوشته نمی‌شود (تست: `test_auth_otp.py`).
  2. **Rate-limit keys**: کلیدهای شمارش شماره/IP به‌صورت HMAC کوتاه‌شده ساخته می‌شوند (`_rate_key`)،
     پس شماره خام حتی به‌عنوان کلید Redis هم باقی نمی‌ماند.
  3. **Logging**: `app/core/logging.py::redact` مقادیر کلیدهای حساس
     (`otp, code, token, access_token, authorization, password, phone, secret`) را حذف می‌کند و
     `mask_phone` شماره را به `+989***567` تبدیل می‌کند. لاگ‌های پیامک فقط provider/status را دارند.
  4. **Audit**: `AuditService.record` همان `redact` را قبل از ذخیره `details` اعمال و `request_id` را می‌چسباند.
  5. **پنل مرکز**: `donor_reference` یک HMAC ۱۲-hex با `SECRET_KEY` است؛ نه شماره، نه نام، نه مختصات.
     `GET /candidates` هرگز `latitude/longitude/phone` برنمی‌گرداند (تست: `test_dispatch.py::test_candidates_endpoint_hides_donor_pii`).
  6. **لغو رضایت مکان**: `apply_profile_patch` با `location_consent=false` رکورد `donor_locations` را **حذف** می‌کند،
     نه اینکه فقط flag را عوض کند.
  7. **Notes مرکز** (`blood_requests.notes`) فقط در endpointهای مرکز است و در پیامک/`/notifications`/`/candidates` ظاهر نمی‌شود.
  8. **Token پاسخ داوطلب**: `notifications.response_token` یک مقدار تصادفی یک‌بارمصرف است؛ فقط مسیر پاسخ را باز می‌کند
     و هیچ دسترسی دیگری نمی‌دهد. در هیچ پاسخ JSON برنمی‌گردد.
  9. **OTP هرگز از broker رد نمی‌شود**: ارسال پیامک کد، inline در مسیر درخواست است (`_send_otp_sms` در
     `endpoints/auth.py`). تسک Celery داشتیم، اما آرگومان تسک در Redis ذخیره می‌شود؛ یعنی کد یک‌بارمصرف و
     شماره تماس در صف/بروکر می‌نشستند. تسک‌های باقی‌مانده فقط `request_id`/`batch_number` می‌برند.
 10. **صندوق پیام دمو**: `SMS_DEV_OUTBOX_FILE` (فقط development) متن پیامک را در یک فایل gitignore شده می‌نویسد
     تا کد OTP و لینک پاسخ در دمو قابل خواندن باشند؛ این جایگزین لاگ نیست و در production توسط Settings رد می‌شود.
- پیامد:
  - برای درگاه واقعی، لاگ‌ها باید همان `get_logger` را استفاده کنند؛ لاگ مستقیم `print` یا logger سفارشی ممنوع است.
  - اسرا در `GET /blood-requests/{id}/responses` باید از `donor_reference` استفاده کند، نه شماره تماس؛
    نمایش تماس مستقیم فقط با مجوز صریح و در نقش مرکز (بخش ۹.۱۳) و پس از ثبت تصمیم جدید مجاز است.
  - اگر روزی نیاز به دیباگ شماره شد، از `mask_phone` استفاده کنید و تصمیم را در همین پوشه ثبت کنید.
