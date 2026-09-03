"""Applying every migration to an empty database must produce a usable schema.

This is the test whose absence let a five-migration cascade of silent failures
reach production (#456). Every other migration test reads the ``.sql`` files as
*text*; none of them had PostgreSQL parse one. So a migration could reference a
role, table, or publication that did not exist and no test would notice — and
when the runner's first-run branch recorded the failure as success, neither
would the boot.

It creates its own throwaway database rather than reusing the shared integration
one, because "fresh" is the entire point: a database that already has the schema
cannot demonstrate that the migrations build it.

Every database operation here is bounded by an explicit timeout. Creating and
dropping databases is the heaviest thing this suite asks of a shared server, and
an unbounded ``CREATE DATABASE`` can block indefinitely — on a template database
that still has sessions attached, or behind a lock this test cannot see. A test
that cannot finish is worse than one that fails, so infrastructure that will not
cooperate skips loudly here, and only the thing actually under test is allowed
to fail the build.

Requires a reachable PostgreSQL with the ``vector`` extension available and a
role permitted to CREATE DATABASE; skipped otherwise.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from src.migrations import discover_migrations, run_migrations

from .conftest import POSTGRES_DSN, _postgres_available

pytestmark = pytest.mark.integration

#: Seconds allowed for CREATE/DROP DATABASE. Generous for a copy of an empty
#: template, far short of a hang.
ADMIN_TIMEOUT = 60.0

#: Seconds allowed to apply every migration to an empty database. Takes ~1s on
#: stock PostgreSQL 16; the margin covers extension builds on heavier images.
MIGRATE_TIMEOUT = 180.0

#: Objects the coordinator's code paths dereference at runtime. Each one was
#: absent from a database the old runner reported as fully migrated.
REQUIRED_TABLES = [
    "agent_profile_assignments",
    "agent_profiles",
    "agent_sessions",
    "approval_queue",
    "audit_log",
    "file_locks",
    "work_queue",
]

REQUIRED_FUNCTIONS = [
    "check_guardrails",
    "claim_task",
    "coordinator_notify",
    "get_agent_profile",
    "is_domain_allowed",
]


@pytest.fixture(autouse=True)
def cleanup_tables():
    """Opt out of the package-wide truncation fixture.

    These tests build their own database from zero migrations, so they must not
    depend on the shared one already having the tables that fixture deletes
    from — that dependency is what this module exists to stop trusting.
    """
    yield


def _admin_dsn_for(database: str) -> str:
    base, _, _ = POSTGRES_DSN.rpartition("/")
    return f"{base}/{database}"


async def _connect(dsn: str) -> asyncpg.Connection:
    """Connect with both a connect timeout and a per-statement timeout.

    ``command_timeout`` is the one that matters: without it a statement that
    blocks on a lock waits forever and takes the whole job with it.
    """
    return await asyncpg.connect(dsn=dsn, timeout=10.0, command_timeout=ADMIN_TIMEOUT)


@pytest.fixture
async def migrated_database():
    """An empty database with every migration applied, dropped afterwards.

    Yields ``(dsn, applied_filenames)`` so each test can assert against one run
    rather than paying for its own.
    """
    if not _postgres_available:
        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")

    name = f"migtest_{uuid.uuid4().hex[:12]}"
    try:
        admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
    except (TimeoutError, OSError) as exc:
        pytest.skip(f"could not reach PostgreSQL to create a test database: {exc}")

    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    except asyncpg.InsufficientPrivilegeError:
        pytest.skip("role may not CREATE DATABASE")
    except (TimeoutError, asyncpg.QueryCanceledError) as exc:
        # A blocked CREATE DATABASE is an environment problem, not a defect in
        # the migrations. Skip loudly rather than hang or red the build.
        pytest.skip(f"CREATE DATABASE did not complete within {ADMIN_TIMEOUT}s: {exc}")
    finally:
        await admin.close()

    try:
        try:
            applied = await asyncio.wait_for(
                run_migrations(_admin_dsn_for(name)), timeout=MIGRATE_TIMEOUT
            )
        except asyncpg.FeatureNotSupportedError as exc:
            if "vector" in str(exc):
                pytest.skip("pgvector extension not installed on this server")
            raise
        except TimeoutError:
            pytest.fail(
                f"applying migrations to an empty database exceeded "
                f"{MIGRATE_TIMEOUT}s — it takes about a second normally"
            )
        yield _admin_dsn_for(name), applied
    finally:
        # Best effort: a failure to drop a throwaway database must not mask the
        # test's own result, and must not hang either.
        try:
            admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            finally:
                await admin.close()
        except Exception:  # noqa: BLE001 - cleanup is advisory
            pass


async def test_every_migration_applies_to_an_empty_database(migrated_database) -> None:
    """No migration may be skipped, and none may fail.

    Before the fix this run "succeeded" while silently recording 000, 001, 002
    and 015 as applied after each had aborted.
    """
    _dsn, applied = migrated_database

    expected = [filename for _seq, filename, _path in discover_migrations()]
    assert applied == expected, (
        "Not every migration applied to an empty database. Missing: "
        f"{sorted(set(expected) - set(applied))}"
    )


async def test_fresh_database_has_the_objects_the_code_calls(migrated_database) -> None:
    """A migrated database must actually contain what the services dereference.

    Counting applied migrations is not enough — that count was complete on a
    database missing half its schema. Ask the catalog instead.
    """
    dsn, _applied = migrated_database

    conn = await _connect(dsn)
    try:
        tables = {
            r["tablename"]
            for r in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        functions = {
            r["proname"]
            for r in await conn.fetch(
                "SELECT p.proname FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public'"
            )
        }
    finally:
        await conn.close()

    assert not [t for t in REQUIRED_TABLES if t not in tables], (
        f"missing tables: {[t for t in REQUIRED_TABLES if t not in tables]}"
    )
    assert not [f for f in REQUIRED_FUNCTIONS if f not in functions], (
        f"missing functions: {[f for f in REQUIRED_FUNCTIONS if f not in functions]}"
    )


async def test_audit_inserts_survive_the_notify_trigger(migrated_database) -> None:
    """An ``audit_log`` insert must survive the trigger on a fresh database.

    Migration 024 puts an AFTER INSERT trigger on ``audit_log`` that calls
    ``coordinator_notify()``. When 015 was silently skipped that function did
    not exist, so every audit write raised ``UndefinedFunctionError`` — and the
    audit service swallowed it. This is the narrowest check that the function
    the trigger needs is actually there.

    Note this insert omits ``delegated_from`` deliberately: that column is #455's
    fix, not this one's, so hardcoding it here would couple the two PRs.
    """
    dsn, _applied = migrated_database

    conn = await _connect(dsn)
    try:
        row = await conn.fetchrow(
            "INSERT INTO audit_log "
            "(agent_id, agent_type, operation, parameters, result) "
            "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb) RETURNING id",
            "test-agent",
            "test_type",
            "migration_smoke_test",
            "{}",
            "{}",
        )
        assert row is not None and row["id"] is not None
    finally:
        await conn.close()
