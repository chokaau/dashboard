"""Integration tests: response shape contract verification — story 003-009, AC4–AC5.

Verifies that the PostgreSQL read path produces response shapes identical to
the Redis/S3 baseline snapshots captured in tests/fixtures/.

Contract rule: any field added or removed from the baseline causes these tests
to fail — preventing accidental breaking changes to the API contract.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(client, tenant_slug: str = "acme") -> dict[str, str]:
    token = client.mint_jwt(tenant_slug=tenant_slug, sub=f"user-{tenant_slug}")
    return {"Authorization": f"Bearer {token}"}


def _make_call(
    call_id: str,
    tenant_slug: str = "acme",
    env: str = "dev",
    status: str = "missed",
) -> "Call":
    from app.db.models import Call

    return Call(
        id=call_id,
        tenant_slug=tenant_slug,
        env=env,
        start_time=datetime(2026, 3, 1, 9, 15, 0, tzinfo=timezone.utc),
        duration_s=154,  # "2m 34s" — matches example in baseline
        status=status,
        intent=None,
        caller_name=None,
        phone_hash=None,
        needs_callback=False,
        summary=None,
        has_recording=False,
    )


def _make_billing_row(
    tenant_slug: str = "acme",
    env: str = "dev",
) -> "BillingUsage":
    from app.db.models import BillingUsage

    return BillingUsage(
        id=uuid.uuid4(),
        tenant_slug=tenant_slug,
        env=env,
        plan="trial",
        trial_start=datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc),
        trial_days=14,
        activation_status="none",
        product="",
    )


def _non_meta_keys(data: dict) -> set[str]:
    """Return keys from a dict that don't start with underscore (ignore fixture metadata)."""
    return {k for k in data.keys() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# AC4 — call list response shape matches baseline
# ---------------------------------------------------------------------------


async def test_response_shape_matches_redis_baseline(integration_client, db_session):
    """AC4 — PostgreSQL call list response has same top-level keys and types as
    call_list_baseline.json. No fields added, no fields removed.
    """
    baseline = json.loads((FIXTURES_DIR / "call_list_baseline.json").read_text())

    # Seed one call
    call = _make_call(call_id="example-call-001")
    db_session.add(call)
    await db_session.flush()

    headers = _auth(integration_client)
    resp = await integration_client.get("/api/calls", headers=headers)

    assert resp.status_code == 200
    body = resp.json()

    # Top-level keys must match baseline (ignoring underscore metadata keys)
    baseline_top_keys = _non_meta_keys(baseline)
    response_top_keys = set(body.keys())
    assert response_top_keys == baseline_top_keys, (
        f"Top-level key mismatch.\n"
        f"  Baseline:  {sorted(baseline_top_keys)}\n"
        f"  Response:  {sorted(response_top_keys)}"
    )

    # Type checks: calls is list, pagination is dict, stats is dict
    assert isinstance(body["calls"], list)
    assert isinstance(body["pagination"], dict)
    assert isinstance(body["stats"], dict)

    # Pagination shape
    pagination_keys = set(baseline["pagination"].keys())
    assert set(body["pagination"].keys()) == pagination_keys, (
        f"Pagination shape mismatch: {set(body['pagination'].keys())} != {pagination_keys}"
    )
    assert isinstance(body["pagination"]["page"], int)
    assert isinstance(body["pagination"]["pageSize"], int)
    assert isinstance(body["pagination"]["total"], int)

    # Stats shape
    stats_keys = set(baseline["stats"].keys())
    assert set(body["stats"].keys()) == stats_keys, (
        f"Stats shape mismatch: {set(body['stats'].keys())} != {stats_keys}"
    )

    # Each call object keys must match baseline call object keys
    assert len(body["calls"]) >= 1
    baseline_call_keys = set(baseline["calls"][0].keys())
    for call_item in body["calls"]:
        response_call_keys = set(call_item.keys())
        assert response_call_keys == baseline_call_keys, (
            f"Call object key mismatch.\n"
            f"  Baseline: {sorted(baseline_call_keys)}\n"
            f"  Response: {sorted(response_call_keys)}"
        )


# ---------------------------------------------------------------------------
# AC5 — billing response shape matches baseline
# ---------------------------------------------------------------------------


async def test_billing_response_shape_matches_baseline(integration_client, db_session):
    """AC5 — PostgreSQL billing response has same 6 fields as billing_baseline.json,
    with matching types. No extra fields added, no baseline fields removed.
    """
    baseline = json.loads((FIXTURES_DIR / "billing_baseline.json").read_text())
    baseline_keys = _non_meta_keys(baseline)

    row = _make_billing_row()
    db_session.add(row)
    await db_session.flush()

    headers = _auth(integration_client)

    from botocore.exceptions import ClientError

    s3 = MagicMock()
    s3.__aenter__ = AsyncMock(return_value=s3)
    s3.__aexit__ = AsyncMock(return_value=False)
    s3.get_object = AsyncMock(
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject"
        )
    )
    mock_session_s3 = MagicMock()
    mock_session_s3.client = MagicMock(return_value=s3)

    with patch("app.routes.billing.aioboto3.Session", return_value=mock_session_s3):
        resp = await integration_client.get("/api/billing", headers=headers)

    assert resp.status_code == 200
    body = resp.json()

    response_keys = set(body.keys())
    assert response_keys == baseline_keys, (
        f"Billing response key mismatch.\n"
        f"  Baseline:  {sorted(baseline_keys)}\n"
        f"  Response:  {sorted(response_keys)}"
    )

    # Type validation per baseline
    assert isinstance(body["plan"], str)
    assert isinstance(body["trialDaysRemaining"], int)
    assert isinstance(body["trialEndDate"], str)
    assert isinstance(body["isTrialExpired"], bool)
    assert isinstance(body["activationStatus"], str)
    assert isinstance(body["product"], str)

    # trialEndDate format: YYYY-MM-DD
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", body["trialEndDate"]), (
        f"trialEndDate format wrong: {body['trialEndDate']}"
    )
