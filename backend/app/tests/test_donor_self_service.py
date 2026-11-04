"""DON-01/DON-02 scenarios: donor profile, consents and consent-gated location."""

from decimal import Decimal

PREFIX = "/api/v1"


def test_patch_profile_stores_only_allowed_fields(client, registered_donor):
    """DON-01"""
    response = client.patch(
        f"{PREFIX}/donors/me/profile",
        json={
            "blood_group": "O",
            "rh_factor": "positive",
            "last_donation_date": "2026-05-10",
            "sms_consent": True,
            "location_consent": True,
        },
        headers=registered_donor["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["blood_group"] == "O"
    assert data["rh_factor"] == "positive"
    assert data["last_donation_date"] == "2026-05-10"
    assert data["blood_type_verified"] is False
    assert data["sms_consent"] is True
    assert set(data) == {
        "donor_id",
        "blood_group",
        "rh_factor",
        "blood_type_verified",
        "last_donation_date",
        "sms_consent",
        "location_consent",
    }


def test_profile_completion_is_reported_on_users_me(client, registered_donor):
    assert client.get(f"{PREFIX}/users/me", headers=registered_donor["headers"]).json()["data"][
        "is_profile_complete"
    ] is False

    client.patch(
        f"{PREFIX}/donors/me/profile",
        json={"blood_group": "A", "rh_factor": "negative"},
        headers=registered_donor["headers"],
    )
    assert client.get(f"{PREFIX}/users/me", headers=registered_donor["headers"]).json()["data"][
        "is_profile_complete"
    ] is True


def test_donor_cannot_verify_own_blood_type(client, registered_donor):
    response = client.patch(
        f"{PREFIX}/donors/me/profile",
        json={"blood_type_verified": True},
        headers=registered_donor["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_blood_group_enum_is_enforced(client, registered_donor):
    response = client.patch(
        f"{PREFIX}/donors/me/profile", json={"blood_group": "YY"}, headers=registered_donor["headers"]
    )
    assert response.status_code == 422


def test_empty_profile_patch_is_rejected(client, registered_donor):
    assert client.patch(f"{PREFIX}/donors/me/profile", json={}, headers=registered_donor["headers"]).status_code == 422


def test_profile_requires_donor_role(client, center_factory, auth_headers):
    _, operator = center_factory()
    response = client.patch(f"{PREFIX}/donors/me/profile", json={"sms_consent": True}, headers=auth_headers(operator.id, operator.role))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_location_without_consent_is_not_stored(client, registered_donor, db):
    """DON-02: 403 and nothing is written."""
    from app.db.models.donor_location import DonorLocation

    response = client.patch(
        f"{PREFIX}/donors/me/location",
        json={"latitude": 33.4878, "longitude": 48.3558},
        headers=registered_donor["headers"],
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    db.expire_all()
    assert db.query(DonorLocation).count() == 0


def test_location_with_consent_is_stored_and_returned(client, registered_donor):
    client.patch(
        f"{PREFIX}/donors/me/profile",
        json={"location_consent": True},
        headers=registered_donor["headers"],
    )

    response = client.patch(
        f"{PREFIX}/donors/me/location",
        json={"latitude": 35.700000, "longitude": 51.400000},
        headers=registered_donor["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert Decimal(str(data["latitude"])) == Decimal("35.700000")
    assert Decimal(str(data["longitude"])) == Decimal("51.400000")
    assert data["location_consent"] is True

    second = client.patch(
        f"{PREFIX}/donors/me/location",
        json={"latitude": 35.71, "longitude": 51.41},
        headers=registered_donor["headers"],
    )
    assert second.status_code == 200
    assert Decimal(str(second.json()["data"]["latitude"])) == Decimal("35.710000")


def test_revoking_location_consent_deletes_stored_coordinates(client, registered_donor, db):
    from app.db.models.donor_location import DonorLocation

    client.patch(
        f"{PREFIX}/donors/me/profile",
        json={"location_consent": True},
        headers=registered_donor["headers"],
    )
    client.patch(
        f"{PREFIX}/donors/me/location",
        json={"latitude": 35.7, "longitude": 51.4},
        headers=registered_donor["headers"],
    )
    assert db.query(DonorLocation).count() == 1

    client.patch(
        f"{PREFIX}/donors/me/profile",
        json={"location_consent": False},
        headers=registered_donor["headers"],
    )
    db.expire_all()
    assert db.query(DonorLocation).count() == 0


def test_out_of_range_coordinates_are_rejected(client, registered_donor):
    client.patch(f"{PREFIX}/donors/me/profile", json={"location_consent": True}, headers=registered_donor["headers"])
    response = client.patch(
        f"{PREFIX}/donors/me/location",
        json={"latitude": 120, "longitude": 51.4},
        headers=registered_donor["headers"],
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "latitude"
