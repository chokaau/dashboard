"""Tests for extract_tenant_context dependency — story-3-3.

Decision table:
  tenant_slug   | tenant_id       | role    | expected outcome
  ------------- | --------------- | ------- | ----------------
  valid slug    | valid UUID4     | owner   | TenantContext populated
  valid slug    | valid UUID4     | staff   | TenantContext populated
  valid slug    | valid UUID4     | unknown | defaults to "staff", warning logged
  empty string  | valid UUID4     | owner   | 403 (account not associated)
  bad slug      | valid UUID4     | owner   | 403 (invalid tenant slug)
  valid slug    | not UUID4       | owner   | 403 (invalid tenant config)
  valid slug    | empty string    | owner   | 403 (invalid tenant config)
  valid slug    | UUID v1 format  | owner   | 403 (invalid tenant config)
  no claims     | —               | —       | 403
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.dependencies.tenant import TenantContext, extract_tenant_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app_with_claims(claims: dict) -> FastAPI:
    """Tiny app that injects raw claims and exposes TenantContext via route."""
    app = FastAPI()

    @app.get("/ctx")
    async def _ctx(request: Request):
        request.state.jwt_claims = claims
        ctx: TenantContext = extract_tenant_context(request)
        return {
            "user_id": ctx.user_id,
            "tenant_id": ctx.tenant_id,
            "tenant_slug": ctx.tenant_slug,
            "role": ctx.role,
            "email": ctx.email,
        }

    return app


_GOOD_CLAIMS = {
    "sub": "uid-001",
    "email": "alice@acme.com",
    "custom:tenant_slug": "acme",
    "custom:tenant_id": "12345678-1234-4234-8234-123456789abc",
    "custom:role": "owner",
}

_VALID_UUID4 = "12345678-1234-4234-8234-123456789abc"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_owner_context() -> None:
    with TestClient(_app_with_claims(_GOOD_CLAIMS), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_slug"] == "acme"
    assert body["tenant_id"] == _VALID_UUID4
    assert body["role"] == "owner"
    assert body["user_id"] == "uid-001"
    assert body["email"] == "alice@acme.com"


def test_valid_staff_context() -> None:
    claims = {**_GOOD_CLAIMS, "custom:role": "staff"}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200
    assert resp.json()["role"] == "staff"


def test_unknown_role_defaults_to_staff() -> None:
    claims = {**_GOOD_CLAIMS, "custom:role": "superadmin"}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200
    assert resp.json()["role"] == "staff"


def test_missing_role_defaults_to_staff() -> None:
    claims = {k: v for k, v in _GOOD_CLAIMS.items() if k != "custom:role"}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200
    assert resp.json()["role"] == "staff"


# ---------------------------------------------------------------------------
# Slug validation failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "",            # empty
        "A",           # uppercase (single char)
        "ALLCAPS",     # uppercase
        "has space",   # space
        "has_under",   # underscore
        "a",           # single char (too short — regex requires start+{0,61}+end ≥ 2 chars)
        "-starts-dash",  # starts with dash
        "ends-dash-",  # ends with dash
    ],
    ids=["empty", "uppercase_single", "all_caps", "space", "underscore", "single_char", "leading_dash", "trailing_dash"],
)
def test_invalid_slug_returns_403(slug: str) -> None:
    claims = {**_GOOD_CLAIMS, "custom:tenant_slug": slug}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "slug",
    [
        "acme",
        "my-tenant",
        "choka-voice-dashboard",
        "ab",          # 2 chars — minimum valid
        "a1",          # alphanumeric 2-char
    ],
    ids=["simple", "hyphenated", "long_valid", "two_chars", "alphanumeric_two"],
)
def test_valid_slug_passes(slug: str) -> None:
    claims = {**_GOOD_CLAIMS, "custom:tenant_slug": slug}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# tenant_id validation failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tenant_id",
    [
        "",                                          # empty
        "not-a-uuid",                               # no hyphens
        "12345678-1234-1234-1234-123456789abc",     # UUID v1, not v4
        "12345678-1234-4234-1234-123456789abc",     # v4 but variant bits wrong (1234 → must be [89ab]...)
        "XXXXXXXX-XXXX-4XXX-8XXX-XXXXXXXXXXXX",    # uppercase hex
    ],
    ids=["empty", "not_uuid", "uuid_v1", "bad_variant", "uppercase"],
)
def test_invalid_tenant_id_returns_403(tenant_id: str) -> None:
    claims = {**_GOOD_CLAIMS, "custom:tenant_id": tenant_id}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 403


def test_valid_uuid4_passes() -> None:
    claims = {**_GOOD_CLAIMS, "custom:tenant_id": "a1b2c3d4-e5f6-4a7b-8c9d-e0f1a2b3c4d5"}
    with TestClient(_app_with_claims(claims), raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# No claims at all
# ---------------------------------------------------------------------------


def test_no_jwt_claims_on_state_returns_403() -> None:
    app = FastAPI()

    @app.get("/ctx")
    async def _ctx(request: Request):
        # Don't set request.state.jwt_claims at all
        ctx = extract_tenant_context(request)
        return {"role": ctx.role}

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/ctx")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TenantContext is frozen / immutable
# ---------------------------------------------------------------------------


def test_tenant_context_is_frozen() -> None:
    ctx = TenantContext(
        user_id="u1",
        tenant_id=_VALID_UUID4,
        tenant_slug="acme",
        role="owner",
        email="u@acme.com",
    )
    with pytest.raises((AttributeError, TypeError)):
        ctx.role = "staff"  # type: ignore[misc]
