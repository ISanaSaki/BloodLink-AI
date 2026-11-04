# ERD — مدل داده اجراشده

منبع حقیقت: `backend/app/db/models/*.py` + مهاجرت‌های Alembic (هد فعلی: `10dc83a66c29`).
این فایل با `alembic revision --autogenerate`ها به‌روز می‌ماند؛ هر تغییر مدل باید
هم Migration، هم این سند، هم `docs/decisions/` را به‌روز کند (بخش ۴ و ۲۰ سند تیمی).

```mermaid
erDiagram
    USERS ||--o| DONOR_PROFILES : "has"
    DONOR_PROFILES ||--o| DONOR_LOCATIONS : "stores"
    DONOR_PROFILES ||--o| DONOR_AVAILABILITY : "declares"
    USERS ||--o{ BLOOD_CENTERS : "owns"
    BLOOD_CENTERS ||--o{ BLOOD_REQUESTS : "raises"
    USERS ||--o{ BLOOD_REQUESTS : "creates"
    BLOOD_REQUESTS ||--o{ NOTIFICATIONS : "dispatches"
    DONOR_PROFILES ||--o{ NOTIFICATIONS : "receives"
    NOTIFICATIONS ||--o| DONOR_RESPONSES : "answered_by"
    USERS ||--o{ AUDIT_LOGS : "acts"

    USERS {
        uuid id PK
        varchar phone UK "E.164"
        varchar role "donor | center_operator | admin"
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }
    DONOR_PROFILES {
        uuid id PK
        uuid user_id FK_UK
        varchar blood_group "A | B | AB | O | null"
        varchar rh_factor "positive | negative | null"
        boolean blood_type_verified "فقط مرجع مجاز"
        date last_donation_date "خوداظهاری تا تأیید"
        boolean sms_consent
        boolean location_consent
    }
    DONOR_LOCATIONS {
        uuid id PK
        uuid donor_id FK_UK
        numeric latitude "9,6 | ck -90..90"
        numeric longitude "9,6 | ck -180..180"
        timestamptz updated_at
    }
    DONOR_AVAILABILITY {
        uuid id PK
        uuid donor_id FK_UK
        varchar status "available | unavailable"
        timestamptz available_from
        timestamptz available_until "ck: from <= until"
    }
    BLOOD_CENTERS {
        uuid id PK
        varchar name
        text address
        numeric latitude "NOT NULL"
        numeric longitude "NOT NULL"
        varchar phone
        boolean is_verified
        boolean is_active
        varchar opening_hours "+اضافه"
        uuid owner_user_id "+اضافه"
    }
    BLOOD_REQUESTS {
        uuid id PK
        uuid center_id FK
        varchar component_type "red_cells | platelets | plasma | whole_blood"
        varchar blood_group
        varchar rh_factor
        integer units_needed "ck > 0"
        varchar urgency "routine | urgent | critical"
        varchar status "draft | active | fulfilled | cancelled | expired"
        timestamptz expires_at
        uuid created_by FK
        text notes "+اضافه (داخلی، هرگز در پیامک)"
        timestamptz activated_at "+اضافه"
    }
    NOTIFICATIONS {
        uuid id PK
        uuid request_id FK
        uuid donor_id FK
        varchar channel "sms"
        varchar status "queued | sent | delivered | failed | cancelled"
        varchar idempotency_key UK "sms:{request}:{donor}:b{batch}"
        varchar provider_message_id
        integer batch_number "+اضافه (مرحله فراخوان)"
        integer retry_count "+اضافه"
        text failure_reason "+اضافه"
        varchar response_token UK "+اضافه (لینک امن پاسخ)"
    }
    DONOR_RESPONSES {
        uuid id PK
        uuid notification_id FK_UK
        varchar response "interested | unavailable"
        timestamptz responded_at
        integer eta_minutes "+اضافه"
    }
    AUDIT_LOGS {
        uuid id PK
        timestamptz created_at "append-only"
        uuid actor_id FK_null "SET NULL on delete"
        varchar action "60"
        varchar entity_type "40"
        varchar entity_id "64 (uuid رشته‌ای)"
        json details "redact شده"
        varchar request_id "36"
        text comment
    }
```

## قواعد یکپارچگی اجراشده

- کلید اصلی همه جداول UUID است (استثنایی ندارد؛ جداول رابطی هم UUID دارند و فقط uniqueness را حفظ می‌کنند).
- enum‌ها به‌صورت `VARCHAR + CHECK` ذخیره می‌شوند (`native_enum=False`) تا افزودن مقدار جدید
  نیازمند مهاجرت سنگین PostgreSQL نباشد؛ قید `create_constraint=True` مقدار نامعتبر را در دیتابیس هم رد می‌کند.
- نام‌گذاری قیدها از `NAMING_CONVENTION` در `app/db/base.py` می‌آید: `ix_`, `uq_`, `ck_`, `fk_`, `pk_`.
  همین نام‌ها باعث می‌شود `alembic --autogenerate` تغییر مبهم نسازد.
- `notifications.idempotency_key` و `donor_responses.notification_id` منحصربه‌فردند:
  DSP-03 و «یک پاسخ نهایی برای هر اعلان» در دیتابیس تضمین می‌شود، نه فقط در کد.
- `ondelete`: برای `request_id`/`donor_id` در `notifications` و برای `notification_id` در `donor_responses`
  مقدار `CASCADE` است، `blood_requests.center_id` با `RESTRICT` محافظت می‌شود (حذف مرکز با درخواست باز مجاز نیست)
  و `audit_logs.actor_id` روی `SET NULL` می‌رود تا سوابق با حذف کاربر از بین نروند.
- یکپارچگی معنایی در مدل است نه DB: `BloodRequest.transition_to` و `Notification.transition_to`
  ماشین‌وضعیت بخش ۱۵ را اعمال و در صورت انتقال غیرمجاز `409 CONFLICT` می‌دهند.

## یادداشت پزشکی (محدوده‌ای که هرگز خودسرانه کدگذاری نمی‌شود)

`blood_group`/`rh_factor`/`component_type` فقط «نوع اعلامی» مرکز و «داده تأییدشده» داوطلب را نگه می‌دارند.
هیچ سازگاری بالینی، قواعد فاصله بین اهدا یا مجوز پزشکی از سمت تیم ساخته نمی‌شود؛
`DemoDeclaredTypePolicy` فقط تطابق اعلامی را برای دمو بررسی می‌کند و برچسب `demo` می‌خورد
(تصمیم ۰۰۰۲). منبع رسمی قواعد باید توسط مرکز/سازمان انتقال خون تعیین شود.
