"""Section 7 wire contract: envelope, error codes, request id, casing, pagination."""

import re
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app

PREFIX = "/api/v1"
ISO_ZULU = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

LEAD_OWNED_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/otp/request",
    "/api/v1/auth/otp/verify",
    "/api/v1/users/me",
    "/api/v1/donors/me/profile",
    "/api/v1/donors/me/location",
    "/api/v1/blood-requests/{request_id}/dispatch",
    "/api/v1/blood-requests/{request_id}/candidates",
    "/api/v1/notifications",
    "/api/v1/notifications/{notification_id}/response",
}


def test_success_responses_use_the_data_meta_envelope(client, registered_donor):
    response = client.get(f"{PREFIX}/users/me", headers=registered_donor["headers"])
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert set(body["meta"]) == {"request_id"}
    UUID(body["meta"]["request_id"])


def test_client_supplied_request_id_is_reused_everywhere(client):
    request_id = str(UUID("2f4a1b6c-7d9e-4a11-8b2f-0000000000aa"))
    response = client.get(f"{PREFIX}/health", headers={"X-Request-Id": request_id})

    assert response.headers["X-Request-Id"] == request_id
    assert response.json()["meta"]["request_id"] == request_id


def test_request_id_is_generated_when_absent(client):
    response = client.get(f"{PREFIX}/health")
    assert UUID(response.headers["X-Request-Id"])
    assert UUID(response.json()["meta"]["request_id"])


def test_error_responses_use_the_single_error_envelope(client):
    response = client.get(f"{PREFIX}/users/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "UNAUTHENTICATED"
    UUID(body["error"]["request_id"])


def test_unknown_route_and_unknown_resource_share_the_not_found_shape(client):
    missing_route = client.get(f"{PREFIX}/does-not-exist")
    assert missing_route.status_code == 404
    assert missing_route.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    missing_resource = client.get(f"{PREFIX}/blood-requests/{UUID(int=0)}/candidates")
    assert missing_resource.status_code == 401
    assert set(missing_resource.json()) == {"error"}


def test_validation_errors_are_per_field_with_the_frozen_code(client):
    response = client.post(f"{PREFIX}/auth/otp/request", json={"phone": "09121234567", "purpose": "register"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert {"field": "phone", "message": error["details"][0]["message"]} in error["details"]


def test_pagination_meta_defaults_and_maximum(client, center_factory, request_factory, donor_factory, auth_headers):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory()
    headers = auth_headers(owner.id, owner.role)

    default_page = client.get(
        f"{PREFIX}/blood-requests/{request.id}/candidates", headers=headers
    ).json()["meta"]
    assert default_page["page"] == 1
    assert default_page["page_size"] == 20
    assert default_page["total"] == 1

    over_limit = client.get(
        f"{PREFIX}/blood-requests/{request.id}/candidates", params={"page_size": 101}, headers=headers
    )
    assert over_limit.status_code == 422
    assert over_limit.json()["error"]["code"] == "VALIDATION_ERROR"


def test_json_names_are_snake_case_and_timestamps_are_utc_zulu(client, registered_donor):
    from conftest import make_phone

    verify_shape = client.post(
        f"{PREFIX}/auth/otp/request", json={"phone": make_phone(), "purpose": "login"}
    ).json()
    assert set(verify_shape["data"]) == {
        "challenge_id",
        "expires_in_seconds",
        "resend_after_seconds",
    }

    me = client.get(f"{PREFIX}/users/me", headers=registered_donor["headers"]).json()["data"]
    assert set(me) == {"id", "phone", "role", "is_active", "is_profile_complete"}
    UUID(me["id"])


def test_enum_values_are_lowercase_snake_case(
    client, center_factory, request_factory, donor_factory, auth_headers
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", units_needed=1)
    donor = donor_factory()
    client.post(
        f"{PREFIX}/blood-requests/{request.id}/dispatch",
        headers=auth_headers(owner.id, owner.role),
    )

    item = client.get(
        f"{PREFIX}/notifications", headers=auth_headers(donor.user_id, "donor")
    ).json()["data"][0]
    assert item["channel"] == "sms"
    assert item["status"] == "sent"
    assert item["component_type"] == "red_cells"
    assert item["urgency"] == "urgent"
    assert item["blood_group"] == "O"
    assert item["rh_factor"] == "positive"
    assert ISO_ZULU.match(item["created_at"])
    assert ISO_ZULU.match(item["expires_at"])


def test_internal_errors_never_leak_internals(client):
    def explode():
        raise ZeroDivisionError("secret internal detail")

    app.add_api_route("/api/v1/_boom", explode, methods=["GET"])
    try:
        raw_client = TestClient(app, raise_server_exceptions=False)
        response = raw_client.get("/api/v1/_boom")
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/api/v1/_boom"]

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text
    assert "ZeroDivisionError" not in response.text


def test_openapi_documents_the_lead_owned_paths(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert LEAD_OWNED_PATHS <= set(paths)
    assert paths["/api/v1/auth/otp/request"]["post"]["responses"]["202"]["description"]
    assert paths["/api/v1/blood-requests/{request_id}/dispatch"]["post"]["responses"]["202"]


def test_cors_preflight_allows_the_frontend_origin(client):
    preflight = client.options(
        f"{PREFIX}/auth/otp/request",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5500"
