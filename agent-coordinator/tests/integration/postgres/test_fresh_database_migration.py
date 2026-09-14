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
import json
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
    "mutate_issue_if_unowned",
    "close_issues_if_unowned",
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


@pytest.fixture
async def pre039_upgrade_database(tmp_path):
    """A 038-era database upgraded through 039 with ambiguous labelled rows."""
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
    finally:
        await admin.close()

    dsn = _admin_dsn_for(name)
    pre039_dir = tmp_path / "pre039"
    post039_dir = tmp_path / "post039"
    pre039_dir.mkdir()
    post039_dir.mkdir()
    for sequence, filename, path in discover_migrations():
        if sequence < 39:
            (pre039_dir / filename).symlink_to(path)
        elif sequence == 39:
            (post039_dir / filename).symlink_to(path)

    try:
        await asyncio.wait_for(
            run_migrations(dsn, migrations_dir=pre039_dir), timeout=MIGRATE_TIMEOUT
        )
        conn = await _connect(dsn)
        try:
            legitimate_raw = await conn.fetchval(
                "SELECT submit_task('issue', 'Autopilot phase INIT', $1::jsonb, "
                "1, NULL::uuid[], NULL::timestamptz, NULL::jsonb, $2::text[])",
                json.dumps(
                    {
                        "change_id": "upgrade-legitimate",
                        "phase": "INIT",
                        "transition_sequence": 0,
                    }
                ),
                ["change:upgrade-legitimate", "projection:autopilot-phase"],
            )
            legitimate = json.loads(legitimate_raw)
            assert legitimate["success"] is True
            assert legitimate["created"] is True
            legitimate_id = uuid.UUID(legitimate["task_id"])
            spoof_id = await conn.fetchval(
                "INSERT INTO work_queue "
                "(task_type, description, input_data, priority, labels) "
                "VALUES ('issue', 'ordinary spoof', $1::jsonb, 5, $2::text[]) "
                "RETURNING id",
                json.dumps(
                    {
                        "change_id": "upgrade-spoof",
                        "phase": "PLAN",
                        "transition_sequence": 7,
                    }
                ),
                ["change:upgrade-spoof", "projection:autopilot-phase"],
            )
        finally:
            await conn.close()

        await asyncio.wait_for(
            run_migrations(dsn, migrations_dir=post039_dir), timeout=MIGRATE_TIMEOUT
        )
        yield dsn, legitimate_id, spoof_id
    finally:
        try:
            admin = await asyncio.wait_for(_connect(POSTGRES_DSN), timeout=ADMIN_TIMEOUT)
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            finally:
                await admin.close()
        except Exception:
            pass


async def test_039_upgrade_fails_closed_until_owner_registers_verified_row(
    pre039_upgrade_database,
) -> None:
    dsn, legitimate_id, spoof_id = pre039_upgrade_database
    labels = ["change:upgrade-legitimate", "projection:autopilot-phase"]
    conn = await _connect(dsn)
    try:
        ownership = await conn.fetch(
            "SELECT task_id FROM work_queue_projection_ownership ORDER BY task_id"
        )
        assert ownership == []

        collision_raw = await conn.fetchval(
            "SELECT submit_task('issue', 'Autopilot phase INIT', $1::jsonb, "
            "1, NULL::uuid[], NULL::timestamptz, NULL::jsonb, $2::text[])",
            json.dumps(
                {
                    "change_id": "upgrade-legitimate",
                    "phase": "INIT",
                    "transition_sequence": 0,
                }
            ),
            labels,
        )
        collision = json.loads(collision_raw)
        assert collision["success"] is False
        assert collision["reason"] == "projection_key_collision"

        reconcile_raw = await conn.fetchval(
            "SELECT reconcile_work_projection('upgrade-legitimate', 'PLAN', 1, "
            "'issue', 'Autopilot phase PLAN', '{}'::jsonb, 1, NULL::jsonb, "
            "$1::text[])",
            labels,
        )
        reconcile = json.loads(reconcile_raw)
        assert reconcile["success"] is False
        assert reconcile["reason"] == "projection_key_collision"
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM work_queue WHERE input_data->>'change_id'="
                "'upgrade-legitimate'"
            )
            == 1
        )
        assert await conn.fetchrow(
            "SELECT phase, transition_sequence FROM work_queue_projection_heads "
            "WHERE change_id='upgrade-legitimate'"
        ) == ("INIT", 0)

        await conn.execute(
            "INSERT INTO work_queue_projection_ownership(task_id) VALUES ($1)",
            legitimate_id,
        )
        replay_raw = await conn.fetchval(
            "SELECT reconcile_work_projection('upgrade-legitimate', 'PLAN', 1, "
            "'issue', 'Autopilot phase PLAN', '{}'::jsonb, 1, NULL::jsonb, "
            "$1::text[])",
            labels,
        )
        replay = json.loads(replay_raw)
        assert replay["success"] is True
        assert replay["created"] is True
        assert str(legitimate_id) in replay["cancelled_task_ids"]
        legitimate = await conn.fetchrow(
            "SELECT status, labels FROM work_queue WHERE id=$1", legitimate_id
        )
        assert legitimate["status"] == "cancelled"
        assert legitimate["labels"] == []

        spoof = await conn.fetchrow(
            "SELECT status, labels, result FROM work_queue WHERE id=$1", spoof_id
        )
        assert spoof["status"] == "pending"
        assert spoof["labels"] == [
            "change:upgrade-spoof",
            "projection:autopilot-phase",
        ]
        assert spoof["result"] is None
        assert (
            await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM work_queue_projection_ownership WHERE task_id=$1)",
                spoof_id,
            )
            is False
        )
    finally:
        await conn.close()


