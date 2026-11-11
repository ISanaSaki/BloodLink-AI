# 0004 — Privacy: mask, hash and delete; not just "hide in the UI"

- Status: accepted (2026-11-04) — Owner: Sana
- Context: document section 14 says phone numbers, OTP codes, tokens and exact locations must never
  appear in logs or unnecessary responses, and section 1.2 forbids storing a location without
  explicit consent. "Don't show it in the UI" does not guarantee this rule; it must be enforced in
  the storage layer, the logs and the API contract.
- Decision (each item has one code mechanism + one test):
  1. **OTP**: only `hash_otp(code)` (HMAC-SHA256 with `SECRET_KEY`) is stored; comparison uses
     `hmac.compare_digest`. The raw code is never written anywhere (test: `test_auth_otp.py`).
  2. **Rate-limit keys**: the phone/IP counting keys are built as truncated HMACs (`_rate_key`), so
     the raw phone never remains even as a Redis key.
  3. **Logging**: `app/core/logging.py::redact` removes values of sensitive keys
     (`otp, code, token, access_token, authorization, password, phone, secret`) and `mask_phone`
     turns a number into `+989***567`. SMS logs carry only provider/status.
  4. **Audit**: `AuditService.record` applies the same `redact` before storing `details` and
     attaches the `request_id`.
  5. **Centre panel**: `donor_reference` is a 12-hex HMAC with `SECRET_KEY`; no number, name or
     coordinates. `GET /candidates` never returns `latitude/longitude/phone` (test:
     `test_dispatch.py::test_candidates_endpoint_hides_donor_pii`).
  6. **Revoking location consent**: `apply_profile_patch` with `location_consent=false` **deletes**
     the `donor_locations` record instead of only flipping a flag.
  7. **Centre notes** (`blood_requests.notes`) exist only in centre endpoints and never appear in
     SMS/`/notifications`/`/candidates`.
  8. **Donor response token**: `notifications.response_token` is a random one-time value; it only
     opens the response path and grants no other access. It is never returned in any JSON response.
  9. **The OTP never passes through the broker**: sending the code SMS is inline in the request path
     (`_send_otp_sms` in `endpoints/auth.py`). We had a Celery task, but task arguments are stored in
     Redis; that would put the one-time code and the phone number in the queue/broker. The remaining
     tasks carry only `request_id`/`batch_number`.
 10. **Demo message outbox**: `SMS_DEV_OUTBOX_FILE` (development only) writes the SMS text to a
     gitignored file so the OTP code and the response link stay readable in the demo; this is not a
     substitute for logs and Settings rejects it in production.
- Consequences:
  - For a real gateway, logs must use the same `get_logger`; direct `print` or a custom logger is
    forbidden.
  - In `GET /blood-requests/{id}/responses`, Asra must use `donor_reference`, not the phone number;
    showing the direct contact is allowed only with explicit permission in the centre role
    (section 9.13) and after a new decision is recorded.
  - If a number ever needs debugging, use `mask_phone` and record the decision in this folder.
