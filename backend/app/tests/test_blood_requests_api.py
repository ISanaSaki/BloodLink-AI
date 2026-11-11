"""Blood request lifecycle endpoints contributed by Asra (contract section 9.8)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.api.v1.endpoints.dispatch import donor_reference
from app.core.enums import (
    BloodRequestStatus,
    DonorResponseType,
    NotificationChannel,
    NotificationStatus,
    UserRole,
)
from app.db.models.donor_response import DonorResponse
from app.db.models.notification import Notification
from app.db.models.user import User
from conftest import make_phone

PREFIX = "/api/v1"


def _admin(db):
    user = User(phone=make_phone(), role=UserRole.ADMIN, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _future() -> str:
    return (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past() -> str:
    return (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(center_id, **overrides):
    payload = {
        "center_id": str(center_id),
        "component_type": "red_cells",
        "blood_group": "O",
        "rh_factor": "positive",
        "units_needed": 2,
        "urgency": "urgent",
        "expires_at": _future(),
    }
    payload.update(overrides)
    return payload


def _seed_response(db, request, donor, answer, eta_minutes=None):
    notification = Notification(
        request_id=request.id,
        donor_id=donor.id,
        channel=NotificationChannel.SMS,
        idempotency_key=f"seeded-{uuid4().hex}",
        status=NotificationStatus.DELIVERED,
    )
    db.add(notification)
    db.flush()
    row = DonorResponse(
        notification_id=notification.id,
        response=answer,
        eta_minutes=eta_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------- create


def test_create_returns_draft_with_centre_summary(client, center_factory, auth_headers):
    center, owner = center_factory()
    response = client.post(
        f"{PREFIX}/blood-requests",
        json=_payload(center.id),
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["activated_at"] is None
    assert data["notes"] is None
    assert set(data["center"]) == {"id", "name", "address"}
    assert data["center"]["id"] == str(center.id)


def test_create_is_operator_only(client, db, center_factory, donor_factory, auth_headers):
    center, _ = center_factory()
    donor = donor_factory()
    admin = _admin(db)
    url = f"{PREFIX}/blood-requests"
    assert (
        client.post(
            url, json=_payload(center.id), headers=auth_headers(donor.user_id, UserRole.DONOR)
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json=_payload(center.id), headers=auth_headers(admin.id, UserRole.ADMIN)
        ).status_code
        == 403
    )


def test_create_rejects_inactive_centre(client, center_factory, auth_headers):
    center, owner = center_factory(is_active=False)
    response = client.post(
        f"{PREFIX}/blood-requests",
        json=_payload(center.id),
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 409


def test_create_rejects_foreign_centre(client, center_factory, auth_headers):
    center, _ = center_factory()
    _, other_owner = center_factory()
    response = client.post(
        f"{PREFIX}/blood-requests",
        json=_payload(center.id),
        headers=auth_headers(other_owner.id, other_owner.role),
    )
    assert response.status_code == 403


def test_create_validation(client, center_factory, auth_headers):
    center, owner = center_factory()
    headers = auth_headers(owner.id, owner.role)
    without_urgency = _payload(center.id)
    without_urgency.pop("urgency")
    cases = [
        _payload(center.id, units_needed=0),
        without_urgency,
        _payload(center.id, unexpected_field=True),
    ]
    for payload in cases:
        response = client.post(f"{PREFIX}/blood-requests", json=payload, headers=headers)
        assert response.status_code == 422, payload


def test_create_rejects_past_expiry(client, center_factory, auth_headers):
    center, owner = center_factory()
    response = client.post(
        f"{PREFIX}/blood-requests",
        json=_payload(center.id, expires_at=_past()),
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


# --------------------------------------------------------------------- list


def test_list_is_scoped_by_role(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center_a, owner_a = center_factory()
    center_b, _ = center_factory()
    draft = request_factory(center_a, owner_a, status="draft")
    active_a = request_factory(center_a, owner_a, status="active")
    active_b = request_factory(center_b, owner_a, status="active")
    donor = donor_factory()

    as_donor = client.get(
        f"{PREFIX}/blood-requests", headers=auth_headers(donor.user_id, UserRole.DONOR)
    ).json()["data"]
    assert {row["id"] for row in as_donor} == {str(active_a.id), str(active_b.id)}
    assert all("notes" not in row for row in as_donor)

    as_operator = client.get(
        f"{PREFIX}/blood-requests", headers=auth_headers(owner_a.id, owner_a.role)
    ).json()["data"]
    assert {row["id"] for row in as_operator} == {str(draft.id), str(active_a.id)}
    assert all("notes" in row for row in as_operator)

    as_admin = client.get(
        f"{PREFIX}/blood-requests", headers=auth_headers(_admin(db).id, UserRole.ADMIN)
    ).json()["data"]
    assert {row["id"] for row in as_admin} == {str(draft.id), str(active_a.id), str(active_b.id)}


def test_list_filters(client, db, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request_factory(center, owner, status="draft")
    request_factory(center, owner, status="active", component_type="plasma")
    headers = auth_headers(_admin(db).id, UserRole.ADMIN)
    url = f"{PREFIX}/blood-requests"

    by_status = client.get(url, params={"status_filter": "draft"}, headers=headers).json()["data"]
    assert len(by_status) == 1 and by_status[0]["status"] == "draft"
    by_component = client.get(url, params={"component_type": "plasma"}, headers=headers).json()["data"]
    assert len(by_component) == 1 and by_component[0]["component_type"] == "plasma"
    by_center = client.get(url, params={"center_id": str(center.id)}, headers=headers).json()["data"]
    assert len(by_center) == 2


def test_donor_status_filter_is_ignored(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request_factory(center, owner, status="draft")
    active = request_factory(center, owner, status="active")
    donor = donor_factory()
    data = client.get(
        f"{PREFIX}/blood-requests",
        params={"status": "draft"},
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    ).json()["data"]
    assert [row["id"] for row in data] == [str(active.id)]


# --------------------------------------------------------------------- detail


def test_detail_access_rules(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    draft = request_factory(center, owner, status="draft")
    active = request_factory(center, owner, status="active")
    donor = donor_factory()
    _, other_owner = center_factory()

    assert (
        client.get(
            f"{PREFIX}/blood-requests/{draft.id}",
            headers=auth_headers(donor.user_id, UserRole.DONOR),
        ).status_code
        == 404
    )
    visible = client.get(
        f"{PREFIX}/blood-requests/{active.id}",
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    ).json()["data"]
    assert visible["status"] == "active"
    assert "notes" not in visible

    managed = client.get(
        f"{PREFIX}/blood-requests/{draft.id}", headers=auth_headers(owner.id, owner.role)
    ).json()["data"]
    assert "notes" in managed

    assert (
        client.get(
            f"{PREFIX}/blood-requests/{draft.id}",
            headers=auth_headers(other_owner.id, other_owner.role),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"{PREFIX}/blood-requests/{uuid4()}", headers=auth_headers(owner.id, owner.role)
        ).status_code
        == 404
    )


# --------------------------------------------------------------------- patch


def test_patch_is_allowed_only_for_drafts(client, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    draft = request_factory(center, owner, status="draft")
    active = request_factory(center, owner, status="active")
    headers = auth_headers(owner.id, owner.role)

    updated = client.patch(
        f"{PREFIX}/blood-requests/{draft.id}", json={"units_needed": 5}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["units_needed"] == 5

    assert (
        client.patch(
            f"{PREFIX}/blood-requests/{active.id}", json={"units_needed": 5}, headers=headers
        ).status_code
        == 409
    )


def test_patch_validation(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    donor = donor_factory()
    url = f"{PREFIX}/blood-requests/{request.id}"

    assert client.patch(url, json={}, headers=auth_headers(owner.id, owner.role)).status_code == 422
    assert (
        client.patch(
            url, json={"unexpected_field": 1}, headers=auth_headers(owner.id, owner.role)
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url, json={"expires_at": _past()}, headers=auth_headers(owner.id, owner.role)
        ).status_code
        == 400
    )
    assert (
        client.patch(
            url, json={"units_needed": 3}, headers=auth_headers(donor.user_id, UserRole.DONOR)
        ).status_code
        == 403
    )


# --------------------------------------------------------------------- activate


def test_activate_sets_status_and_timestamp(client, db, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/activate",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "active"
    assert data["activated_at"] is not None
    db.refresh(request)
    assert request.status is BloodRequestStatus.ACTIVE


def test_activate_requires_verified_centre(client, center_factory, request_factory, auth_headers):
    center, owner = center_factory(verified=False)
    request = request_factory(center, owner, status="draft")
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/activate",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 409


def test_activate_rejects_expired_request(client, db, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft", minutes=-5)
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/activate",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 409
    db.refresh(request)
    assert request.status is BloodRequestStatus.DRAFT


def test_activate_twice_is_conflict(client, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/activate",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 409


def test_activate_requires_operator(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    donor = donor_factory()
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/activate",
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    )
    assert response.status_code == 403


# --------------------------------------------------------------------- cancel


def test_cancel_draft_and_reject_second_cancel(client, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")
    url = f"{PREFIX}/blood-requests/{request.id}/cancel"
    headers = auth_headers(owner.id, owner.role)

    cancelled = client.post(url, headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert client.post(url, headers=headers).status_code == 409


def test_cancel_stops_pending_notifications(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(6):
        donor_factory()
    headers = auth_headers(owner.id, owner.role)

    dispatched = client.post(f"{PREFIX}/blood-requests/{request.id}/dispatch", headers=headers)
    assert dispatched.status_code == 202, dispatched.text
    queued = db.scalars(
        select(Notification).where(
            Notification.request_id == request.id,
            Notification.status == NotificationStatus.QUEUED,
        )
    ).all()
    assert len(queued) == 1

    cancelled = client.post(f"{PREFIX}/blood-requests/{request.id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    remaining = db.scalars(
        select(Notification).where(
            Notification.request_id == request.id,
            Notification.status == NotificationStatus.QUEUED,
        )
    ).all()
    assert remaining == []


def test_cancel_terminal_status_is_conflict(client, center_factory, request_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="fulfilled")
    response = client.post(
        f"{PREFIX}/blood-requests/{request.id}/cancel",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 409


# --------------------------------------------------------------------- responses


def test_responses_are_anonymised(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_one = donor_factory()
    donor_two = donor_factory()
    _seed_response(db, request, donor_one, DonorResponseType.INTERESTED, eta_minutes=15)
    _seed_response(db, request, donor_two, DonorResponseType.UNAVAILABLE)

    response = client.get(
        f"{PREFIX}/blood-requests/{request.id}/responses",
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 2
    for row in data:
        assert set(row) == {"donor_reference", "response", "responded_at", "eta_minutes"}
    by_reference = {row["donor_reference"]: row for row in data}
    assert by_reference[donor_reference(donor_one.id)]["response"] == "interested"
    assert by_reference[donor_reference(donor_one.id)]["eta_minutes"] == 15
    assert by_reference[donor_reference(donor_two.id)]["response"] == "unavailable"
    assert by_reference[donor_reference(donor_two.id)]["eta_minutes"] is None
    assert response.json()["meta"]["total"] == 2


def test_responses_require_owner_or_admin(client, db, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor = donor_factory()
    _, other_owner = center_factory()
    url = f"{PREFIX}/blood-requests/{request.id}/responses"

    assert (
        client.get(url, headers=auth_headers(donor.user_id, UserRole.DONOR)).status_code == 403
    )
    assert (
        client.get(url, headers=auth_headers(other_owner.id, other_owner.role)).status_code == 403
    )
    admin = _admin(db)
    assert client.get(url, headers=auth_headers(admin.id, UserRole.ADMIN)).status_code == 200
    assert (
        client.get(
            f"{PREFIX}/blood-requests/{uuid4()}/responses",
            headers=auth_headers(owner.id, owner.role),
        ).status_code
        == 404
    )