async def test_039_unlabelled_reconcile_fails_closed_on_reserved_upgrade_row(
    pre039_upgrade_database,
) -> None:
    dsn, _legitimate_id, spoof_id = pre039_upgrade_database
    conn = await _connect(dsn)
    try:
        result = json.loads(
            await conn.fetchval(
                "SELECT reconcile_work_projection('upgrade-spoof','IMPLEMENT',8,"
                "'issue','legacy caller','{}'::jsonb,1,NULL::jsonb,NULL::text[])"
            )
        )
        assert result["success"] is False
        assert result["reason"] == "projection_key_collision"
        assert await conn.fetchrow(
            "SELECT status,labels FROM work_queue WHERE id=$1", spoof_id
        ) == (
            "pending",
            ["change:upgrade-spoof", "projection:autopilot-phase"],
        )
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM work_queue_projection_heads WHERE change_id='upgrade-spoof'"
            )
            == 0
        )
    finally:
        await conn.close()


async def test_039_issue_mutation_fails_closed_on_reserved_upgrade_row(
    pre039_upgrade_database,
) -> None:
    dsn, _legitimate_id, spoof_id = pre039_upgrade_database
    conn = await _connect(dsn)
    try:
        result = json.loads(
            await conn.fetchval(
                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
                spoof_id,
                json.dumps({"status": "completed"}),
            )
        )
        assert result["success"] is False
        assert result["reason"] == "reserved_projection_label"
        assert await conn.fetchrow(
            "SELECT status,labels FROM work_queue WHERE id=$1", spoof_id
        ) == (
            "pending",
            ["change:upgrade-spoof", "projection:autopilot-phase"],
        )
    finally:
        await conn.close()


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


