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
import uuid
from dataclasses import dataclass
from typing import Literal

import structlog
from fastapi import HTTPException, Request

from app.logging_events import UNKNOWN_ROLE_DEFAULTED

log = structlog.get_logger()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,61}[a-z0-9]$")
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
