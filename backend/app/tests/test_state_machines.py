"""Section 15 state machines: illegal transitions are rejected, stop conditions are silent."""

import pytest
from sqlalchemy import select

from app.core.enums import BloodRequestStatus, NotificationStatus
from app.core.exceptions import Conflict
from app.db.models.blood_request import TRANSITIONS as REQUEST_TRANSITIONS
from app.db.models.notification import Notification
from app.db.models.notification import TRANSITIONS as NOTIFICATION_TRANSITIONS
from conftest import sent_messages

PREFIX = "/api/v1"
TERMINAL_REQUESTS = {
    BloodRequestStatus.FULFILLED,
    BloodRequestStatus.CANCELLED,
    BloodRequestStatus.EXPIRED,
}


def test_request_state_machine_matches_the_contract():
    assert REQUEST_TRANSITIONS[BloodRequestStatus.DRAFT] == frozenset(
        {BloodRequestStatus.ACTIVE, BloodRequestStatus.CANCELLED}
    )
    assert REQUEST_TRANSITIONS[BloodRequestStatus.ACTIVE] == TERMINAL_REQUESTS
    for terminal in TERMINAL_REQUESTS:
        assert REQUEST_TRANSITIONS[terminal] == frozenset()


def test_notification_state_machine_matches_the_contract():
    assert NOTIFICATION_TRANSITIONS[NotificationStatus.QUEUED] == frozenset(
        {NotificationStatus.SENT, NotificationStatus.FAILED, NotificationStatus.CANCELLED}
    )
    assert NOTIFICATION_TRANSITIONS[NotificationStatus.SENT] == frozenset(
        {NotificationStatus.DELIVERED, NotificationStatus.FAILED}
    )
    for terminal in (
        NotificationStatus.DELIVERED,
        NotificationStatus.FAILED,
        NotificationStatus.CANCELLED,
    ):
        assert NOTIFICATION_TRANSITIONS[terminal] == frozenset()


@pytest.mark.parametrize(
    ("start", "target", "is_allowed"),
    [
        (BloodRequestStatus.DRAFT, BloodRequestStatus.ACTIVE, True),
        (BloodRequestStatus.DRAFT, BloodRequestStatus.CANCELLED, True),
        (BloodRequestStatus.DRAFT, BloodRequestStatus.FULFILLED, False),
        (BloodRequestStatus.DRAFT, BloodRequestStatus.EXPIRED, False),
        (BloodRequestStatus.ACTIVE, BloodRequestStatus.EXPIRED, True),
        (BloodRequestStatus.ACTIVE, BloodRequestStatus.DRAFT, False),
        (BloodRequestStatus.FULFILLED, BloodRequestStatus.CANCELLED, False),
        (BloodRequestStatus.CANCELLED, BloodRequestStatus.ACTIVE, False),
        (BloodRequestStatus.EXPIRED, BloodRequestStatus.FULFILLED, False),
    ],
)
def test_request_transition_rules(
    db, center_factory, request_factory, start, target, is_allowed
):
    center, owner = center_factory()
    request = request_factory(center, owner, status=start.value)

    if not is_allowed:
        with pytest.raises(Conflict) as raised:
            request.transition_to(target)
        assert raised.value.details == [{"field": "status", "message": f"{start.value} -> {target.value}"}]
        assert request.status is start
        return

    request.transition_to(target)
    db.commit()
    db.refresh(request)
    assert request.status is target
    if target is BloodRequestStatus.ACTIVE:
        assert request.activated_at is not None


@pytest.mark.parametrize("final_status", ["cancelled", "expired", "fulfilled"])
def test_a_closed_call_never_sends_again(
    client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch, final_status
):
    """A late worker pickup must not ring a call the centre already stopped (section 15)."""
    from app.core.config import settings
    from app.services.notification_service import NotificationService

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=5)
    for _ in range(2):
        donor_factory()
    client.post(
        f"{PREFIX}/blood-requests/{request.id}/dispatch",
        headers=auth_headers(owner.id, owner.role),
    )

    db.expire_all()
    db.refresh(request)
    queued = db.scalars(
        select(Notification).where(
            Notification.request_id == request.id, Notification.status == NotificationStatus.QUEUED
        )
    ).all()
    assert len(queued) == 1

    request.transition_to(BloodRequestStatus(final_status))
    db.commit()

    service = NotificationService.build(db)
    assert service.send_batch(request.id, queued[0].batch_number) == 0
    assert len(sent_messages()) == 1, "no message may leave after the call is closed"


def test_dispatch_on_an_open_call_is_replayed_not_resent(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    """Section 15 + DSP-03: one donor/request/stage can never produce two messages."""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=5)
    donor = donor_factory()
    headers = auth_headers(owner.id, owner.role)

    for _ in range(3):
        client.post(f"{PREFIX}/blood-requests/{request.id}/dispatch", headers=headers)

    db.expire_all()
    rows = db.scalars(select(Notification).where(Notification.request_id == request.id)).all()
    assert len(rows) == 1
    assert rows[0].status is NotificationStatus.SENT
    assert len(sent_messages()) == 1


def test_terminal_notification_cannot_be_reopened(db, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    notification = Notification(
        request_id=request.id,
        donor_id=donor.id,
        channel="sms",
        status=NotificationStatus.CANCELLED,
        idempotency_key=f"sms:sm:{request.id}:{donor.id}:b1",
    )
    db.add(notification)
    db.commit()

    with pytest.raises(Conflict):
        notification.transition_to(NotificationStatus.SENT)
    assert notification.status is NotificationStatus.CANCELLED


def test_expired_request_blocks_a_pending_batch(
    client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch
):
    """Section 15: `expires_at` passing turns the call expired and cancels its queue."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "dispatch_batch_size", 1)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=5)
    for _ in range(2):
        donor_factory()
    client.post(
        f"{PREFIX}/blood-requests/{request.id}/dispatch",
        headers=auth_headers(owner.id, owner.role),
    )

    db.expire_all()
    db.refresh(request)
    batch_two = [
        row
        for row in db.scalars(select(Notification).where(Notification.request_id == request.id)).all()
        if row.batch_number == 2
    ][0]
    batch_two.request.expires_at = batch_two.request.expires_at.replace(
        year=batch_two.request.expires_at.year - 1
    )
    db.commit()

    from app.services.notification_service import NotificationService

    service = NotificationService.build(db)
    assert service.send_batch(request.id, 2) == 0

    db.expire_all()
    db.refresh(request)
    db.refresh(batch_two)
    assert request.status is BloodRequestStatus.EXPIRED
    assert batch_two.status is NotificationStatus.CANCELLED
