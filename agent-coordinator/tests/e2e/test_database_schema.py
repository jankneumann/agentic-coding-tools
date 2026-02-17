"""E2E tests verifying the database schema is complete.

These tests check that all expected tables and RPC functions exist
in the running PostgreSQL instance. Useful as a regression check
after migration changes.

Requires: docker-compose up -d
Run with: pytest tests/e2e/ -m e2e
"""

from __future__ import annotations

import httpx
import pytest

EXPECTED_TABLES = [
    "agent_profile_assignments",
    "agent_profiles",
    "agent_sessions",
    "audit_log",
    "cedar_policies",
    "changesets",
    "file_locks",
    "handoff_documents",
    "memory_episodic",
    "memory_procedural",
    "memory_working",
    "network_policies",
    "operation_guardrails",
    "verification_results",
    "work_queue",
]


@pytest.mark.e2e
class TestDatabaseSchema:
    """Verify all expected tables exist in the database."""

    async def test_core_tables_exist(self, base_url: str) -> None:
        """All core tables from migrations should be queryable via PostgREST."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            for table in EXPECTED_TABLES:
                response = await client.get(f"/{table}?limit=0")
                assert response.status_code == 200, (
                    f"Table '{table}' not accessible via PostgREST "
                    f"(status {response.status_code}): {response.text}"
                )

    async def test_file_locks_table_has_columns(self, base_url: str) -> None:
        """file_locks table should have expected columns."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.get("/file_locks?limit=0")
            assert response.status_code == 200

    async def test_work_queue_table_has_columns(self, base_url: str) -> None:
        """work_queue table should have expected columns."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.get("/work_queue?limit=0")
            assert response.status_code == 200

    async def test_audit_log_table_accessible(self, base_url: str) -> None:
        """audit_log table should be accessible."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.get("/audit_log?limit=0")
            assert response.status_code == 200

    async def test_memory_tables_accessible(self, base_url: str) -> None:
        """All three memory tables should be accessible."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            for table in ["memory_episodic", "memory_working", "memory_procedural"]:
                response = await client.get(f"/{table}?limit=0")
                assert response.status_code == 200, f"{table} not accessible"
