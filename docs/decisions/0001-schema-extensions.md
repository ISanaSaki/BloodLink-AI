# 0001 — Data model extensions beyond the section 5 table of the document

- Status: accepted (2026-11-04) — Owner: Sana
- Context: the section 5 table of the document lists minimal columns. Several mandatory behaviors of
  the document (secure response link, staged dispatch, SMS retry counting, operational
  accountability) could not be implemented without columns, and renaming the pre-defined names is
  not allowed.
- Decision: the columns below were added; no existing column or name was removed or changed. All of
  them are marked "added" in `docs/ERD.md`.

| Table | Column | Why it was needed |
| --- | --- | --- |
| `blood_centers` | `opening_hours` | Section 9.7 names this field in the `GET /centers` output. |
| `blood_centers` | `owner_user_id` | "Centre operator", "centre owner" and section 9.9 access control need a user↔centre link. |
| `blood_requests` | `notes` | Section 9.8 takes `notes` as input; internal and forbidden in SMS. |
| `blood_requests` | `activated_at` | The 9.9 response must return `activated_at`. |
| `notifications` | `batch_number` | The 11.3 staging and `dispatch_stage` in 9.11. |
| `notifications` | `retry_count`, `failure_reason` | The retry policy and diagnosing the SMS failure cause. |
| `notifications` | `response_token` | The "secure link" of section 12; one-time and separate from the JWT. |
| `donor_responses` | `eta_minutes` | Section 9.13 "eta_minutes if the donor declares it". |
| `audit_logs` | `details`, `request_id`, `comment`, `created_at` | Tracing sensitive operations with log↔request correlation; without `created_at` a record has no evidentiary value. |

- Consequences:
  - The `test_state_machines.py` and `test_dispatch.py` tests lock the behavior of these columns.
  - Asra/Shaghayeq can consume these same columns in their UI and endpoints; the names are
    change-safe.
  - Any further column addition requires a separate PR + migration + an update to this file.
