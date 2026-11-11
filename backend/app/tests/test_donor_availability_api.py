"""Donor availability endpoint contributed by Asra (contract section 9.9)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.enums import UserRole
from app.db.models.donor_profile import DonorProfile

PREFIX = "/api/v1"


def _window(**overrides):
    window = {
        "status": "available",
        "available_from": (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "available_until": (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    window.update(overrides)
    return window


def test_set_availability_window_creates_profile_on_demand(client, db, registered_donor):
    response = client.patch(
        f"{PREFIX}/donors/me/availability",
        json=_window(),
        headers=registered_donor["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == {
        "donor_id",
        "status",
        "available_from",
        "available_until",
        "updated_at",
    }
    assert data["status"] == "available"
    profile = db.scalar(select(DonorProfile))
    assert profile is not None
    assert str(profile.id) == data["donor_id"]


def test_available_requires_both_times(client, registered_donor):
    headers = registered_donor["headers"]
    without_until = _window()
    without_until.pop("available_until")
    without_from = _window()
    without_from.pop("available_from")
    for payload in (without_until, without_from):
        response = client.patch(f"{PREFIX}/donors/me/availability", json=payload, headers=headers)
        assert response.status_code == 422, payload


def test_window_must_be_ordered(client, registered_donor):
    headers = registered_donor["headers"]
    window = _window()
    reversed_window = _window(
        available_from=window["available_until"],
        available_until=window["available_from"],
    )
    equal_window = _window(
        available_from=window["available_from"],
        available_until=window["available_from"],
    )
    for payload in (reversed_window, equal_window):
        response = client.patch(f"{PREFIX}/donors/me/availability", json=payload, headers=headers)
        assert response.status_code == 422, payload


def test_unavailable_clears_times(client, registered_donor):
    response = client.patch(
        f"{PREFIX}/donors/me/availability",
        json={"status": "unavailable"},
        headers=registered_donor["headers"],
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "unavailable"
    assert data["available_from"] is None
    assert data["available_until"] is None


def test_unavailable_rejects_times(client, registered_donor):
    response = client.patch(
        f"{PREFIX}/donors/me/availability",
        json=_window(status="unavailable"),
        headers=registered_donor["headers"],
    )
    assert response.status_code == 422


def test_operator_cannot_set_availability(client, center_factory, auth_headers):
    _, owner = center_factory()
    response = client.patch(
        f"{PREFIX}/donors/me/availability",
        json={"status": "unavailable"},
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 403


def test_availability_gates_dispatch(client, db, center_factory, request_factory, donor_factory, auth_headers):
    donor = donor_factory(available=False)
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    operator_headers = auth_headers(owner.id, owner.role)
    url = f"{PREFIX}/blood-requests/{request.id}/dispatch"

    blocked = client.post(url, headers=operator_headers)
    assert blocked.status_code == 409

    donor_headers = auth_headers(donor.user_id, UserRole.DONOR)
    updated = client.patch(
        f"{PREFIX}/donors/me/availability", json=_window(), headers=donor_headers
    )
    assert updated.status_code == 200, updated.text

    dispatched = client.post(url, headers=operator_headers)
    assert dispatched.status_code == 202, dispatched.text
    assert dispatched.json()["data"]["candidate_count"] >= 1
