"""Applying every migration to an empty database must produce a usable schema.

This is the test whose absence let a five-migration cascade of silent failures
reach production. Every other migration test reads the ``.sql`` files as *text*;
none of them had PostgreSQL parse one. So a migration could reference a role,
table, or publication that did not exist and no test would notice — and when the
runner's first-run branch recorded the failure as success, neither would the
boot.

It creates its own throwaway database rather than reusing the shared integration
one, because "fresh" is the entire point: a database that already has the schema
cannot demonstrate that the migrations build it.

Requires a reachable PostgreSQL with the ``vector`` extension available and a
role permitted to CREATE DATABASE; skipped otherwise.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from src.migrations import discover_migrations, run_migrations

from .conftest import POSTGRES_DSN, _postgres_available

pytestmark = pytest.mark.integration

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


@pytest.fixture
async def fresh_database():
    """An empty database, dropped when the test finishes."""
    if not _postgres_available:
        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")

    name = f"migtest_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=5.0)
    try:
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        except asyncpg.InsufficientPrivilegeError:
            pytest.skip("role may not CREATE DATABASE")
    finally:
        await admin.close()

    try:
        yield _admin_dsn_for(name)
    finally:
        admin = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=5.0)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


async def test_every_migration_applies_to_an_empty_database(fresh_database) -> None:
    """No migration may be skipped, and none may fail.

    Before the fix this run "succeeded" while silently recording 000, 001, 002
    and 015 as applied after each had aborted.
    """
    try:
        applied = await run_migrations(fresh_database)
    except asyncpg.FeatureNotSupportedError as exc:
        if "vector" in str(exc):
            pytest.skip("pgvector extension not installed on this server")
        raise

    expected = [filename for _seq, filename, _path in discover_migrations()]
    assert applied == expected, (
        "Not every migration applied to an empty database. Missing: "
        f"{sorted(set(expected) - set(applied))}"
    )


async def test_fresh_database_has_the_objects_the_code_calls(fresh_database) -> None:
    """A migrated database must actually contain what the services dereference.

    Counting applied migrations is not enough — that count was 33 on a database
    missing half its schema. Ask the catalog instead.
    """
    try:
        await run_migrations(fresh_database)
    except asyncpg.FeatureNotSupportedError as exc:
        if "vector" in str(exc):
            pytest.skip("pgvector extension not installed on this server")
        raise

    conn = await asyncpg.connect(dsn=fresh_database, timeout=5.0)
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


async def test_audit_inserts_survive_the_notify_trigger(fresh_database) -> None:
    """An ``audit_log`` insert must succeed end to end on a fresh database.

    Migration 024 puts an AFTER INSERT trigger on ``audit_log`` that calls
    ``coordinator_notify()``. When 015 was silently skipped that function did
    not exist, so every audit write raised ``UndefinedFunctionError`` — and the
    audit service swallowed it. This is the narrowest check that both halves
    are in place: the ``delegated_from`` column (033) and the function the
    trigger needs (015).
    """
    try:
        await run_migrations(fresh_database)
    except asyncpg.FeatureNotSupportedError as exc:
        if "vector" in str(exc):
            pytest.skip("pgvector extension not installed on this server")
        raise

    conn = await asyncpg.connect(dsn=fresh_database, timeout=5.0)
    try:
        row = await conn.fetchrow(
            "INSERT INTO audit_log "
            "(agent_id, agent_type, operation, parameters, result, delegated_from) "
            "VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6) RETURNING id",
            "test-agent",
            "test_type",
            "migration_smoke_test",
            "{}",
            "{}",
            None,
        )
        assert row is not None and row["id"] is not None
    finally:
        await conn.close()
