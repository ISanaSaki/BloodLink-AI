# 0002 — Swappable adapters, demo values and the added settings keys

- Status: accepted (2026-11-04) — Owner: Sana
- Context: the document (sections 0 and 13) explicitly says no contract may pre-determine the brand
  of the SMS gateway, the maps service, the official donation-eligibility rules or an API key. In a
  contest environment, no secret may sit in the repo either.
- Decision:
  1. **SMS**: `app/services/sms_service.py` has an `SmsProvider` Protocol and a `MockSmsProvider`
     implementation. `SMS_PROVIDER` (values: `mock`) selects the adapter. In mock mode the message is
     recorded in memory and the number is masked with `mask_phone`; tests use the same record.
  2. **Maps**: `app/services/maps_service.py` with `MockMapsProvider` (haversine × 30 km/h speed ×
     1.25 factor). If the provider errors, `estimate_route()` falls back to a distance estimate and
     records `source` as `fallback` so it stays explainable in `/candidates` (section 11.4).
  3. **Eligibility**: `DemoDeclaredTypePolicy` only checks "declared type matching" and works with
     the `COMPATIBILITY_POLICY=demo` label. No clinical guess, group/component compatibility or
     inter-donation interval is built in the team's code (document section 1.2).
  4. **OTP store**: Redis if `REDIS_URL` answers, otherwise `InMemoryChallengeStore` (for tests and
     fast local runs). Rate-limit keys include an HMAC of phone/IP so raw data never becomes a key.
  5. **Celery broker**: if Redis is unavailable, the dispatch endpoint runs inline so the demo does
     not break (`_enqueue_batch`); stage scheduling is recovered from the database state
     (decision 0003).
- Settings keys added relative to document section 13 (MVP values, changeable without a migration):

| Key | Default | Purpose |
| --- | --- | --- |
| `OTP_RATE_LIMIT_WINDOW_SECONDS` | 3600 | Window for the code-request cap |
| `OTP_MAX_REQUESTS_PER_PHONE` | 5 | Cap per phone in the window |
| `OTP_MAX_REQUESTS_PER_IP` | 15 | Cap per IP in the window |
| `COMPATIBILITY_POLICY` | `demo` | Selects the matching policy; only `demo` has a real value |
| `PUBLIC_APP_BASE_URL` | `http://localhost:5500` | Base of the secure response link in SMS and the allowed CORS origin |
| `DISPATCH_RESPONSE_WINDOW_MINUTES` | 15 | Interval between dispatch stages |
| `SMS_DEV_OUTBOX_FILE` | empty (`backend/.dev-outbox.log` in development mode) | Demo message outbox: writes the full SMS text (OTP code and response link) to a readable file so the team can see the code without logging secrets; in production the value must stay empty and the Settings validator rejects it |

- Consequences: connecting a real gateway needs only a new class + `SMS_PROVIDER=<name>` and a secret
  in `.env`; no endpoint or test changes. Until demo day, no real key/secret value is allowed in the
  repo (or in this file).
