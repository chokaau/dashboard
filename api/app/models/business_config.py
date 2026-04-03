"""BusinessConfig Pydantic model — story-4-4.

Mirrors the voice backend BusinessConfig validators exactly.
Used by GET /profile and PUT /profile.

Field validators match voice/backend/app/config.py:BusinessConfig.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator
from pydantic import ValidationInfo

_AU_PHONE_RE = re.compile(r"^\+61[1-9]\d{8}$")
_PLACEHOLDERS = frozenset({"your name", "todo", "placeholder", "xxx", "tbd"})


class BusinessConfig(BaseModel):
    """Business identity config — loaded from / written to S3 business.yaml."""

    model_config = {"extra": "ignore"}  # unknown fields silently ignored

    business_name: str
    owner_name: str
    receptionist_name: str
    owner_phone: str
    services: str
    services_not_offered: list[str] = []
    service_areas: str
    hours: str
    pricing: str = ""
    faq: str = ""
    policies: str = ""
    about_owner: str = ""
    state: str = "VIC"

    @field_validator("business_name", "owner_name", "receptionist_name", "owner_phone")
    @classmethod
    def no_placeholders(cls, v: str, info: ValidationInfo) -> str:
        for p in _PLACEHOLDERS:
            if p in v.lower():
                raise ValueError(
                    f"{info.field_name} contains placeholder text: '{v}'"
                )
        return v

    @field_validator("owner_phone")
    @classmethod
    def valid_au_phone(cls, v: str, info: ValidationInfo) -> str:
        if not _AU_PHONE_RE.match(v):
            raise ValueError(
                f"owner_phone must be AU E.164 format (+61XXXXXXXXX), got: {v}"
            )
        return v

    @field_validator("business_name", "owner_name", "receptionist_name")
    @classmethod
    def reasonable_name_length(cls, v: str, info: ValidationInfo) -> str:
        if len(v) > 100:
            raise ValueError(
                f"{info.field_name} too long ({len(v)} chars, max 100)"
            )
        return v

    @field_validator("services", "service_areas", "hours")
    @classmethod
    def required_content_length(cls, v: str, info: ValidationInfo) -> str:
        if len(v) < 10:
            raise ValueError(
                f"{info.field_name} too short ({len(v)} chars, min 10)"
            )
        if len(v) > 20_000:
            raise ValueError(
                f"{info.field_name} too long ({len(v)} chars, max 20000)"
            )
        return v

    @field_validator("pricing", "faq", "policies", "about_owner")
    @classmethod
    def optional_content_length(cls, v: str, info: ValidationInfo) -> str:
        if len(v) > 20_000:
            raise ValueError(
                f"{info.field_name} too long ({len(v)} chars, max 20000)"
            )
        return v
