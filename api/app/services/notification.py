"""Notification service — dashboard-10.

Sends operator alerts via AWS SNS.
Uses the existing choka-infra-alarms topic ARN from AppConfig.
"""

from __future__ import annotations

import aioboto3
import structlog

log = structlog.get_logger()


async def notify_activation_request(
    sns_topic_arn: str,
    aws_region: str,
    tenant_slug: str,
    business_name: str,
    owner_name: str,
    state: str,
) -> None:
    """Publish an activation request notification to SNS.

    Raises on SNS publish failure — callers should catch and handle
    non-fatally so the activation request still succeeds.
    """
    if not sns_topic_arn:
        log.warning("sns_topic_arn_not_configured", tenant_slug=tenant_slug)
        return

    message = (
        f"New activation request:\n\n"
        f"Business: {business_name}\n"
        f"Owner: {owner_name}\n"
        f"State: {state}\n"
        f"Tenant: {tenant_slug}\n\n"
        f"Review and activate via voice-tenants workflow."
    )

    session = aioboto3.Session()
    async with session.client("sns", region_name=aws_region) as sns:
        await sns.publish(
            TopicArn=sns_topic_arn,
            Subject=f"Activation request: {tenant_slug}",
            Message=message,
        )

    log.info("activation_notification_sent", tenant_slug=tenant_slug)
