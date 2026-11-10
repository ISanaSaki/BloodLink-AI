# 0003 — Staged dispatch: Beat owns stage progression, not the sending task

- Status: accepted (2026-11-04) — Owner: Sana
- Context: document section 11.3 says the dispatch must be sent in stages and must not advance to
  the next stage before the response window ends. The initial implementation scheduled the next
  stage from `dispatch_notification_batch` itself with `apply_async(countdown=…)`. That design had
  two practical flaws: (a) in eager/test mode and in runs without Redis, all stages fired
  immediately; (b) a worker restart destroyed Celery's in-memory schedule and a stage was never
  sent.
- Decision:
  1. `dispatch_notification_batch(request_id, batch_number)` sends **exactly one stage** and builds
     no chain.
  2. Progression is read from the database state: `NotificationService.advance_due_batches(now)`
     releases, for each `active` non-expired request, the smallest `queued` stage once
     `now - max(updated_at of sent/delivered) >= DISPATCH_RESPONSE_WINDOW_MINUTES`.
  3. The Beat task `check-dispatch-timeout` runs `expire_overdue()` then `advance_due_batches()`
     every 60 seconds and calls `dispatch_notification_batch.delay(...)` for each dispatched
     `(request_id, batch_number)` pair.
  4. Stops are checked before sending: terminal/non-active/expired/fulfilled request → `send_batch`
     returns zero and sends no SMS (`test_state_machines.py` tests).
- Consequences:
  - The demo/tests work correctly without Redis, and a real `celery beat` runs the exact same path.
  - Task registration is done with explicit `imports` in `celery_app.py`;
    `autodiscover_tasks(["app.tasks"])` did not find the `notification_tasks` module and the worker
    started with an empty registry (tests stayed green). Two tests in `test_dispatch.py` lock this.
  - Maximum delay between two stages = response window + 60 seconds (Beat precision); acceptable for
    the MVP.
  - If Beat stays off, the next stage is not sent — this is intentional (careless sending is worse)
    and is noted in the README.
  - For `POST /blood-requests/{id}/cancel`, Asra only needs to call `cancel_pending_notifications`;
    the staging logic is not rewritten.
