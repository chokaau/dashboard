"""BillingConfig Pydantic model — story-4-5, dashboard-10.

Phase 1 only supports "trial" plan.
Reads billing.json from S3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BillingConfig(BaseModel):
    """Billing configuration — Phase 1 trial-only."""

    model_config = {"extra": "ignore"}

    plan: Literal["trial"]
    trial_start: datetime  # timezone-aware
    trial_days: int = 14
    activation_status: Literal["none", "pending", "active"] = "none"
    product: str = ""  # "voice" or "" (no product selected yet)
