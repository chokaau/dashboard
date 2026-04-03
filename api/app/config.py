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

    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_metadata_enabled: bool = True

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


def get_config() -> AppConfig:
    return AppConfig()
