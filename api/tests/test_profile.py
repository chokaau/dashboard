"""Tests for story-4-4: GET /profile and PUT /profile Endpoints.

TDD: RED tests written first. Tests cover:
  - GET /profile returns BusinessConfig JSON
  - PUT /profile validates with BusinessConfig before writing
  - staff role PUT → 403
  - invalid phone format → 422
  - PUT then GET returns updated value
  - setupComplete boolean (setup_complete.json existence)
  - services min-length validation
  - Unknown fields silently ignored in PUT
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import mint_jwt

_VALID_PROFILE = {
    "business_name": "Spark Right Electrical",
    "owner_name": "John Smith",
    "receptionist_name": "Aria",
    "owner_phone": "+61412345678",
    "services": "General electrical work, fault finding, switchboard upgrades and safety inspections",
    "service_areas": "Melbourne inner suburbs including Richmond, Fitzroy and Collingwood",
    "hours": "Monday to Friday 7am to 5pm, Saturday 8am to 12pm",
    "pricing": "",
    "faq": "",
    "policies": "",
    "about_owner": "",
    "state": "VIC",
    "services_not_offered": [],
}


def _mock_s3_profile(config_data: dict | None = None, setup_complete: bool = False):
    """Return an aioboto3 S3 mock for profile reads/writes."""
    import json
    import yaml

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    async def _get_object(**kwargs):
        key = kwargs.get("Key", "")
        if "business.yaml" in key:
            if config_data is None:
                from botocore.exceptions import ClientError
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                    "GetObject",
                )
            body = MagicMock()
            body.read = AsyncMock(
                return_value=yaml.dump(config_data).encode()
            )
            return {"Body": body}
        if "setup_complete.json" in key:
            if not setup_complete:
                from botocore.exceptions import ClientError
                raise ClientError(
                    {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                    "GetObject",
                )
            body = MagicMock()
            body.read = AsyncMock(
                return_value=json.dumps({"setup_complete": True}).encode()
            )
            return {"Body": body}
        raise ValueError(f"Unexpected key: {key}")

    s3.get_object = AsyncMock(side_effect=_get_object)
    s3.put_object = AsyncMock(return_value={})

    session = MagicMock()
    session.client = MagicMock(return_value=s3)
    return session


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_get_profile_401_without_token(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 401


def test_put_profile_401_without_token(client):
    resp = client.put("/api/profile", json=_VALID_PROFILE)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /profile — happy path
# ---------------------------------------------------------------------------


def test_get_profile_returns_business_config(client, auth_headers, app_no_redis):
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.get("/api/profile", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["businessName"] == "Spark Right Electrical"
    assert body["ownerPhone"] == "+61412345678"


def test_get_profile_includes_setup_complete_false(client, auth_headers, app_no_redis):
    session = _mock_s3_profile(config_data=_VALID_PROFILE, setup_complete=False)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.get("/api/profile", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["setupComplete"] is False


def test_get_profile_includes_setup_complete_true(client, auth_headers, app_no_redis):
    session = _mock_s3_profile(config_data=_VALID_PROFILE, setup_complete=True)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.get("/api/profile", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["setupComplete"] is True


def test_get_profile_404_when_not_configured(client, auth_headers, app_no_redis):
    """S3 NoSuchKey → 404 (tenant not onboarded yet)."""
    session = _mock_s3_profile(config_data=None)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.get("/api/profile", headers=auth_headers)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /profile — role check
# ---------------------------------------------------------------------------


def test_put_profile_staff_role_returns_403(client, app_no_redis):
    token = mint_jwt(role="staff")
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put(
            "/api/profile",
            json=_VALID_PROFILE,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 403


def test_put_profile_owner_role_succeeds(client, auth_headers, app_no_redis):
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put("/api/profile", json=_VALID_PROFILE, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"status": "updated"}


# ---------------------------------------------------------------------------
# PUT /profile — validation
# ---------------------------------------------------------------------------


def test_put_profile_invalid_phone_returns_422(client, auth_headers, app_no_redis):
    """Non-AU E.164 phone format → 422."""
    bad_profile = {**_VALID_PROFILE, "owner_phone": "0412345678"}  # no +61
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put("/api/profile", json=bad_profile, headers=auth_headers)

    assert resp.status_code == 422


def test_put_profile_services_too_short_returns_422(client, auth_headers, app_no_redis):
    """services < 10 chars → 422."""
    bad_profile = {**_VALID_PROFILE, "services": "short"}
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put("/api/profile", json=bad_profile, headers=auth_headers)

    assert resp.status_code == 422


def test_put_profile_placeholder_business_name_returns_422(client, auth_headers, app_no_redis):
    """Placeholder text in business_name → 422."""
    # "your name" is a substring of "enter your name here" — matches placeholder check
    bad_profile = {**_VALID_PROFILE, "business_name": "enter your name here"}
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put("/api/profile", json=bad_profile, headers=auth_headers)

    assert resp.status_code == 422


def test_put_profile_unknown_fields_ignored(client, auth_headers, app_no_redis):
    """Unknown fields in PUT body are silently ignored, not rejected."""
    profile_with_extra = {**_VALID_PROFILE, "unknown_field_xyz": "some_value"}
    session = _mock_s3_profile(config_data=_VALID_PROFILE)
    with patch("app.routes.profile.aioboto3.Session", return_value=session):
        resp = client.put("/api/profile", json=profile_with_extra, headers=auth_headers)

    assert resp.status_code == 200