async def test_reserved_projection_rows_are_database_owned_and_issue_immutable(
    migrated_database,
) -> None:
    dsn, _applied = migrated_database
    change_id = "ordinary-issue-isolation"
    labels = [f"change:{change_id}", "projection:autopilot-phase"]
    conn = await _connect(dsn)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="reserved_projection_label"):
            await conn.execute(
                "INSERT INTO work_queue "
                "(task_type,description,input_data,priority,labels) "
                "VALUES ('issue','spoof','{}'::jsonb,5,$1::text[])",
                labels,
            )

        ordinary_id = await conn.fetchval(
            "INSERT INTO work_queue "
            "(task_type,description,input_data,priority,labels) "
            "VALUES ('issue','ordinary','{}'::jsonb,5,ARRAY[]::text[]) RETURNING id"
        )
        reserved_patch = json.loads(
            await conn.fetchval(
                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
                ordinary_id,
                json.dumps({"labels": labels}),
            )
        )
        assert reserved_patch == {
            "success": False,
            "reason": "reserved_projection_label",
        }

        projected = json.loads(
            await conn.fetchval(
                "SELECT reconcile_work_projection($1,'INIT',0,'issue',"
                "'Autopilot phase INIT','{}'::jsonb,1,NULL::jsonb,$2::text[])",
                change_id,
                labels,
            )
        )
        assert projected["success"] is True
        projection_id = uuid.UUID(projected["task_id"])
        assert (
            await conn.fetchval(
                "SELECT labels=$2::text[] FROM work_queue WHERE id=$1",
                projection_id,
                labels,
            )
            is True
        )

        immutable = json.loads(
            await conn.fetchval(
                "SELECT mutate_issue_if_unowned($1, $2::jsonb)",
                projection_id,
                json.dumps({"description": "tampered", "status": "completed"}),
            )
        )
        assert immutable == {
            "success": False,
            "reason": "projection_issue_immutable",
        }
        assert await conn.fetchrow(
            "SELECT description,status,labels FROM work_queue WHERE id=$1",
            projection_id,
        ) == ("Autopilot phase INIT", "pending", labels)

        second_ordinary_id = await conn.fetchval(
            "INSERT INTO work_queue "
            "(task_type,description,input_data,priority,labels) "
            "VALUES ('issue','second ordinary','{}'::jsonb,5,ARRAY[]::text[]) "
            "RETURNING id"
        )
        refused_batch = json.loads(
            await conn.fetchval(
                "SELECT close_issues_if_unowned($1::jsonb)",
                json.dumps(
                    {
                        "issue_ids": [
                            str(ordinary_id),
                            str(projection_id),
                            str(second_ordinary_id),
                        ],
                        "closed_at": "2026-09-14T14:00:00+00:00",
                        "reason": None,
                    }
                ),
            )
        )
        assert refused_batch == {
            "success": False,
            "reason": "projection_issue_immutable",
        }
        assert (
            await conn.fetchval("SELECT status FROM work_queue WHERE id=$1", ordinary_id)
            == "pending"
        )
        assert (
            await conn.fetchval("SELECT status FROM work_queue WHERE id=$1", second_ordinary_id)
            == "pending"
        )

        closed_batch = json.loads(
            await conn.fetchval(
                "SELECT close_issues_if_unowned($1::jsonb)",
                json.dumps(
                    {
                        "issue_ids": [str(ordinary_id), str(second_ordinary_id)],
                        "closed_at": "2026-09-14T14:00:00+00:00",
                        "reason": "batch complete",
                    }
                ),
            )
        )
        assert closed_batch["success"] is True
        assert [uuid.UUID(row["id"]) for row in closed_batch["issues"]] == [
            ordinary_id,
            second_ordinary_id,
        ]

        advanced = json.loads(
            await conn.fetchval(
                "SELECT reconcile_work_projection($1,'PLAN',1,'issue',"
                "'Autopilot phase PLAN','{}'::jsonb,1,NULL::jsonb,$2::text[])",
                change_id,
                labels,
            )
        )
        assert advanced["success"] is True
        assert (
            await conn.fetchval(
                "SELECT COUNT(*) FROM work_queue WHERE task_type='issue' "
                "AND status='pending' AND labels @> $1::text[]",
                labels,
            )
            == 1
        )
    finally:
        await conn.close()


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
            for r in await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
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


async def test_seeded_database_survives_the_first_run_pass(migrated_database) -> None:
    """A schema seeded out-of-band must not be corrupted by the bootstrap pass.

    CI and Docker apply the ``.sql`` files with psql, which leaves
    ``schema_migrations`` empty. The runner's first-run pass then RE-EXECUTES
    every migration and tolerates only "already applied" errors. Two things
    have to hold, and the second is the one that bit:

    * the pass must run to the end — 019's renames raise unique_violation on a
      seeded database, and if that stops the pass, 015 has already been
      re-executed and has clobbered 025's rewrite of
      ``notify_work_queue_change``, so ``claim_task`` then calls an ambiguous
      ``coordinator_notify`` overload (the test-integration failure on #464);
    * afterwards the schema must be exactly what 025 left behind.
    """
    dsn, _applied = migrated_database

    conn = await _connect(dsn)
    try:
        await conn.execute("DELETE FROM schema_migrations")  # simulate seeding
    finally:
        await conn.close()

    await asyncio.wait_for(run_migrations(dsn), timeout=MIGRATE_TIMEOUT)

    conn = await _connect(dsn)
    try:
        body = await conn.fetchval("SELECT pg_get_functiondef('notify_work_queue_change'::regproc)")
        recorded = await conn.fetchval("SELECT count(*) FROM schema_migrations")
    finally:
        await conn.close()

    assert "change_id" in body, (
        "015 re-ran over 025: notify_work_queue_change lost its change_id form, "
        "so claim_task now calls an ambiguous coordinator_notify overload"
    )
    assert recorded == len(discover_migrations()), (
        "the first-run pass stopped early and left migrations unrecorded"
    )
