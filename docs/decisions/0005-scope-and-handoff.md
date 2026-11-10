# 0005 — Scope of this implementation and the teammates' integration point

- Status: accepted (2026-11-04) — Owner: Sana
- Context: the ticket defined the scope as "only Sana's share (Backend Lead)". Asra's and
  Shaghayeq's shares are contract-driven and must sit on top of this base, not rewrite these same
  files.
- Decision — what is **implemented** (all tested on real PostgreSQL):

| Module | Files | Tests |
| --- | --- | --- |
| config/security/exceptions/logging/context/dependencies | `app/core/*` | across all tests |
| Models + migrations | `app/db/models/*`, `alembic/versions/*` | `alembic check`, `test_state_machines.py` |
| Auth OTP + token | `services/otp_service.py`, `api/v1/endpoints/auth.py` | `test_auth_otp.py` |
| Donor self-service | `services/donor_service.py`, `endpoints/donor_profile.py`, `endpoints/donor_location.py` | `test_donor_self_service.py` |
| Matching | `services/matching_service.py` | `test_matching_service.py` |
| Dispatch + response | `services/notification_service.py`, `endpoints/dispatch.py`, `endpoints/notifications.py` | `test_dispatch.py`, `test_notifications_api.py` |
| SMS/maps adapters | `services/sms_service.py`, `services/maps_service.py` | `test_matching_service.py`, `test_dispatch.py` |
| Celery + Beat | `tasks/celery_app.py`, `tasks/notification_tasks.py` | `test_dispatch.py`, `test_state_machines.py` |
| API contract | `schemas/*`, `main.py` | `test_api_contract.py` |
| Demo data | `scripts/seed_demo.py` | `test_seed_demo.py` |

- What is **deliberately not built** (owner: Asra):
  - `api/v1/endpoints/centers.py` — `GET /centers`, `GET/PATCH /centers/{id}`, `POST /centers`
    (admin).
  - `api/v1/endpoints/blood_requests.py` — Create/List/Detail/PATCH(draft)/activate/cancel/responses.
  - `api/v1/endpoints/donor_availability.py` — `PATCH /donors/me/availability`.
  - Registering the three routers in `api/v1/router.py` (the commented block is right there; only 4
    lines to uncomment, no Git conflict).
  - Owner: Shaghayeq — all of `frontend/**`, including `pages/respond.html` which consumes the
    `?token=` link of the SMS.
- Integration contract (so we can work in parallel without breaking tests):
  1. Only Sana changes the `app/core/*`, `app/services/*` and `app/tasks/*` files (document
     section 4).
  2. For a new endpoint: a schema in `app/schemas/`, a test in `app/tests/`, and a section in
     `docs/API_CONTRACT.md` in the same PR.
  3. Model change → Migration + green `alembic check` + `docs/ERD.md` update.
  4. `donor_availability` writes to the existing table; Matching reads the same
     `DonorAvailability.is_available_at`, so don't duplicate the availability logic.
  5. For `activate` use `BloodRequest.transition_to(ACTIVE)` (the state machine + `activated_at`
     come for free).
- Consequences: the demo runs without Asra's code (seed + dispatch + donor response); but the full
  "operator creates a request" flow is closed through the API until those endpoints are registered.
  For the demo, `scripts/seed_demo.py` and a DB status change can be used.
