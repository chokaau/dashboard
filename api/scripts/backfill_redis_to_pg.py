"""Backfill script: Redis → PostgreSQL — story 003-006.

Reads all call data from Redis using SCAN of call_index:{ENV_SHORT}:* keys,
then bulk-upserts into PostgreSQL using ON CONFLICT DO NOTHING.

Safety guarantees:
  - IDEMPOTENT: safe to run multiple times. ON CONFLICT DO NOTHING means
    re-running will insert 0 rows for already-migrated data.
  - NO DELETES: Redis data is not touched. Phase 4 handles Redis cleanup.
  - CROSS-ENV GUARD: database hostname must contain ENV_SHORT to prevent
    accidentally running dev script against prod database.

Usage:
    ENV_SHORT=dev DATABASE_URL=postgresql+asyncpg://... REDIS_URL=redis://...
    uv run python scripts/backfill_redis_to_pg.py [--yes] [--dry-run]

Environment variables required:
    ENV_SHORT       — deployment environment: dev | demo | prod
    DATABASE_URL    — asyncpg connection URL to target PostgreSQL
    REDIS_URL       — Redis connection URL

Flags:
    --yes       Skip interactive confirmation prompt
    --dry-run   Scan and count without writing to PostgreSQL (implies --yes)

Exit codes:
    0  — success, all records migrated
    1  — error (validation failure, connection failure, partial failure)
    2  — success with skipped invalid records (safe to re-run)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()

VALID_ENVS = ("dev", "demo", "prod")
VALID_STATUSES = ("missed", "completed", "needs-callback")
BATCH_SIZE = 100


def _validate_inputs(env_short: str, database_url: str, redis_url: str) -> None:
    """Validate required env vars. Exits with code 1 on any failure."""
    errors: list[str] = []

    if env_short not in VALID_ENVS:
        errors.append(
            f"ENV_SHORT must be one of {VALID_ENVS}, got: {env_short!r}"
        )

    if not database_url:
        errors.append("DATABASE_URL must be set and non-empty")

    if not redis_url:
        errors.append("REDIS_URL must be set and non-empty")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    # Cross-env guard: database hostname must contain env_short
    try:
        parsed = urlparse(database_url)
        host = parsed.hostname or ""
        if env_short not in host:
            print(
                f"ERROR: Cross-env guard triggered. ENV_SHORT={env_short!r} "
                f"but database host {host!r} does not contain it. "
                "Potential environment mismatch.",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to parse DATABASE_URL: {exc}", file=sys.stderr)
        sys.exit(1)


def _confirm(env_short: str, database_url: str, redis_url: str) -> None:
    """Interactive confirmation prompt. Exits if user doesn't confirm."""
    db_host = urlparse(database_url).hostname or database_url
    redis_host = urlparse(redis_url).hostname or redis_url

    print()
    print("=" * 60)
    print("  Redis → PostgreSQL Backfill")
    print("=" * 60)
    print(f"  ENV:      {env_short}")
    print(f"  DB host:  {db_host}")
    print(f"  Redis:    {redis_host}")
    print("=" * 60)
    print()
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)


def _parse_call_hash(
    call_id: str,
    tenant_slug: str,
    env_short: str,
    meta: dict[str, str],
) -> "Call | None":
    """Convert a Redis hash to a Call ORM object.

    Returns None for invalid records (logged as backfill_record_skipped).
    """
    from app.db.models import Call

    status = meta.get("status", "")
    if status not in VALID_STATUSES:
        log.info(
            "backfill_record_skipped",
            call_id=call_id,
            tenant_slug=tenant_slug,
            invalid_status=status,
        )
        return None

    try:
        start_ts = float(meta.get("start_time", "0"))
        start_time = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    except (ValueError, TypeError):
        start_time = datetime.now(timezone.utc)

    try:
        duration_s = int(meta.get("duration_s", 0))
    except (ValueError, TypeError):
        duration_s = None

    return Call(
        id=call_id,
        tenant_slug=tenant_slug,
        env=env_short,
        start_time=start_time,
        duration_s=duration_s,
        status=status,
        intent=meta.get("intent") or None,
        caller_name=meta.get("caller_name") or None,
        phone_hash=meta.get("phone_hash") or None,
        needs_callback=meta.get("needs_callback", "false") == "true",
        summary=meta.get("summary") or None,
        has_recording=meta.get("has_recording", "false") == "true",
    )


