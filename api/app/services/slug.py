"""Slug generation utilities — dashboard-8.

Converts arbitrary business names to URL-safe tenant slugs.
"""

from __future__ import annotations

import re
import secrets


def slugify(name: str) -> str:
    """Convert business name to URL-safe slug.

    Rules:
    - Lowercase and strip surrounding whitespace
    - Replace any run of non-alphanumeric chars with a single hyphen
    - Strip leading/trailing hyphens
    - Truncate to 63 chars
    - If result is shorter than 2 chars, generate a random fallback
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:63]
    if len(slug) < 2:
        slug = f"tenant-{secrets.token_hex(4)}"
    return slug


def make_unique_slug(base_slug: str) -> str:
    """Append a 4-hex-char random suffix to resolve slug collisions.

    Total length is capped at 63: base[:58] + "-" + 4 hex chars.
    """
    suffix = secrets.token_hex(2)  # 4 hex chars
    return f"{base_slug[:58]}-{suffix}"
