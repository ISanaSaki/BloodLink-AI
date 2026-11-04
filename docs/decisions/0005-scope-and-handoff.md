# ۰۰۰۵ — دامنه این پیاده‌سازی و نقطه اتصال هم‌تیمی‌ها

- وضعیت: پذیرفته‌شده (۲۰۲۶-۱۱-۰۴) — مالک: ثنا
- زمینه: تیکت دامنه را «فقط سهم ثنا (Backend Lead)» تعیین کرد. سهم اسرا و شقایق قرارداد‌محور است و
  باید روی همین پایه سوار شود، نه اینکه همین فایل‌ها بازنویسی شوند.
- تصمیم — آنچه **پیاده‌سازی شده** (همه با تست روی PostgreSQL واقعی):

| ماژول | فایل‌ها | تست |
| --- | --- | --- |
| config/security/exceptions/logging/context/dependencies | `app/core/*` | در همه تست‌ها |
| مدل‌ها + مهاجرت | `app/db/models/*`, `alembic/versions/*` | `alembic check`، `test_state_machines.py` |
| Auth OTP + توکن | `services/otp_service.py`, `api/v1/endpoints/auth.py` | `test_auth_otp.py` |
| خودخدمات داوطلب | `services/donor_service.py`, `endpoints/donor_profile.py`, `endpoints/donor_location.py` | `test_donor_self_service.py` |
| Matching | `services/matching_service.py` | `test_matching_service.py` |
| Dispatch + پاسخ | `services/notification_service.py`, `endpoints/dispatch.py`, `endpoints/notifications.py` | `test_dispatch.py`, `test_notifications_api.py` |
| Adapter پیامک/نقشه | `services/sms_service.py`, `services/maps_service.py` | `test_matching_service.py`, `test_dispatch.py` |
| Celery + Beat | `tasks/celery_app.py`, `tasks/notification_tasks.py` | `test_dispatch.py`, `test_state_machines.py` |
| قرارداد API | `schemas/*`, `main.py` | `test_api_contract.py` |
| داده نمایشی | `scripts/seed_demo.py` | `test_seed_demo.py` |

- آنچه **عمداً ساخته نشده** (مالک: اسرا):
  - `api/v1/endpoints/centers.py` — `GET /centers`، `GET/PATCH /centers/{id}`، `POST /centers` (admin).
  - `api/v1/endpoints/blood_requests.py` — Create/List/Detail/PATCH(draft)/activate/cancel/responses.
  - `api/v1/endpoints/donor_availability.py` — `PATCH /donors/me/availability`.
  - ثبت سه router در `api/v1/router.py` (بلاک کامنت‌شده همان‌جاست؛ فقط ۴ خط باز می‌شود، تضاد Git ندارد).
  - مالک: شقایق — کل `frontend/**`، از جمله `pages/respond.html` که لینک `?token=` پیامک را مصرف می‌کند.
- قرارداد اتصال (برای اینکه موازی کار کنیم بدون شکستن تست‌ها):
  1. فایل‌های `app/core/*` و `app/services/*` و `app/tasks/*` را فقط ثنا تغییر دهد (بخش ۴ سند).
  2. برای endpoint جدید: schema در `app/schemas/`، تست در `app/tests/`، و یک بخش در `docs/API_CONTRACT.md` در همان PR.
  3. تغییر مدل → Migration + `alembic check` سبز + به‌روزرسانی `docs/ERD.md`.
  4. `donor_availability` روی جدول موجود می‌نویسد؛Matching همان `DonorAvailability.is_available_at` را می‌خواند،
     پس منطق آمادگی را duplicate نکنید.
  5. برای `activate` از `BloodRequest.transition_to(ACTIVE)` استفاده کنید (ماشین‌وضعیت + `activated_at` رایگان می‌آید).
- پیامد: دمو بدون کد اسرا قابل اجراست (seed + dispatch + پاسخ داوطلب)؛ اما جریان کامل «اپراتور درخواست می‌سازد»
  تا ثبت آن endpointها از طریق API بسته است. برای دمو می‌توان از `scripts/seed_demo.py` و تغییر وضعیت در DB استفاده کرد.
