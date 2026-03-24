"""Wait for the database to be ready with all required tables.

Polls the PostgreSQL database until the connection succeeds and all
expected coordination tables exist. Intended for CI pipelines where
migrations are applied separately and the DB may take a moment to
become fully available.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import asyncpg

REQUIRED_TABLES = [
    "file_locks",
    "work_queue",
    "agent_sessions",
    "memory_episodic",
    "audit_log",
]

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:54322/postgres"


async def check_db(dsn: str) -> tuple[bool, str]:
    """Attempt to connect and verify required tables exist.

    Returns (success, message).
    """
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(dsn),
            timeout=5,
        )

        rows = await conn.fetch(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
        )
        existing = {row["tablename"] for row in rows}

        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if missing:
            return False, f"Missing tables: {', '.join(missing)}"

        return True, "All required tables found"
    except Exception as exc:  # noqa: BLE001
        return False, f"Connection error: {exc}"
    finally:
        if conn is not None:
            await conn.close()


async def wait_for_db(dsn: str, timeout: int) -> bool:
    """Poll the database until ready or timeout."""
    start = time.monotonic()
    attempt = 0

    while time.monotonic() - start < timeout:
        attempt += 1
        ok, msg = await check_db(dsn)
        elapsed = time.monotonic() - start

        if ok:
            print(f"[attempt {attempt}] DB ready after {elapsed:.1f}s — {msg}")
            return True

        print(f"[attempt {attempt}] {elapsed:.1f}s — {msg}")
        await asyncio.sleep(2)

    print(f"ERROR: Database not ready after {timeout}s")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for database readiness")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("POSTGRES_DSN", DEFAULT_DSN),
        help="PostgreSQL connection string (default: $POSTGRES_DSN or built-in default)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Maximum seconds to wait (default: 60)",
    )
    args = parser.parse_args()

    print(f"Waiting for database at {args.dsn} (timeout {args.timeout}s)...")
    ok = asyncio.run(wait_for_db(args.dsn, args.timeout))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
