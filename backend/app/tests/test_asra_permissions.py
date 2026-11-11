"""Cross-cutting access rules for Asra's endpoints (contract sections 9.7-9.9)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.enums import UserRole
from app.db.models.user import User
from conftest import make_phone

PREFIX = "/api/v1"


def _admin(db):
    user = User(phone=make_phone(), role=UserRole.ADMIN, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _request_payload(center_id):
    return {
        "center_id": str(center_id),
        "component_type": "red_cells",
        "blood_group": "O",
        "rh_factor": "positive",
        "units_needed": 2,
        "urgency": "urgent",
        "expires_at": (datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


UNAUTHENTICATED_CALLS = [
    ("get", "/centers", None),
    ("get", f"/centers/{uuid4()}", None),
    ("post", "/centers", {"name": "X", "address": "Y", "latitude": 35.7, "longitude": 51.4}),
    ("patch", f"/centers/{uuid4()}", {"name": "Z"}),
    ("post", "/blood-requests", _request_payload(uuid4())),
    ("get", "/blood-requests", None),
    ("get", f"/blood-requests/{uuid4()}", None),
    ("patch", f"/blood-requests/{uuid4()}", {"units_needed": 3}),
    ("post", f"/blood-requests/{uuid4()}/activate", None),
    ("post", f"/blood-requests/{uuid4()}/cancel", None),
    ("get", f"/blood-requests/{uuid4()}/responses", None),
    ("patch", "/donors/me/availability", {"status": "unavailable"}),
]


def test_endpoints_require_authentication(client):
    for method, path, body in UNAUTHENTICATED_CALLS:
        request = getattr(client, method)
        response = request(f"{PREFIX}{path}") if body is None else request(f"{PREFIX}{path}", json=body)
        assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_donor_cannot_manage_centres_or_requests(
    client, db, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor = donor_factory()
    headers = auth_headers(donor.user_id, UserRole.DONOR)

    centre_payload = {"name": "X", "address": "Y", "latitude": 35.7, "longitude": 51.4}
    assert client.post(f"{PREFIX}/centers", json=centre_payload, headers=headers).status_code == 403
    assert (
        client.patch(f"{PREFIX}/centers/{center.id}", json={"name": "X"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            f"{PREFIX}/blood-requests", json=_request_payload(center.id), headers=headers
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{PREFIX}/blood-requests/{request.id}", json={"units_needed": 4}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(f"{PREFIX}/blood-requests/{request.id}/activate", headers=headers).status_code
        == 403
    )
    assert (
        client.post(f"{PREFIX}/blood-requests/{request.id}/cancel", headers=headers).status_code
        == 403
    )
    assert (
        client.get(f"{PREFIX}/blood-requests/{request.id}/responses", headers=headers).status_code
        == 403
    )


def test_operator_is_isolated_to_their_own_centre(
    client, db, center_factory, request_factory, auth_headers
):
    center_a, owner_a = center_factory()
    center_b, _ = center_factory()
    request_a = request_factory(center_a, owner_a, status="active")
    request_b = request_factory(center_b, owner_a, status="active")
    headers = auth_headers(owner_a.id, owner_a.role)

    assert (
        client.patch(f"{PREFIX}/centers/{center_b.id}", json={"name": "X"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            f"{PREFIX}/blood-requests", json=_request_payload(center_b.id), headers=headers
        ).status_code
        == 403
    )
    assert (
        client.get(f"{PREFIX}/blood-requests/{request_b.id}", headers=headers).status_code == 403
    )
    assert (
        client.get(f"{PREFIX}/blood-requests/{request_b.id}/responses", headers=headers).status_code
        == 403
    )
    listing = client.get(f"{PREFIX}/blood-requests", headers=headers).json()["data"]
    assert {row["id"] for row in listing} == {str(request_a.id)}


def test_centre_detail_stays_public_but_hides_management_fields(
    client, center_factory, auth_headers
):
    _, owner_a = center_factory()
    center_b, _ = center_factory()
    response = client.get(
        f"{PREFIX}/centers/{center_b.id}", headers=auth_headers(owner_a.id, owner_a.role)
    )
    assert response.status_code == 200
    assert "is_verified" not in response.json()["data"]
