# ۰۰۰۳ — مرحله‌بندی فراخوان:Beat مسئول پیشرفت مرحله است، نه task ارسال

- وضعیت: پذیرفته‌شده (۲۰۲۶-۱۱-۰۴) — مالک: ثنا
- زمینه: بخش ۱۱.۳ سند می‌گوید فراخوان مرحله‌ای ارسال شود و تا پایان پنجره پاسخ، مرحله بعدی نرود.
  پیاده‌سازی اولیه، خود `dispatch_notification_batch` با `apply_async(countdown=…)` مرحله بعد را زمان‌بندی می‌کرد.
  این طرح دو اشکال عملی داشت: (الف) در حالت eager/تست و در اجرای بدون Redis، همه مراحل بلافاصله fire می‌شدند؛
  (ب) با restart ورکر، زمان‌بندی درون حافظه Celery از بین می‌رفت و مرحله‌ای هرگز ارسال نمی‌شد.
- تصمیم:
  1. `dispatch_notification_batch(request_id, batch_number)` **دقیقاً یک مرحله** می‌فرستد و هیچ زنجیره‌ای نمی‌سازد.
  2. progression از وضعیت دیتابیس خوانده می‌شود: `NotificationService.advance_due_batches(now)`
     برای هر درخواست `active` که منقضی نشده، کوچک‌ترین مرحله `queued` را زمانی آزاد می‌کند که
     `now - max(updated_at of sent/delivered) >= DISPATCH_RESPONSE_WINDOW_MINUTES` باشد.
  3. تسک Beat `check-dispatch-timeout` هر ۶۰ ثانیه `expire_overdue()` و سپس `advance_due_batches()` را اجرا و
     برای هر جفت `(request_id, batch_number)` فرستاده‌شده، `dispatch_notification_batch.delay(...)` می‌زند.
  4. توقف‌ها قبل از ارسال بررسی می‌شوند: درخواست terminal/non-active/expired/fulfilled → `send_batch` صفر برمی‌گرداند
     و پیامکی نمی‌فرستد (تست‌های `test_state_machines.py`).
- پیامد:
  - دمو/تست بدون Redis درست کار می‌کند و با یک `celery beat` واقعی هم همان مسیر اجرا می‌شود.
  - ثبت تسک‌ها با `imports` صریح در `celery_app.py` انجام می‌شود؛ `autodiscover_tasks(["app.tasks"])` ماژول
    `notification_tasks` را پیدا نمی‌کرد و کارگر با رجیستری خالی بالا می‌آمد (تست‌ها سبز می‌ماندند).
    دو تست در `test_dispatch.py` این را قفل می‌کنند.
  - حداکثر تأخیر بین دو مرحله = پنجره پاسخ + ۶۰ ثانیه (دقت Beat)؛ برای MVP قابل قبول است.
  - اگر Beat خاموش بماند، مرحله بعدی ارسال نمی‌شود — این عمدی است (ارسال بی‌رویه بدتر است) و در README یادآوری شده.
  - اسرا برای `POST /blood-requests/{id}/cancel` فقط باید `cancel_pending_notifications` را صدا بزند؛
    منطق مرحله‌بندی دوباره نوشته نمی‌شود.
