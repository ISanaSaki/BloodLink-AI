# API Contract — Implemented Version (aligned with the v2.0 spec)

This document records the **implemented** API. Until the Change Log declares otherwise, any change
to a path, a field name or an enum value must be applied here, in the code and in the tests together.

Owner: Sana (Backend Lead). Contributors: Asra, Shaghayeq (section 4 of the team spec).

## 0. Implementation Status

| Scope | Status | Owner |
| --- | --- | --- |
| `auth`, `users/me`, `donors/me/profile`, `donors/me/location` | Implemented and tested | Sana |
| `dispatch`, `candidates`, `notifications`, donor response | Implemented and tested | Sana |
| `centers`, `blood-requests` (CRUD/activate/cancel/responses), `donors/me/availability` | **Pending** (contract = section 9 of the main spec) | Asra |
| `frontend/**` | Pending | Shaghayeq |

`backend/app/api/v1/router.py` marks the exact spot where Asra's routers are registered; uncomment
those three lines without touching any other file, so Git conflicts are avoided (section 16.2).

## 1. Common Rules (no exceptions)

- Dev base URL: `http://localhost:8000`; every path sits under the `/api/v1` prefix.
- Auth: `Authorization: Bearer <access_token>`; only `/auth/otp/*` and `/health` are public.
- Success body: `{ "data": ..., "meta": { "request_id": "uuid", "page"?: int, "page_size"?: int, "total"?: int } }`
- Error body: `{ "error": { "code", "message", "request_id", "details"?: [{ "field", "message" }] } }`
- `X-Request-Id`: when the client sends it, the same value comes back in `meta.request_id`,
  `error.request_id` and the response header; otherwise the server generates one. Include this
  header when reporting an error.
- Field names are exactly `snake_case`; timestamps are ISO-8601 UTC with a `Z` suffix; dates are `YYYY-MM-DD`.
- Enums are lowercase with underscores (`awaiting` does not exist; `available` / `queued` / `red_cells`).
- Pagination: `page` starts at 1, `page_size` defaults to 20 and caps at 100; `page_size=101` → `422`.
- `PATCH` bodies use `extra="forbid"`: an unknown field → `422` (never silently ignored).

Error codes (section 7.2): `INVALID_REQUEST` 400, `UNAUTHENTICATED` 401, `FORBIDDEN` 403,
`RESOURCE_NOT_FOUND` 404, `CONFLICT` 409, `VALIDATION_ERROR` 422, `RATE_LIMITED` 429, `INTERNAL_ERROR` 500.
A 500 body never leaks internal detail or a stack trace; it carries only `request_id` for log correlation.

## 2. Auth

### `POST /api/v1/auth/otp/request` — public → 202

```json
{ "phone": "+989121234567", "purpose": "register" }
```

```json
{ "data": { "challenge_id": "uuid", "expires_in_seconds": 120, "resend_after_seconds": 60 },
  "meta": { "request_id": "uuid" } }
```

- `purpose` is only `register` or `login`; the phone must be E.164 (`PHONE_PATTERN` in `app/schemas/common.py`).
- Early resend → `429 RATE_LIMITED` with a `Retry-After` header.
- Window caps: `OTP_MAX_REQUESTS_PER_PHONE` / `OTP_MAX_REQUESTS_PER_IP` (decision 0002).
- The OTP itself is stored only as an HMAC digest; it never appears in a response or a log.

### `POST /api/v1/auth/otp/verify` — public → 200

```json
{ "challenge_id": "uuid", "phone": "+989121234567", "code": "123456", "purpose": "register" }
```

```json
{ "data": { "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600,
            "user": { "id": "uuid", "phone": "+989121234567", "role": "donor", "is_profile_complete": false } },
  "meta": { "request_id": "uuid" } }
```

- `code` is exactly 6 digits; a wrong or expired code → `401 UNAUTHENTICATED`. After `OTP_MAX_ATTEMPTS`
  (default 5) failed tries, the challenge locks with `429 RATE_LIMITED`; request a new code to continue.
- `purpose=login` for a phone without an active user → `404 RESOURCE_NOT_FOUND`.
- A disabled user → `401 UNAUTHENTICATED`. A challenge is single-use; a second verify on the same
  challenge never succeeds.
- A new user's role is always `donor`; other roles are only created by an admin.

## 3. Current User

### `GET /api/v1/users/me` — any role → 200

```json
{ "data": { "id": "uuid", "phone": "+989121234567", "role": "donor",
            "is_active": true, "is_profile_complete": true },
  "meta": { "request_id": "uuid" } }
```

`is_profile_complete` means blood group + Rh are recorded (only for the `donor` role; for other roles it
is `false` unless they have a donor profile).

## 4. Donor Self-Service

### `PATCH /api/v1/donors/me/profile` — role `donor` → 200

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

- `blood_type_verified` does not exist on input; sending it → `422` (section 9.4 of the spec).
- An empty body (`{}`) → `422`.
- Revoking `location_consent` **deletes** the location record (not just disables it).
- Changes land in `audit_logs` with the field names, without sensitive values.

### `PATCH /api/v1/donors/me/location` — role `donor` with `location_consent=true` → 200

```json
{ "latitude": 35.7050, "longitude": 51.4050 }
```

