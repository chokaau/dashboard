"""Tests for app/db/secrets.py — story 002-002 AC1.

TDD: fetch_database_url must build the correct asyncpg connection URL
from the Secrets Manager JSON payload.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest

from app.db.secrets import fetch_database_url


_SECRET_PAYLOAD = {
    "username": "u",
    "password": "p",
    "host": "h",
    "port": 5432,
    "dbname": "db",
}
_EXPECTED_URL = "postgresql+asyncpg://u:p@h:5432/db"


@pytest.fixture
def mock_secretsmanager_client():
    """Mock aioboto3 Secrets Manager client returning a canned secret."""
    client = AsyncMock()
    client.get_secret_value = AsyncMock(return_value={
        "SecretString": json.dumps(_SECRET_PAYLOAD)
    })
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def test_fetch_database_url_builds_asyncpg_url(mock_secretsmanager_client):
    with patch("app.db.secrets._session") as mock_session:
        mock_session.client.return_value = mock_secretsmanager_client
        url = await fetch_database_url("arn:aws:secretsmanager:ap-southeast-2:123:secret:test")
    assert url == _EXPECTED_URL


async def test_fetch_database_url_calls_correct_secret_arn(mock_secretsmanager_client):
    secret_arn = "arn:aws:secretsmanager:ap-southeast-2:123:secret:my-secret"
    with patch("app.db.secrets._session") as mock_session:
        mock_session.client.return_value = mock_secretsmanager_client
        await fetch_database_url(secret_arn)
    mock_secretsmanager_client.get_secret_value.assert_called_once_with(SecretId=secret_arn)


async def test_fetch_database_url_uses_secretsmanager_service(mock_secretsmanager_client):
    with patch("app.db.secrets._session") as mock_session:
        mock_session.client.return_value = mock_secretsmanager_client
        await fetch_database_url("arn:aws:secretsmanager:ap-southeast-2:123:secret:test")
    mock_session.client.assert_called_once_with("secretsmanager")
