"""Fetch RDS credentials from AWS Secrets Manager.

Used at startup to resolve DATABASE_SECRET_ARN into an asyncpg connection URL.
Also called lazily on connection failure to handle credential rotation.
"""
from __future__ import annotations

import json
import logging

import aioboto3

log = logging.getLogger(__name__)

_session = aioboto3.Session()


async def fetch_database_url(secret_arn: str) -> str:
    """Fetch the RDS secret JSON from Secrets Manager and build an asyncpg URL.

    Args:
        secret_arn: AWS Secrets Manager ARN for the RDS credentials secret.

    Returns:
        postgresql+asyncpg://user:password@host:port/dbname

    Raises:
        Exception: Propagates any Secrets Manager API errors to the caller
            (caught and translated to DBConnectionError in main.py lifespan).
    """
    async with _session.client("secretsmanager") as client:
        resp = await client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(resp["SecretString"])
    url = (
        f"postgresql+asyncpg://{secret['username']}:{secret['password']}"
        f"@{secret['host']}:{secret['port']}/{secret['dbname']}"
    )
    log.info("db_secret_fetched", extra={"host": secret["host"]})
    return url
