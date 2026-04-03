"""TenantContext extraction FastAPI dependency — story-3-3.

Extracts tenant_slug, tenant_id, role, user_id EXCLUSIVELY from validated JWT claims.
Route handlers receive TenantContext — never a raw slug from URL or body.

Security invariants:
  - tenant_slug validated against ^[a-z0-9][a-z0-9\\-]{0,61}[a-z0-9]$ before any AWS call
  - Empty or absent tenant_slug → 403
  - custom:tenant_id not matching UUID v4 → 403
  - Unknown role → defaults to "staff", logs warning
"""

import re
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, Request

from app.logging_events import UNKNOWN_ROLE_DEFAULTED

log = structlog.get_logger()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,61}[a-z0-9]$")


# ---------------------------------------------------------------------------
# Lightweight identity — no tenant claims required (used by register endpoint)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserIdentity:
    """Minimal identity from JWT — no tenant required."""

    user_id: str  # Cognito sub
    email: str


def extract_user_identity(request: Request) -> UserIdentity:
    """Extract user identity from JWT without requiring tenant claims.

    Raises 401 if sub is absent; 403 if email is absent.
    Used by the register endpoint only.
    """
    claims: dict = getattr(request.state, "jwt_claims", {})
    user_id = claims.get("sub") or ""
    email = claims.get("email") or ""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not email:
        raise HTTPException(status_code=403, detail="Email claim missing from token")
    return UserIdentity(user_id=user_id, email=email)


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_VALID_ROLES: frozenset[str] = frozenset({"owner", "staff"})


@dataclass(frozen=True)
class TenantContext:
    """Immutable tenant context extracted from validated JWT claims."""

    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    email: str


def extract_tenant_context(request: Request) -> TenantContext:
    """FastAPI dependency: extract TenantContext from request.state.jwt_claims.

    Raises HTTPException 403 if any required claim is missing or invalid.
    """
    claims: dict = getattr(request.state, "jwt_claims", {})

    # tenant_slug — required, regex-validated
    tenant_slug: str = claims.get("custom:tenant_slug") or ""
    if not tenant_slug or not _SLUG_RE.match(tenant_slug):
        raise HTTPException(
            status_code=403,
            detail=(
                "Account not associated with a tenant. Contact support."
                if not tenant_slug
                else "Invalid tenant slug. Contact support."
            ),
        )

    # tenant_id — required, UUID v4
    tenant_id: str = claims.get("custom:tenant_id") or ""
    if not tenant_id or not _UUID4_RE.match(tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Invalid tenant configuration. Contact support.",
        )

    # role — optional, defaults to "staff" on unknown values
    raw_role: str = claims.get("custom:role") or ""
    if raw_role in _VALID_ROLES:
        role = raw_role
    else:
        role = "staff"
        if raw_role:
            log.warning(UNKNOWN_ROLE_DEFAULTED, raw_role=raw_role, tenant_slug=tenant_slug)

    user_id: str = claims.get("sub") or ""
    email: str = claims.get("email") or ""

    return TenantContext(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        role=role,
        email=email,
    )
