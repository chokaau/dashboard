"""BFF application configuration — story-3-1."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """All configuration from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AWS / Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    aws_region: str = "ap-southeast-2"

    # S3
    s3_config_bucket: str = ""
    s3_recordings_bucket: str = ""

    # Redis (rate limiting and SSE only — metadata reads removed in Phase 4)
    redis_url: str = "redis://localhost:6379"

    # SSE
    sse_ping_interval_seconds: int = 30
    sse_max_connection_seconds: int = 600
    sse_max_connections_per_tenant: int = 5

    # App
    root_path: str = ""
    maintenance_mode: bool = False
    env_short: str = "dev"
    service_name: str = "choka-dashboard-api"

    # CORS — origins that may call the BFF
    cors_origins: list[str] = [
        "https://app.choka.dev",
        "https://app.choka.com.au",
    ]

    # Rate limiting
    rate_limit_read_per_minute: int = 120
    rate_limit_write_per_minute: int = 20

    # CloudFront origin verify secret (set via Secrets Manager in ECS)
    cloudfront_origin_secret: str = ""

    # SNS alarms topic ARN — used for activation request notifications
    sns_alarms_topic_arn: str = ""

    # Database — PostgreSQL via RDS
    # Resolution order: database_secret_arn (prod/ECS) > database_url (local dev) > disabled
    database_secret_arn: str = ""   # AWS Secrets Manager ARN — injected as env var in ECS task definition
    database_url: str = ""          # Local dev only — direct connection URL bypasses Secrets Manager
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout: int = 10
    db_pool_recycle: int = 1800


def get_config() -> AppConfig:
    return AppConfig()