```json
{ "data": { "donor_id": "uuid", "latitude": 35.7050, "longitude": 51.4050,
            "updated_at": "2026-11-04T10:30:00Z", "location_consent": true },
  "meta": { "request_id": "uuid" } }
```

- No consent → `403 FORBIDDEN`. Out-of-range coordinates → `422`.
- Coordinates never appear in logs, in other users' responses or in `/candidates`.

### `PATCH /api/v1/donors/me/availability` — role `donor` (Asra)

Section 9.5 contract unchanged: `{ "status": "available", "available_from": "...Z", "available_until": "...Z" }`
with a `{ donor_id, status, available_from, available_until, updated_at }` response.
The `DonorAvailability` model and the `window_is_ordered` constraint are ready; only the endpoint and
its schema remain. Note: matching reads this table; if you change `status` or the window semantics,
re-review `app/services/matching_service.py::_candidate_query` with a test.

## 5. Dispatch

### `POST /api/v1/blood-requests/{request_id}/dispatch` — owning `center_operator` or `admin` → 202

No body.

```json
{ "data": { "dispatch_id": "uuid", "request_id": "uuid", "status": "queued",
            "candidate_count": 3, "first_batch_size": 3 },
  "meta": { "request_id": "uuid" } }
```

- Only an `active` request at a verified/active centre; otherwise `403` (unverified centre) or
  `409` (state / empty candidate list).
- An already-expired request: the response is still `202`, but the request moves to `expired` and the
  queue is cancelled (no SMS is sent).
- Re-dispatching never duplicates: `idempotency_key = sms:{request}:{donor}:b{batch}`.
- `candidate_count` counts only fully verified candidates (data / consent / availability).

### `GET /api/v1/blood-requests/{request_id}/candidates` — owning `center_operator` or `admin` → 200

```json
{ "data": [ { "donor_reference": "donor-9f2c1a7b3e4d", "eta_minutes": 18, "distance_km": 9.0,
              "eligibility_check_status": "verified_data", "dispatch_stage": 1 } ],
  "meta": { "request_id": "uuid", "page": 1, "page_size": 20, "total": 1 } }
```

- `donor_reference` is an anonymous HMAC; it exists to correlate with `/responses` and cannot be
  turned back into a name or a phone number.
- `eligibility_check_status` is `verified_data` or `needs_review`; only `verified_data` is dispatched.
- `dispatch_stage` is the stage number in which the donor receives an SMS (before any send, the
  planned stage is shown).

### `GET /api/v1/notifications` — role `donor` → 200

```json
{ "data": [ { "id": "uuid", "request_id": "uuid", "channel": "sms", "status": "sent",
              "created_at": "2026-11-04T10:31:00Z", "center_id": "uuid",
              "center_name": "Tehran Central Blood Center", "component_type": "red_cells",
              "blood_group": "O", "rh_factor": "positive", "urgency": "urgent",
              "expires_at": "2026-11-04T16:00:00Z", "response": null } ],
  "meta": { "request_id": "uuid", "page": 1, "page_size": 20, "total": 1 } }
```

- Order: newest first. Only the donor's own notifications.
- `response` after answering: `{ "response": "interested", "responded_at": "...Z" }`.
- The secure response link in the SMS carries `?token=`; that token never comes back in any JSON response.

### `POST /api/v1/notifications/{notification_id}/response` — role `donor` → 201

```json
{ "response": "interested", "eta_minutes": 18 }
```

```json
{ "data": { "notification_id": "uuid", "response": "interested", "responded_at": "2026-11-04T10:35:00Z" },
  "meta": { "request_id": "uuid" } }
```

- `response` is only `interested` or `unavailable`; `eta_minutes` is optional, range `0..1440`.
- A second answer on the same notification → `409 CONFLICT` (`details[].message = already_answered`).
- Another donor's notification → `403`; unknown notification → `404`.
- Side effect: when the `interested` count reaches `units_needed`, the request becomes `fulfilled`
  and the remaining queue is `cancelled`.

### `GET /api/v1/blood-requests/{request_id}/responses` — Asra

Section 9.13 contract unchanged. The data is ready in the `donor_responses` table
(unique `notification_id`, `response`, `responded_at`, `eta_minutes`, `donor_id`).
For `donor_reference` use `app.api.v1.endpoints.dispatch.donor_reference(donor_id)` so the naming
stays identical to `/candidates`. Never return phone numbers or coordinates.

## 6. System

- `GET /api/v1/health` → `{ "data": { "status": "ok", "environment", "api_version", "sms_provider", "maps_provider", "compatibility_policy" }, "meta": ... }`
  It exposes the adapter names, not secret values. `mock` is expected in the demo.

## 7. Integration Notes for the Frontend (Shaghayeq)

- `frontend/js/config.js` must set `API_BASE_URL` to `http://localhost:8000/api/v1`
  (`PUBLIC_APP_BASE_URL` defaults to `http://localhost:5500`; CORS accepts that origin).
- Keep the token in `sessionStorage` under the key `blood_access_token` and send an `X-Request-Id`
  (a uuid built in the browser) so server logs and the UI stay correlatable.
- Switch on `error.code`, never on the message text; messages may change.
- `401` → send to login, `409` → show the state message, `429` → disable the button until `Retry-After` elapses.
- Consume `PATCH` fields with their exact names; no camelCase conversion happens server-side.
