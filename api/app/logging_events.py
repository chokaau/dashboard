"""Structured log event constants — story-3-1."""

# Call events
CALL_LIST_FETCHED = "call_list_fetched"
CALL_DETAIL_FETCHED = "call_detail_fetched"

# Profile / config
PROFILE_UPDATED = "profile_updated"
CONFIG_RELOAD_POLLER_DEGRADED = "config_poller_degraded"

# Auth rejection reasons
AUTH_REJECTED = "auth_rejected"
SSE_TOKEN_MISSING = "sse_token_missing"
SSE_TOKEN_INVALID = "sse_token_invalid"
UNKNOWN_ROLE_DEFAULTED = "unknown_role_defaulted"

# Rate limiting
TENANT_RATE_LIMITED = "tenant_rate_limited"
RATE_LIMITER_UNAVAILABLE = "rate_limiter_unavailable"

# Redis
CALL_METADATA_REDIS_WRITE_FAILED = "call_metadata_redis_write_failed"
CALL_METADATA_WRITTEN = "call_metadata_written"
CALL_EVENT_PUBLISH_FAILED = "call_event_publish_failed"

# Recording
RECORDING_STREAM_INTERRUPTED = "recording_stream_interrupted"

# Health
DEPENDENCY_HEALTH_CHECK_FAILED = "dependency_health_check_failed"

# Registration
TENANT_REGISTERED = "tenant_registered"