async def _run_backfill(
    env_short: str,
    database_url: str,
    redis_url: str,
    dry_run: bool,
) -> int:
    """Main backfill loop. Returns exit code (0, 1, or 2)."""
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.db.repositories.calls import SQLAlchemyCallRepository

    redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    had_skipped = False
    exit_code = 0

    try:
        # SCAN for all call_index keys for this env
        pattern = f"call_index:{env_short}:*"
        cursor = 0
        index_keys: list[str] = []

        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            index_keys.extend(keys)
            if cursor == 0:
                break

        log.info("backfill_scan_complete", env=env_short, index_key_count=len(index_keys))

        for index_key in index_keys:
            # Extract tenant_slug from key: call_index:{env}:{tenant_slug}
            parts = index_key.split(":", 2)
            if len(parts) != 3:
                log.warning("backfill_unexpected_key", key=index_key)
                continue
            tenant_slug = parts[2]

            # Get all call_ids from the sorted set
            call_ids: list[str] = await redis_client.zrange(index_key, 0, -1)
            redis_count = len(call_ids)

            if dry_run:
                print(f"DRY RUN: would insert {redis_count} rows for tenant {tenant_slug}")
                continue

            # Process in batches of BATCH_SIZE
            total_inserted = 0
            total_skipped = 0

            for batch_start in range(0, len(call_ids), BATCH_SIZE):
                batch_ids = call_ids[batch_start:batch_start + BATCH_SIZE]
                calls_batch = []

                for call_id in batch_ids:
                    meta_key = f"call_meta:{env_short}:{tenant_slug}:{call_id}"
                    meta = await redis_client.hgetall(meta_key)
                    if not meta:
                        log.warning(
                            "backfill_record_skipped",
                            call_id=call_id,
                            tenant_slug=tenant_slug,
                            invalid_status="missing_hash",
                        )
                        total_skipped += 1
                        had_skipped = True
                        continue

                    call = _parse_call_hash(call_id, tenant_slug, env_short, meta)
                    if call is None:
                        total_skipped += 1
                        had_skipped = True
                        continue
                    calls_batch.append(call)

                if calls_batch:
                    async with session_factory() as session:
                        repo = SQLAlchemyCallRepository(session)
                        inserted = await repo.bulk_upsert(calls_batch)
                        await session.commit()
                        total_inserted += inserted

            # Post-backfill validation: compare Redis count with PG count
            async with session_factory() as session:
                from sqlalchemy import select, func
                from app.db.models import Call as CallModel
                pg_count_result = await session.execute(
                    select(func.count()).select_from(CallModel).where(
                        CallModel.tenant_slug == tenant_slug,
                        CallModel.env == env_short,
                    )
                )
                pg_count = pg_count_result.scalar_one()

            if pg_count < redis_count:
                log.warning(
                    "backfill_count_discrepancy",
                    tenant_slug=tenant_slug,
                    redis_count=redis_count,
                    pg_count=pg_count,
                    diff=redis_count - pg_count,
                )

            log.info(
                "backfill_complete",
                tenant_slug=tenant_slug,
                redis_count=redis_count,
                pg_count=pg_count,
                inserted_count=total_inserted,
                skipped_count=total_skipped,
            )

    except Exception as exc:
        log.error("backfill_error", error=str(exc))
        exit_code = 1
    finally:
        await redis_client.aclose()
        await engine.dispose()

    if exit_code == 0 and had_skipped:
        return 2
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill call data from Redis to PostgreSQL."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip interactive confirmation prompt"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and count without writing to PostgreSQL",
    )
    args = parser.parse_args()

    env_short = os.environ.get("ENV_SHORT", "")
    database_url = os.environ.get("DATABASE_URL", "")
    redis_url = os.environ.get("REDIS_URL", "")

    _validate_inputs(env_short, database_url, redis_url)

    if not args.yes and not args.dry_run:
        _confirm(env_short, database_url, redis_url)

    exit_code = asyncio.run(
        _run_backfill(
            env_short=env_short,
            database_url=database_url,
            redis_url=redis_url,
            dry_run=args.dry_run,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
