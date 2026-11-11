"""RES-01/RES-02: donors answer calls, answers stay final, and the call stops when full."""

from sqlalchemy import select

from app.core.enums import BloodRequestStatus, DonorResponseType, NotificationStatus
from app.db.models.donor_response import DonorResponse
from app.db.models.notification import Notification
from conftest import sent_messages

PREFIX = "/api/v1"


def dispatch(client, headers, request_id):
    return client.post(f"{PREFIX}/blood-requests/{request_id}/dispatch", headers=headers)


def answer(client, headers, notification_id, payload):
    return client.post(f"{PREFIX}/notifications/{notification_id}/response", json=payload, headers=headers)


def notifications_for(db, donor_id):
    return db.scalars(
        select(Notification)
        .where(Notification.donor_id == donor_id)
        .order_by(Notification.created_at, Notification.id)
    ).all()


def test_donor_sees_and_answers_open_call(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    """RES-01"""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    headers = auth_headers(donor.user_id, "donor")
    listing = client.get(f"{PREFIX}/notifications", headers=headers)
    assert listing.status_code == 200, listing.text
    items = listing.json()["data"]
    assert len(items) == 1
    assert items[0]["status"] == "sent"
    assert items[0]["response"] is None
    assert items[0]["request_id"] == str(request.id)
    assert items[0]["center_name"] == center.name

    answered = answer(client, headers, items[0]["id"], {"response": "interested", "eta_minutes": 18})
    assert answered.status_code == 201, answered.text
    data = answered.json()["data"]
    assert data == {
        "notification_id": items[0]["id"],
        "response": "interested",
        "responded_at": data["responded_at"],
    }
    assert data["responded_at"].endswith("Z")

    db.expire_all()
    stored = db.get(Notification, items[0]["id"])
    assert stored.response.response is DonorResponseType.INTERESTED
    assert stored.response.eta_minutes == 18


def test_response_is_final_and_only_for_its_own_donor(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=5)
    donor = donor_factory()
    other = donor_factory()
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    notification = notifications_for(db, donor.id)[0]
    headers = auth_headers(donor.user_id, "donor")

    assert answer(client, headers, notification.id, {"response": "unavailable"}).status_code == 201

    repeat = answer(client, headers, notification.id, {"response": "interested"})
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "CONFLICT"

    stranger = answer(
        client, auth_headers(other.user_id, "donor"), notification.id, {"response": "interested"}
    )
    assert stranger.status_code == 403

    missing = answer(client, headers, "5f0c8b1e-0000-4000-8000-000000000000", {"response": "interested"})
    assert missing.status_code == 404


def test_response_payload_is_validated_by_the_contract(client, donor_factory, auth_headers):
    donor = donor_factory()
    headers = auth_headers(donor.user_id, "donor")

    bad_value = answer(client, headers, donor.id, {"response": "maybe"})
    assert bad_value.status_code == 422
    assert bad_value.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad_value.json()["error"]["details"][0]["field"] == "response"

    extra_field = answer(client, headers, donor.id, {"response": "interested", "is_admin": True})
    assert extra_field.status_code == 422

    negative_eta = answer(client, headers, donor.id, {"response": "interested", "eta_minutes": -1})
    assert negative_eta.status_code == 422


def test_enough_interested_answers_fulfil_the_request_and_stop_the_queue(
    client, db, center_factory, request_factory, donor_factory, auth_headers, monkeypatch
):
    """Section 1.1 step 9 + DSP-04: the call ends as soon as the target is reached."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "dispatch_batch_size", 2)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=2)
    donors = {profile.id: profile for profile in (donor_factory() for _ in range(4))}
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    db.expire_all()
    rows = db.scalars(
        select(Notification)
        .where(Notification.request_id == request.id)
        .order_by(Notification.batch_number, Notification.created_at, Notification.id)
    ).all()
    assert len(rows) == 4
    assert [row.batch_number for row in rows] == [1, 1, 2, 2]
    assert len(sent_messages()) == 2

    for row in rows[:2]:
        donor = donors[row.donor_id]
        answered = answer(
            client, auth_headers(donor.user_id, "donor"), row.id, {"response": "interested"}
        )
        assert answered.status_code == 201

    db.expire_all()
    db.refresh(request)
    assert request.status is BloodRequestStatus.FULFILLED
    statuses = db.scalars(
        select(Notification.status)
        .where(Notification.request_id == request.id)
        .order_by(Notification.batch_number, Notification.created_at, Notification.id)
    ).all()
    assert list(statuses) == [
        NotificationStatus.SENT,
        NotificationStatus.SENT,
        NotificationStatus.CANCELLED,
        NotificationStatus.CANCELLED,
    ]
    assert len(sent_messages()) == 2, "fulfilment must not release another stage"


def test_unavailable_answer_does_not_fulfil(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    notification = notifications_for(db, donor.id)[0]
    answer(
        client,
        auth_headers(donor.user_id, "donor"),
        notification.id,
        {"response": "unavailable"},
    )

    db.expire_all()
    db.refresh(request)
    assert request.status is BloodRequestStatus.ACTIVE


def test_notifications_endpoint_is_donor_only(client, center_factory, auth_headers):
    center, owner = center_factory()

    assert client.get(f"{PREFIX}/notifications").status_code == 401

    forbidden = client.get(
        f"{PREFIX}/notifications", headers=auth_headers(owner.id, owner.role)
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


def test_notification_list_is_scoped_and_paginated(
    client, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    first_request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    other_donor = donor_factory()
    headers = auth_headers(donor.user_id, "donor")
    dispatch(client, auth_headers(owner.id, owner.role), first_request.id)

    second_request = request_factory(center, owner, status="active", units_needed=1)
    dispatch(client, auth_headers(owner.id, owner.role), second_request.id)

    page_one = client.get(
        f"{PREFIX}/notifications", params={"page": 1, "page_size": 1}, headers=headers
    ).json()
    assert page_one["meta"]["page"] == 1
    assert page_one["meta"]["page_size"] == 1
    assert page_one["meta"]["total"] == 2
    assert len(page_one["data"]) == 1
    assert page_one["data"][0]["request_id"] == str(second_request.id)

    page_two = client.get(
        f"{PREFIX}/notifications", params={"page": 2, "page_size": 1}, headers=headers
    ).json()
    assert page_two["data"][0]["request_id"] == str(first_request.id)

    other_view = client.get(
        f"{PREFIX}/notifications", headers=auth_headers(other_donor.user_id, "donor")
    ).json()
    assert {row["request_id"] for row in other_view["data"]} == {
        str(first_request.id),
        str(second_request.id),
    }


def test_notification_payload_leaks_no_private_donor_or_center_data(
    client, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    listing = client.get(f"{PREFIX}/notifications", headers=auth_headers(donor.user_id, "donor"))
    body = listing.text
    assert "Centre internal note" not in body
    assert donor.user.phone not in body
    assert "latitude" not in body
    assert "response_token" not in body
    assert set(listing.json()["data"][0]) == {
        "id",
        "request_id",
        "channel",
        "status",
        "created_at",
        "center_id",
        "center_name",
        "component_type",
        "blood_group",
        "rh_factor",
        "urgency",
        "expires_at",
        "response",
    }


def test_persisted_response_carries_no_contact_details(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    """RES-02 data layer: the answer row links a donor to a call and nothing more."""
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=3)
    donor = donor_factory()
    dispatch(client, auth_headers(owner.id, owner.role), request.id)

    notification = notifications_for(db, donor.id)[0]
    answer(
        client,
        auth_headers(donor.user_id, "donor"),
        notification.id,
        {"response": "interested", "eta_minutes": 25},
    )

    db.expire_all()
    row = db.scalar(select(DonorResponse).where(DonorResponse.notification_id == notification.id))
    assert row is not None
    assert row.donor_id == donor.id
    assert row.eta_minutes == 25
    assert donor.user.phone not in str(row.__dict__)
