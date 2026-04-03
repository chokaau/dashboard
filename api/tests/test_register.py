"""Tests for dashboard-8: POST /api/auth/register endpoint.

TDD: Tests written before implementation.

Coverage:
  - Happy path: new user registers, returns 201 with tenant data
  - 409: user already has tenant (custom:tenant_id set in Cognito)
  - 400: missing required fields (business_name, owner_name, state)
  - 400: invalid state code (not an Australian state/territory)
  - 400: business_name too short / too long
  - 401: no JWT token
  - 403: JWT has no email claim
  - Slug generation: spaces, special chars, very long names
  - Slug uniqueness: HEAD returns 200 → appends suffix
  - S3 billing.json written correctly
  - S3 business.yaml written correctly
  - Cognito AdminGetUser failure propagates as 500
  - Cognito AdminUpdateUserAttributes failure propagates as 500
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_POOL_ID, mint_jwt


# ---------------------------------------------------------------------------
# Helpers — mock boto3 clients
# ---------------------------------------------------------------------------


def _make_cognito_mock(has_tenant: bool = False, get_user_fails: bool = False, update_fails: bool = False):
    """Return a mock aioboto3 Cognito IDP client context manager."""
    from botocore.exceptions import ClientError

    cognito = MagicMock()
    cognito.__aenter__ = AsyncMock(return_value=cognito)
    cognito.__aexit__ = AsyncMock(return_value=False)

    if get_user_fails:
        cognito.admin_get_user = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "InternalError", "Message": "Server Error"}},
                "AdminGetUser",
            )
        )
    else:
        attrs = []
        if has_tenant:
            attrs.append({"Name": "custom:tenant_id", "Value": "12345678-1234-4234-8234-123456789abc"})
        cognito.admin_get_user = AsyncMock(return_value={"UserAttributes": attrs})

    if update_fails:
        cognito.admin_update_user_attributes = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "InternalError", "Message": "Server Error"}},
                "AdminUpdateUserAttributes",
            )
        )
    else:
        cognito.admin_update_user_attributes = AsyncMock(return_value={})

    return cognito


def _make_s3_mock(slug_exists: bool = False, put_fails: bool = False):
    """Return a mock aioboto3 S3 client context manager."""
    from botocore.exceptions import ClientError

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)

    if slug_exists:
        # HEAD returns 200 (object exists) → slug collision
        s3.head_object = AsyncMock(return_value={"ContentLength": 10})
    else:
        s3.head_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        )

    if put_fails:
        s3.put_object = AsyncMock(
            side_effect=ClientError(
                {"Error": {"Code": "InternalError", "Message": "Server Error"}},
                "PutObject",
            )
        )
    else:
        s3.put_object = AsyncMock(return_value={})

    return s3


def _make_session(cognito_mock, s3_mock):
    """Wire cognito and s3 mocks into a single aioboto3 Session mock."""
    session = MagicMock()

    def _client(service, **kwargs):
        if service == "cognito-idp":
            return cognito_mock
        return s3_mock

    session.client = MagicMock(side_effect=_client)
    return session


_VALID_BODY = {
    "business_name": "Acme Plumbing",
    "owner_name": "Jane Smith",
    "state": "NSW",
}


# ---------------------------------------------------------------------------
# Auth / identity
# ---------------------------------------------------------------------------


def test_register_401_without_token(client):
    """No token → 401."""
    resp = client.post("/api/auth/register", json=_VALID_BODY)
    assert resp.status_code == 401


def test_register_403_no_email_claim(client):
    """JWT missing email claim → 403."""
    # Mint a JWT with no email by patching extract_user_identity
    token = mint_jwt(sub="user-no-email", email="")
    resp = client.post(
        "/api/auth/register",
        json=_VALID_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "Email claim missing" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_register_400_missing_business_name(client):
    """Missing business_name → 422 (Pydantic validation)."""
    token = mint_jwt(sub="u1", email="u@test.com")
    resp = client.post(
        "/api/auth/register",
        json={"owner_name": "Jane", "state": "VIC"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_register_400_missing_owner_name(client):
    """Missing owner_name → 422 (Pydantic validation)."""
    token = mint_jwt(sub="u1", email="u@test.com")
    resp = client.post(
        "/api/auth/register",
        json={"business_name": "Acme", "state": "QLD"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_register_400_invalid_state(client):
    """Invalid Australian state code → 422."""
    token = mint_jwt(sub="u1", email="u@test.com")
    resp = client.post(
        "/api/auth/register",
        json={"business_name": "Acme", "owner_name": "Jane", "state": "NY"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_register_400_business_name_too_short(client):
    """business_name of 1 char → 422."""
    token = mint_jwt(sub="u1", email="u@test.com")
    resp = client.post(
        "/api/auth/register",
        json={"business_name": "A", "owner_name": "Jane", "state": "SA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_register_400_business_name_too_long(client):
    """business_name > 100 chars → 422."""
    token = mint_jwt(sub="u1", email="u@test.com")
    resp = client.post(
        "/api/auth/register",
        json={"business_name": "A" * 101, "owner_name": "Jane", "state": "WA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 409 — user already has tenant
# ---------------------------------------------------------------------------


def test_register_409_user_already_has_tenant(client, app_no_redis):
    """User already has custom:tenant_id → 409 Conflict."""
    token = mint_jwt(sub="u1", email="existing@test.com")
    cognito = _make_cognito_mock(has_tenant=True)
    s3 = _make_s3_mock()
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_register_201_new_tenant(client, app_no_redis):
    """New user registers → 201 with tenant data."""
    token = mint_jwt(sub="new-user-sub", email="new@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(slug_exists=False)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "tenant_id" in body
    assert "tenant_slug" in body
    assert body["plan"] == "trial"
    assert body["trial_days"] == 14


def test_register_201_slug_from_business_name(client, app_no_redis):
    """Slug is derived from business_name."""
    token = mint_jwt(sub="u2", email="u2@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(slug_exists=False)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json={"business_name": "Blue Sky Pty Ltd", "owner_name": "Bob", "state": "VIC"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    slug = resp.json()["tenant_slug"]
    # Must be lowercase, no spaces
    assert slug == slug.lower()
    assert " " not in slug
    assert "blue" in slug


def test_register_writes_billing_json(client, app_no_redis):
    """billing.json written to S3 with correct keys."""
    token = mint_jwt(sub="u3", email="u3@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(slug_exists=False)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201

    # Find the billing.json put_object call
    billing_call = None
    for call in s3.put_object.call_args_list:
        key = call[1].get("Key", "")
        if "billing.json" in key:
            billing_call = call
            break

    assert billing_call is not None, "billing.json was not written to S3"
    body = json.loads(billing_call[1]["Body"])
    assert body["plan"] == "trial"
    assert body["trial_days"] == 14
    assert "trial_start" in body


def test_register_writes_business_yaml(client, app_no_redis):
    """business.yaml written to S3 with request data."""
    token = mint_jwt(sub="u4", email="u4@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(slug_exists=False)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201

    yaml_call = None
    for call in s3.put_object.call_args_list:
        key = call[1].get("Key", "")
        if "business.yaml" in key:
            yaml_call = call
            break

    assert yaml_call is not None, "business.yaml was not written to S3"
    yaml_body = yaml_call[1]["Body"]
    assert b"Acme Plumbing" in yaml_body
    assert b"Jane Smith" in yaml_body
    assert b"NSW" in yaml_body


def test_register_sets_cognito_attributes(client, app_no_redis):
    """AdminUpdateUserAttributes called with tenant_id, tenant_slug, role=owner."""
    token = mint_jwt(sub="u5", email="u5@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(slug_exists=False)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    cognito.admin_update_user_attributes.assert_called_once()
    call_kwargs = cognito.admin_update_user_attributes.call_args[1]
    attrs = {a["Name"]: a["Value"] for a in call_kwargs["UserAttributes"]}
    assert "custom:tenant_id" in attrs
    assert "custom:tenant_slug" in attrs
    assert attrs["custom:role"] == "owner"


# ---------------------------------------------------------------------------
# Slug uniqueness — collision handling
# ---------------------------------------------------------------------------


def test_register_slug_suffix_on_collision(client, app_no_redis):
    """When slug already exists in S3, a suffix is appended."""
    token = mint_jwt(sub="u6", email="u6@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    # First HEAD succeeds (collision), second HEAD raises 404 (unique)
    from botocore.exceptions import ClientError

    s3 = _make_s3_mock()
    call_count = {"n": 0}

    async def _head_side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"ContentLength": 10}  # collision
        raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")

    s3.head_object = AsyncMock(side_effect=_head_side_effect)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    slug = resp.json()["tenant_slug"]
    # Slug with suffix should still be valid (contain original base)
    assert "acme" in slug or "-" in slug


# ---------------------------------------------------------------------------
# AWS failure paths
# ---------------------------------------------------------------------------


def test_register_500_cognito_get_user_fails(client, app_no_redis):
    """AdminGetUser failure → 500."""
    token = mint_jwt(sub="u7", email="u7@test.com")
    cognito = _make_cognito_mock(get_user_fails=True)
    s3 = _make_s3_mock()
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 500


def test_register_500_cognito_update_fails(client, app_no_redis):
    """AdminUpdateUserAttributes failure → 500."""
    token = mint_jwt(sub="u8", email="u8@test.com")
    cognito = _make_cognito_mock(has_tenant=False, update_fails=True)
    s3 = _make_s3_mock()
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 500


def test_register_500_s3_put_fails(client, app_no_redis):
    """S3 PutObject failure → 500."""
    token = mint_jwt(sub="u9", email="u9@test.com")
    cognito = _make_cognito_mock(has_tenant=False)
    s3 = _make_s3_mock(put_fails=True)
    session = _make_session(cognito, s3)

    with patch("app.routes.register.aioboto3.Session", return_value=session):
        resp = client.post(
            "/api/auth/register",
            json=_VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Slug generation unit tests (direct import — no HTTP)
# ---------------------------------------------------------------------------


def test_slugify_spaces():
    from app.services.slug import slugify
    assert slugify("Acme Plumbing") == "acme-plumbing"


def test_slugify_special_chars():
    from app.services.slug import slugify
    assert slugify("Blue & Sky Pty. Ltd!") == "blue-sky-pty-ltd"


def test_slugify_already_lowercase():
    from app.services.slug import slugify
    assert slugify("simple") == "simple"


def test_slugify_max_length():
    from app.services.slug import slugify
    long_name = "A" * 100
    result = slugify(long_name)
    assert len(result) <= 63


def test_slugify_too_short_gets_fallback():
    from app.services.slug import slugify
    result = slugify("!")  # Only special chars → stripped to ""
    assert len(result) >= 2


def test_make_unique_slug_appends_suffix():
    from app.services.slug import make_unique_slug
    base = "acme-plumbing"
    result = make_unique_slug(base)
    assert result.startswith("acme-plumbing-")
    assert len(result) > len(base)


def test_make_unique_slug_truncates_long_base():
    from app.services.slug import make_unique_slug
    base = "a" * 60
    result = make_unique_slug(base)
    # Total must be ≤ 63: base[:58] + "-" + 4 hex chars = 63
    assert len(result) <= 63
