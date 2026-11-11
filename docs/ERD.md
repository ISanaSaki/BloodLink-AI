# ERD — Implemented Data Model

Source of truth: `backend/app/db/models/*.py` + Alembic migrations (current head: `10dc83a66c29`).
This file is kept up to date with every `alembic revision --autogenerate`; each model change must update
the Migration, this document, and `docs/decisions/` (team document sections 4 and 20).

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
        boolean blood_type_verified "authorized source only"
        date last_donation_date "self-declared until verified"
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
        varchar opening_hours "+added"
        uuid owner_user_id "+added"
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
        text notes "+added (internal, never in SMS)"
        timestamptz activated_at "+added"
    }
    NOTIFICATIONS {
        uuid id PK
        uuid request_id FK
        uuid donor_id FK
        varchar channel "sms"
        varchar status "queued | sent | delivered | failed | cancelled"
        varchar idempotency_key UK "sms:{request}:{donor}:b{batch}"
        varchar provider_message_id
        integer batch_number "+added (dispatch stage)"
        integer retry_count "+added"
        text failure_reason "+added"
        varchar response_token UK "+added (secure response link)"
    }
    DONOR_RESPONSES {
        uuid id PK
        uuid notification_id FK_UK
        varchar response "interested | unavailable"
        timestamptz responded_at
        integer eta_minutes "+added"
    }
    AUDIT_LOGS {
        uuid id PK
        timestamptz created_at "append-only"
        uuid actor_id FK_null "SET NULL on delete"
        varchar action "60"
        varchar entity_type "40"
        varchar entity_id "64 (uuid as string)"
        json details "redacted"
        varchar request_id "36"
        text comment
    }
```

## Implemented integrity rules

- Every table uses a UUID primary key (no exceptions; junction tables also have UUIDs and only
  preserve uniqueness).
- Enums are stored as `VARCHAR + CHECK` (`native_enum=False`) so adding a new value does not
  require a heavy PostgreSQL migration; the `create_constraint=True` constraint also rejects
  invalid values at the database level.
- Constraint names come from the `NAMING_CONVENTION` in `app/db/base.py`: `ix_`, `uq_`, `ck_`,
  `fk_`, `pk_`. These names keep `alembic --autogenerate` from producing ambiguous changes.
- `notifications.idempotency_key` and `donor_responses.notification_id` are unique:
  DSP-03 and "one final response per notification" are guaranteed in the database, not only in code.
- `ondelete`: `request_id`/`donor_id` in `notifications` and `notification_id` in `donor_responses`
  use `CASCADE`; `blood_requests.center_id` is protected with `RESTRICT` (a centre with open
  requests cannot be deleted) and `audit_logs.actor_id` uses `SET NULL` so records survive user
  deletion.
- Semantic integrity lives in the model, not the DB: `BloodRequest.transition_to` and
  `Notification.transition_to` enforce the state machine from section 15 and return
  `409 CONFLICT` on an illegal transition.

## Medical note (a boundary that is never coded unilaterally)

`blood_group`/`rh_factor`/`component_type` only store the centre's "declared type" and the donor's
"verified data". No clinical compatibility, donation-interval, or medical-eligibility rules are
built by the team; `DemoDeclaredTypePolicy` only checks declared-type matching for the demo and is
labelled `demo` (decision 0002). The official source of the rules must be set by the blood centre /
blood transfusion organization.
