"""DSP-01..04 scenarios: dispatch, staged batches, idempotency and stop conditions."""

from uuid import UUID

from sqlalchemy import select

from app.core.enums import BloodRequestStatus, NotificationStatus
from app.db.models.notification import Notification
from conftest import sent_messages

PREFIX = "/api/v1"


def dispatch(client, headers, request_id):
    return client.post(f"{PREFIX}/blood-requests/{request_id}/dispatch", headers=headers)


def notifications_of(db, request_id):
    return db.scalars(
        select(Notification).where(Notification.request_id == request_id).order_by(Notification.batch_number)
    ).all()


def test_dispatch_rejected_for_draft_request(client, center_factory, request_factory, donor_factory, auth_headers):
    """DSP-01"""
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    donor_factory()

    response = dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_dispatch_returns_202_and_creates_queued_notifications(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    """DSP-02"""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    response = dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["request_id"] == str(request.id)
    assert data["status"] == "queued"
    assert data["candidate_count"] == 3
    assert data["first_batch_size"] == 3
    UUID(data["dispatch_id"])

    rows = notifications_of(db, request.id)
    assert len(rows) == 3
    assert all(row.status is NotificationStatus.SENT for row in rows)
    assert all(row.provider_message_id for row in rows)
    assert len(sent_messages()) == 3


def test_dispatch_is_staged_by_batch_size(
    client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    data = dispatch(client, auth_headers(owner.id, owner.role), request.id).json()["data"]
    assert data["first_batch_size"] == 1

    rows = notifications_of(db, request.id)
    assert [row.batch_number for row in rows] == [1, 2, 3]
    assert [row.status for row in rows] == [
        NotificationStatus.SENT,
        NotificationStatus.QUEUED,
        NotificationStatus.QUEUED,
    ]
    assert len(sent_messages()) == 1


def test_next_batch_is_sent_only_by_its_own_task(client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch):
    """Section 11.3 step 8: stages advance through the Celery task, not at dispatch time."""
    from app.core.config import settings
    from app.tasks.notification_tasks import dispatch_notification_batch

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert len(sent_messages()) == 1

    dispatch_notification_batch(str(request.id), 2)
    db.expire_all()
    assert len(sent_messages()) == 2
    assert [row.status for row in notifications_of(db, request.id)] == [
        NotificationStatus.SENT,
        NotificationStatus.SENT,
        NotificationStatus.QUEUED,
    ]


def test_beat_task_holds_next_stage_until_the_window_passes(
    client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch
):
    """Section 12.1: only the beat task releases a stage, and only after the response window."""
    from app.core.config import settings
    from app.tasks.notification_tasks import check_dispatch_timeout

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    monkeypatch.setattr(settings, "dispatch_response_window_minutes", 60)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    check_dispatch_timeout()
    db.expire_all()
    assert len(sent_messages()) == 1, "the window has not passed; nothing new may be sent"

    monkeypatch.setattr(settings, "dispatch_response_window_minutes", 0)
    check_dispatch_timeout()
    db.expire_all()
    assert len(sent_messages()) == 2
    assert [row.batch_number for row in notifications_of(db, request.id) if row.status is NotificationStatus.SENT] == [1, 2]


def test_beat_task_expires_overdue_requests(client, db, center_factory, request_factory):
    """Section 15: an active request past `expires_at` becomes expired without a dispatch."""
    from app.tasks.notification_tasks import check_dispatch_timeout

    center, owner = center_factory()
    request = request_factory(center, owner, status="active", minutes=-1)

    check_dispatch_timeout()
    db.expire_all()
    db.refresh(request)
    assert request.status is BloodRequestStatus.EXPIRED


def test_repeat_dispatch_does_not_duplicate_notifications(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    """DSP-03"""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(2):
        donor_factory()
    headers = auth_headers(owner.id, owner.role)

    dispatch(client, headers, request.id)
    assert len(sent_messages()) == 2

    second = dispatch(client, headers, request.id)
    assert second.status_code == 202
    db.expire_all()
    assert len(notifications_of(db, request.id)) == 2
    assert len(sent_messages()) == 2  # idempotency key blocked a second SMS


def test_dispatch_forbidden_for_other_center_operator(
    client, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory()
    _, stranger = center_factory()

    response = dispatch(client, auth_headers(stranger.id, stranger.role), request.id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_dispatch_forbidden_for_donor(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor = donor_factory()

    response = dispatch(client, auth_headers(donor.user_id, "donor"), request.id)
    assert response.status_code == 403


def test_dispatch_requires_authentication(client, center_factory, request_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")

    response = client.post(f"{PREFIX}/blood-requests/{request.id}/dispatch")
    assert response.status_code == 401


def test_dispatch_unknown_request_returns_404(client, center_factory, auth_headers):
    center, owner = center_factory()
    response = dispatch(client, auth_headers(owner.id, owner.role), UUID(int=0))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_expired_request_stops_before_sending(client, db, center_factory, request_factory, donor_factory, auth_headers):
    """Section 15: an overdue request becomes expired and its queue is cancelled."""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", minutes=-5)
    donor_factory()

    response = dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert response.status_code == 202

    db.expire_all()
    db.refresh(request)
    assert request.status is BloodRequestStatus.EXPIRED
    assert sent_messages() == []
    assert [row.status for row in notifications_of(db, request.id)] == [NotificationStatus.CANCELLED]


def test_unverified_center_cannot_dispatch(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory(verified=False)
    request = request_factory(center, owner, status="active")
    donor_factory()

    response = dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert response.status_code == 403


def test_no_eligible_candidate_conflicts(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory(blood_group="AB")

    response = dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["field"] == "candidates"


def test_cancel_pending_task_stops_remaining_batches(client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch):
    from app.core.config import settings
    from app.tasks.notification_tasks import cancel_pending_notifications

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    dispatch(client, auth_headers(owner.id, owner.role), request.id)
    assert len(sent_messages()) == 1

    cancel_pending_notifications(str(request.id), "cancelled_by_center")
    db.expire_all()
    statuses = [row.status for row in notifications_of(db, request.id)]
    assert statuses == [NotificationStatus.SENT, NotificationStatus.CANCELLED, NotificationStatus.CANCELLED]
    assert len(sent_messages()) == 1


def test_candidates_endpoint_hides_donor_pii(
    client, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donors = [donor_factory() for _ in range(2)]
    headers = auth_headers(owner.id, owner.role)

    body = client.get(f"{PREFIX}/blood-requests/{request.id}/candidates", headers=headers).json()
    items = body["data"]

    assert len(items) == 2
    assert set(items[0]) == {
        "donor_reference",
        "eta_minutes",
        "distance_km",
        "eligibility_check_status",
        "dispatch_stage",
    }
    assert items[0]["dispatch_stage"] == 1
    assert body["meta"]["total"] == 2
    for donor in donors:
        assert donor.user.phone not in str(body)
    assert str(donors[0].id) not in str(body)


def test_candidates_requires_active_request(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    donor_factory()

    response = client.get(f"{PREFIX}/blood-requests/{request.id}/candidates", headers=auth_headers(owner.id, owner.role))
    assert response.status_code == 409


def test_candidates_are_paginated(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(3):
        donor_factory()

    first = client.get(
        f"{PREFIX}/blood-requests/{request.id}/candidates",
        params={"page": 1, "page_size": 2},
        headers=auth_headers(owner.id, owner.role),
    ).json()
    assert len(first["data"]) == 2
    assert first["meta"] == {**first["meta"], "page": 1, "page_size": 2, "total": 3}

    too_large = client.get(
        f"{PREFIX}/blood-requests/{request.id}/candidates",
        params={"page_size": 500},
        headers=auth_headers(owner.id, owner.role),
    )
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "VALIDATION_ERROR"


def test_admin_may_dispatch_any_center(client, center_factory, request_factory, donor_factory, auth_headers):
    from app.core.enums import UserRole
    from app.db.models.user import User
    from app.db.session import SessionLocal

    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory()

    with SessionLocal() as session:
        admin = User(phone="+989120000001", role=UserRole.ADMIN, is_active=True)
        session.add(admin)
        session.commit()
        admin_id = admin.id

    response = dispatch(client, auth_headers(admin_id, UserRole.ADMIN), request.id)
    assert response.status_code == 202


def test_dispatch_does_not_expose_internal_notes(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory()

    body = dispatch(client, auth_headers(owner.id, owner.role), request.id).json()
    assert "یادداشت داخلی مرکز" not in str(body)
    assert "یادداشت داخلی مرکز" not in str(sent_messages())


def test_worker_imports_every_dispatch_task():
    """A worker started with `-A app.tasks.celery_app` must know these names, or the broker replies `unregistered task`."""
    from app.tasks.celery_app import celery_app
    from app.tasks.notification_tasks import CANCEL_PENDING, CHECK_TIMEOUT, DISPATCH_BATCH

    for name in (DISPATCH_BATCH, CHECK_TIMEOUT, CANCEL_PENDING):
        assert name in celery_app.tasks


def test_beat_schedule_runs_the_timeout_check():
    from app.tasks.celery_app import celery_app
    from app.tasks.notification_tasks import CHECK_TIMEOUT

    entries = [entry for entry in celery_app.conf.beat_schedule.values() if entry["task"] == CHECK_TIMEOUT]
    assert len(entries) == 1
    assert entries[0]["schedule"] > 0
