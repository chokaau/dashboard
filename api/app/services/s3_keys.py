"""Shared S3 key builders and input validators.

Centralises patterns and key derivation functions used across multiple routes
to prevent duplication and ensure consistency.
"""

from __future__ import annotations

import re


# call_id validation pattern: alphanumeric + hyphen + underscore, 1-128 chars
_CALL_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-\_]{0,127}$")


def setup_complete_key(env_short: str, tenant_slug: str) -> str:
    """Return the S3 key for the tenant's setup_complete.json object."""
    return f"{env_short}/{tenant_slug}/setup_complete.json"
