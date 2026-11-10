# Smart Blood-Donation Call-Out and Donor Routing System — MVP

Implementation of **Sana's (Backend Lead)** share of team document v2.0.
Asra and Shaghayeq work against the same contract; their files are not built yet and their exact
integration point is documented in [`docs/decisions/0005-scope-and-handoff.md`](docs/decisions/0005-scope-and-handoff.md).

- API contract (implemented state): [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)
- Data model: [`docs/ERD.md`](docs/ERD.md)
- Technical decisions and documented deviations: [`docs/decisions/`](docs/decisions/)

## 1. Prerequisites

- Python 3.12+, Docker (for PostgreSQL and Redis), and a free port for Postgres.
- On this machine Postgres runs as a local service on 5432; the project container takes port **5433**
  so your service stays untouched.
- If your system has a Windows proxy (e.g. `127.0.0.1:10809`), use `NO_PROXY='*'` for
  `pip`/`pytest`/`alembic`, otherwise localhost requests time out.

## 2. Setup

```bash
cd "D:/Blood Donation/blood-donation-system"

# 1) Database and Redis
docker compose up -d db redis                 # postgres on host:5433, redis on host:6380

# 2) Python environment
cd backend
python -m venv .venv && source .venv/Scripts/activate
NO_PROXY='*' pip install -e ".[dev]"

# 3) Settings (the real .env file is never committed)
cp ../.env.example .env                       # then change SECRET_KEY
# default values are built for running on the host (5433 and 6380)

# 4) Migrations and demo data
NO_PROXY='*' python -m alembic upgrade head
NO_PROXY='*' python -m scripts.seed_demo

# 5) API
NO_PROXY='*' uvicorn app.main:app --reload --port 8000
```

Swagger: `http://localhost:8000/docs` — health: `GET /api/v1/health`.

### Worker and Beat (optional in the demo)

```bash
celery -A app.tasks.celery_app worker --loglevel=INFO --pool=solo -Q notifications,default
celery -A app.tasks.celery_app beat   --loglevel=INFO
```

`--pool=solo` is Windows-specific; the API, the worker and beat must all see the same broker
(`.env.example` points to the Redis container on port 6380).

Beat runs the `check-dispatch-timeout` task every 60 seconds: it marks overdue requests `expired`
and **releases the next dispatch stage**. If Beat is off, only the first stage is sent — this
behavior is intentional (decision 0003) and is not a substitute for carelessly sending later stages.

Redis must be 6 or higher. If Redis 5 is already running on 6379 on the machine, the worker stops
at startup with `Error running script ... ERR syntax error` — that Lua script is kombu's own, not
project code; this is exactly why compose uses port 6380.

Live check with `DISPATCH_BATCH_SIZE=1` and `DISPATCH_RESPONSE_WINDOW_MINUTES=1`: stage 1 reached
`sent` at dispatch time (mock-000000), stage 2 on the next Beat tick and stage 3 on the tick after
that — three SMS messages, each with a response link.

## 3. Tests

```bash
cd backend
NO_PROXY='*' python -m pytest app/tests -q
```

- Tests run against **real PostgreSQL** (`blood_donation_test` on port 5433) and build the test
  schema with the same Alembic migration chain, so every test run also proves `alembic upgrade head`.
- Redis is not needed: the OTP store is in-memory and Celery runs in eager mode.
- Model/migration drift check: `NO_PROXY='*' python -m alembic check` (must print
  `No new upgrade operations detected`).

## 4. Demo flow (INT-01)

The OTP code and the response link are **not** printed in logs (document section 14). In development
mode, the mock provider writes them to `backend/.dev-outbox.log`:

```bash
# 1) Request a code for the demo centre operator
curl -s -X POST localhost:8000/api/v1/auth/otp/request \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+989120000002","purpose":"login"}'
tail -1 .dev-outbox.log                        # the six-digit code is here

# 2) Verify and get a token
curl -s -X POST localhost:8000/api/v1/auth/otp/verify \
  -H 'Content-Type: application/json' \
  -d '{"challenge_id":"<id>","phone":"+989120000002","code":"<code>","purpose":"login"}'

# 3) Activate the request (this endpoint is Asra's share; for now in the DB)
#    UPDATE blood_requests SET status='active', activated_at=now() WHERE id='<uuid>';

# 4) Staged dispatch
curl -s -X POST localhost:8000/api/v1/blood-requests/<request_id>/dispatch -H "Authorization: Bearer <token>"
curl -s localhost:8000/api/v1/blood-requests/<request_id>/candidates -H "Authorization: Bearer <token>"

# 5) Donor response (secure link in the SMS, or with a donor token)
curl -s -X POST localhost:8000/api/v1/notifications/<notification_id>/response \
  -H "Authorization: Bearer <donor_token>" -H 'Content-Type: application/json' \
  -d '{"response":"interested","eta_minutes":18}'
```

Demo activation prerequisites: `COMPATIBILITY_POLICY=demo` and `SMS_PROVIDER=mock`
(defaults in `.env.example`).

## 5. Hard limits (all locked in code and tests)

- Phone numbers, OTP codes, tokens and coordinates never appear in any log; the OTP code is only
  hashed and never passes through the broker.
- The centre panel never receives a donor's phone, name or coordinates; only the anonymous
  `donor_reference`.
- Revoking location consent deletes the location record.
- No clinical rules are built; type matching is declared-only and labelled `demo`.
- Staged dispatch with idempotency keys; one-time donor response; stop on fulfilled/cancelled/expired.

## 6. Structure

```
backend/app/core        settings, security, errors, logging, dependencies
backend/app/db/models   models + state machines (Alembic autogenerate runs from here)
backend/app/schemas     {data,meta} envelope and section 9 shapes
backend/app/services    OTP, Matching, Dispatch, SMS, maps, audit, donor
backend/app/tasks       Celery worker/beat
backend/app/api/v1      Sana's endpoints + the block registering Asra's routers
backend/scripts         seed_demo.py (demo data)
```

## 7. Git (document section 16)

- `main` is the stable version, `develop` is the integration branch — **Asra and Shaghayeq branch
  from `develop`**.
- Each person works on `feature/<name>` and merges into `develop` with `--no-ff`.
- Commits use Conventional Commits: `feat|fix|test|docs|chore(scope): why this change`.
- The remote is `https://github.com/ISanaSaki/BloodLink-AI`; `main` and `develop` are pushed there.
  `.env`, `.dev-outbox.log` and Celery runtime files are in `.gitignore` and only `.env.example`
  with placeholders is committed.
