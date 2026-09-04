"""A real audit insert must reach a real PostgreSQL (issue #455).

The static check in ``tests/test_audit_schema_alignment.py`` compares the
payload against the migrations as text. This one closes the loop the issue
asked for: it drives ``AuditService`` over ``DirectPostgresClient`` so
PostgreSQL itself parses and executes the statement.

That distinction is the whole point. Every existing audit test mocks the
Supabase HTTP transport by URL prefix, so the payload was never checked against
a schema by anything — which is why a missing column went unnoticed for the
life of the table while callers were told ``success=True``.
"""

from __future__ import annotations

import pytest

from src.audit import AuditService

from .conftest import POSTGRES_DSN, _postgres_available

pytestmark = pytest.mark.integration


async def test_log_operation_actually_persists(postgres_db) -> None:
    """Synchronous path: the returned result must reflect the real insert.

    ``async_logging`` is bypassed here deliberately — on the fire-and-forget
    path ``log_operation`` returns ``success=True`` before the insert runs, so
    it cannot distinguish a write from a failure. Awaiting the insert is what
    makes this assertion mean anything.
    """
    service = AuditService(db=postgres_db)

    result = await service._insert_audit_entry(
        {
            "agent_id": "integ-audit-agent",
            "agent_type": "test_agent",
            "operation": "audit_insert_smoke_test",
            "parameters": {},
            "result": {},
            "duration_ms": 1,
            "success": True,
            "error_message": None,
            "delegated_from": None,
        }
    )

    assert result.success, (
        f"audit insert failed against real PostgreSQL: {result.error}. "
        f"Every audit write in production fails the same way."
    )
    assert result.entry_id


async def test_delegated_from_round_trips(postgres_db) -> None:
    """The column must actually store the delegating principal.

    Adding a column that silently drops its value would satisfy the schema
    check while still losing the fact that matters most about a delegated
    operation.
    """
    service = AuditService(db=postgres_db)

    result = await service._insert_audit_entry(
        {
            "agent_id": "integ-audit-delegate",
            "agent_type": "test_agent",
            "operation": "audit_delegation_smoke_test",
            "parameters": {},
            "result": {},
            "duration_ms": 1,
            "success": True,
            "error_message": None,
            "delegated_from": "integ-audit-principal",
        }
    )
    assert result.success, result.error

    rows = await service.query(
        agent_id="integ-audit-delegate",
        operation="audit_delegation_smoke_test",
        limit=5,
    )
    assert rows, "the row we just wrote is not queryable"
    assert rows[0].delegated_from == "integ-audit-principal"


async def test_drain_waits_for_fire_and_forget_writes(postgres_db, monkeypatch) -> None:
    """``drain()`` must make the async path observable.

    Without it a short-lived process can exit before the event loop ever runs
    the queued insert — indistinguishable, from the outside, from the write
    failing.

    ``async_logging`` is pinned explicitly rather than relying on its default:
    if ``AUDIT_ASYNC=false`` is set in the environment, ``log_operation``
    would await the insert synchronously, ``_pending`` would stay empty, and
    ``drain()`` would short-circuit at ``if not self._pending`` without ever
    exercising the fire-and-forget path this test exists to cover.
    """
    monkeypatch.setenv("AUDIT_ASYNC", "true")

    from src.config import reset_config

    reset_config()

    service = AuditService(db=postgres_db)

    await service.log_operation(
        agent_id="integ-audit-async",
        agent_type="test_agent",
        operation="audit_async_smoke_test",
    )
    await service.drain()

    rows = await service.query(
        agent_id="integ-audit-async",
        operation="audit_async_smoke_test",
        limit=5,
    )
    assert rows, "fire-and-forget audit write never landed"


def test_reset_db_closes_connections_orphaned_by_a_dead_event_loop() -> None:
    """The leak that hung ``test-integration`` for six hours (#463).

    pytest gives every test its own event loop. A fire-and-forget audit insert
    still in flight when that loop closes leaves its connection open on the
    server — in the observed case ``active``, waiting for a Sync that never
    arrives, holding RowExclusiveLock on ``audit_log`` inside an implicit
    transaction. The next app startup's migration pass (024 re-creates the
    ``audit_log`` trigger) then blocks on that lock forever.

    ``reset_db()`` used to drop the client reference and leak the pool. It must
    terminate it — and it must still manage that *after* the loop is gone,
    because that is when teardown runs: ``transport.abort()`` raises
    ``RuntimeError: Event loop is closed`` there and would leave the fds open.
    """
    if not _postgres_available:
        pytest.skip("PostgreSQL not running (start with: docker-compose up -d)")

    import asyncio

    import asyncpg

    from src import db as db_module
    from src.config import reset_config

    reset_config()
    db_module.reset_db()

    async def _backends_started_after(t0: object) -> int:
        conn = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=5.0)
        try:
            return int(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND backend_type = 'client backend' "
                    "AND pid <> pg_backend_pid() "
                    "AND backend_start >= $1",
                    t0,
                )
            )
        finally:
            await conn.close()

    async def _now() -> object:
        conn = await asyncpg.connect(dsn=POSTGRES_DSN, timeout=5.0)
        try:
            return await conn.fetchval("SELECT now()")
        finally:
            await conn.close()

    t0 = asyncio.run(_now())

    # Open the GLOBAL client's pool on a throwaway loop via a fire-and-forget
    # audit write, then close that loop without ever draining — exactly what a
    # test's teardown does to an insert still in flight.
    loop = asyncio.new_event_loop()
    try:

        async def _fire() -> None:
            await AuditService().log_operation(
                agent_id="orphan-probe", agent_type="test_agent", operation="orphan_probe"
            )
            await asyncio.sleep(0.3)  # let the pool come up; do not drain

        loop.run_until_complete(_fire())
    finally:
        loop.close()

    orphaned = asyncio.run(_backends_started_after(t0))
    assert orphaned >= 1, "the dead loop should have left the pool's connections open"

    db_module.reset_db()

    assert asyncio.run(_backends_started_after(t0)) == 0, (
        f"{orphaned} connection(s) survived reset_db() — the next migration "
        f"pass will block on whatever locks they hold"
    )
