"""Centre endpoints contributed by Asra (contract section 9.7)."""

from uuid import uuid4

from app.core.enums import UserRole
from app.db.models.blood_center import BloodCenter
from app.db.models.user import User
from conftest import make_phone

PREFIX = "/api/v1"


def _admin(db):
    user = User(phone=make_phone(), role=UserRole.ADMIN, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_payload(**overrides):
    payload = {
        "name": "Sample Centre",
        "address": "Tehran, Sample Street",
        "latitude": 35.7,
        "longitude": 51.4,
    }
    payload.update(overrides)
    return payload


def _move_center(db, center, latitude, longitude):
    center.latitude = latitude
    center.longitude = longitude
    db.commit()


def test_list_requires_auth(client):
    assert client.get(f"{PREFIX}/centers").status_code == 401


def test_list_shows_only_active_centres_without_management_fields(
    client, center_factory, donor_factory, auth_headers
):
    center_factory()
    center_factory(is_active=False)
    donor = donor_factory()

    response = client.get(
        f"{PREFIX}/centers", headers=auth_headers(donor.user_id, UserRole.DONOR)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert set(data[0]) == {
        "id",
        "name",
        "address",
        "latitude",
        "longitude",
        "phone",
        "opening_hours",
        "is_active",
    }


def test_list_geo_filters_by_radius_and_sorts_by_distance(
    client, db, center_factory, donor_factory, auth_headers
):
    near, _ = center_factory()
    far, _ = center_factory()
    _move_center(db, near, 35.700, 51.400)
    _move_center(db, far, 35.800, 51.400)
    donor = donor_factory()

    response = client.get(
        f"{PREFIX}/centers",
        params={"latitude": 35.710, "longitude": 51.400, "radius_km": 5},
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert [row["id"] for row in data] == [str(near.id)]
    assert data[0]["distance_km"] > 0
    assert response.json()["meta"]["total"] == 1


def test_list_radius_zero_keeps_only_the_exact_location(
    client, db, center_factory, donor_factory, auth_headers
):
    near, _ = center_factory()
    far, _ = center_factory()
    _move_center(db, near, 35.700, 51.400)
    _move_center(db, far, 35.800, 51.400)
    donor = donor_factory()

    response = client.get(
        f"{PREFIX}/centers",
        params={"latitude": 35.700, "longitude": 51.400, "radius_km": 0},
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert [row["id"] for row in data] == [str(near.id)]
    assert data[0]["distance_km"] == 0.0


def test_list_without_geo_has_no_distance_field(client, center_factory, donor_factory, auth_headers):
    center_factory()
    donor = donor_factory()
    data = client.get(
        f"{PREFIX}/centers", headers=auth_headers(donor.user_id, UserRole.DONOR)
    ).json()["data"]
    assert data and "distance_km" not in data[0]


def test_list_requires_latitude_and_longitude_together(
    client, center_factory, donor_factory, auth_headers
):
    center_factory()
    donor = donor_factory()
    response = client.get(
        f"{PREFIX}/centers",
        params={"latitude": 35.7},
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_list_rejects_out_of_range_coordinates(client, center_factory, donor_factory, auth_headers):
    center_factory()
    donor = donor_factory()
    response = client.get(
        f"{PREFIX}/centers",
        params={"latitude": 91, "longitude": 51.4},
        headers=auth_headers(donor.user_id, UserRole.DONOR),
    )
    assert response.status_code == 422


def test_detail_hides_is_verified_from_outsiders(client, center_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    donor = donor_factory()

    public = client.get(
        f"{PREFIX}/centers/{center.id}", headers=auth_headers(donor.user_id, UserRole.DONOR)
    ).json()["data"]
    assert "is_verified" not in public

    managed = client.get(
        f"{PREFIX}/centers/{center.id}", headers=auth_headers(owner.id, owner.role)
    ).json()["data"]
    assert managed["is_verified"] is True


def test_inactive_centre_is_hidden_from_outsiders_but_visible_to_owner(
    client, center_factory, donor_factory, auth_headers
):
    center, owner = center_factory(is_active=False)
    donor = donor_factory()
    url = f"{PREFIX}/centers/{center.id}"
    assert client.get(url, headers=auth_headers(donor.user_id, UserRole.DONOR)).status_code == 404
    assert client.get(url, headers=auth_headers(owner.id, owner.role)).status_code == 200


def test_detail_unknown_centre_is_404(client, donor_factory, auth_headers):
    donor = donor_factory()
    response = client.get(
        f"{PREFIX}/centers/{uuid4()}", headers=auth_headers(donor.user_id, UserRole.DONOR)
    )
    assert response.status_code == 404


def test_create_is_admin_only(client, db, center_factory, donor_factory, auth_headers):
    donor = donor_factory()
    _, owner = center_factory()
    url = f"{PREFIX}/centers"
    assert (
        client.post(
            url, json=_create_payload(), headers=auth_headers(donor.user_id, UserRole.DONOR)
        ).status_code
        == 403
    )
    assert (
        client.post(url, json=_create_payload(), headers=auth_headers(owner.id, owner.role)).status_code
        == 403
    )


def test_admin_creates_centre(client, db, auth_headers):
    admin = _admin(db)
    response = client.post(
        f"{PREFIX}/centers",
        json=_create_payload(),
        headers=auth_headers(admin.id, UserRole.ADMIN),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["name"] == "Sample Centre"
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert set(data) == {
        "id",
        "name",
        "address",
        "latitude",
        "longitude",
        "phone",
        "opening_hours",
        "is_active",
        "is_verified",
    }


def test_admin_can_assign_owner_operator(client, db, center_factory, auth_headers):
    admin = _admin(db)
    _, operator = center_factory()
    response = client.post(
        f"{PREFIX}/centers",
        json=_create_payload(owner_user_id=str(operator.id)),
        headers=auth_headers(admin.id, UserRole.ADMIN),
    )
    assert response.status_code == 201
    center = db.get(BloodCenter, response.json()["data"]["id"])
    assert center.owner_user_id == operator.id


def test_owner_must_be_a_valid_operator(client, db, center_factory, donor_factory, auth_headers):
    admin = _admin(db)
    donor = donor_factory()
    headers = auth_headers(admin.id, UserRole.ADMIN)
    for owner_user_id in (str(donor.user_id), str(uuid4())):
        response = client.post(
            f"{PREFIX}/centers",
            json=_create_payload(owner_user_id=owner_user_id),
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_create_validation(client, db, auth_headers):
    admin = _admin(db)
    headers = auth_headers(admin.id, UserRole.ADMIN)
    cases = [
        _create_payload(name=""),
        _create_payload(address=""),
        _create_payload(latitude=91),
        _create_payload(longitude=181),
        _create_payload(unexpected_field=True),
        {"name": "Only a name"},
    ]
    for payload in cases:
        response = client.post(f"{PREFIX}/centers", json=payload, headers=headers)
        assert response.status_code == 422, payload


def test_owner_can_edit_own_centre(client, center_factory, auth_headers):
    center, owner = center_factory()
    response = client.patch(
        f"{PREFIX}/centers/{center.id}",
        json={"name": "Renamed Centre"},
        headers=auth_headers(owner.id, owner.role),
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Renamed Centre"


def test_owner_cannot_change_verification_or_activation(client, center_factory, auth_headers):
    center, owner = center_factory()
    headers = auth_headers(owner.id, owner.role)
    for payload in ({"is_verified": False}, {"is_active": False}):
        response = client.patch(f"{PREFIX}/centers/{center.id}", json=payload, headers=headers)
        assert response.status_code == 403


def test_admin_can_verify_and_deactivate(client, db, center_factory, donor_factory, auth_headers):
    center, _ = center_factory()
    admin = _admin(db)
    donor = donor_factory()
    headers = auth_headers(admin.id, UserRole.ADMIN)

    verified = client.patch(f"{PREFIX}/centers/{center.id}", json={"is_verified": False}, headers=headers)
    assert verified.status_code == 200
    assert verified.json()["data"]["is_verified"] is False

    deactivated = client.patch(f"{PREFIX}/centers/{center.id}", json={"is_active": False}, headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["is_active"] is False

    listing = client.get(f"{PREFIX}/centers", headers=auth_headers(donor.user_id, UserRole.DONOR))
    assert listing.json()["data"] == []


def test_other_operator_cannot_edit(client, center_factory, auth_headers):
    center, _ = center_factory()
    _, other_owner = center_factory()
    response = client.patch(
        f"{PREFIX}/centers/{center.id}",
        json={"name": "Hijacked"},
        headers=auth_headers(other_owner.id, other_owner.role),
    )
    assert response.status_code == 403


def test_patch_validation(client, center_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    donor = donor_factory()
    url = f"{PREFIX}/centers/{center.id}"
    assert (
        client.patch(url, json={}, headers=auth_headers(owner.id, owner.role)).status_code == 422
    )
    assert (
        client.patch(
            url, json={"unexpected_field": 1}, headers=auth_headers(owner.id, owner.role)
        ).status_code
        == 422
    )
    assert (
        client.patch(
            url, json={"name": "X"}, headers=auth_headers(donor.user_id, UserRole.DONOR)
        ).status_code
        == 403
    )
    assert client.patch(f"{PREFIX}/centers/{uuid4()}", json={"name": "X"}, headers=auth_headers(owner.id, owner.role)).status_code == 404
