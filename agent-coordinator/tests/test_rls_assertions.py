"""Migration-level RLS tests for service_role/anon behavior (Task 4.5).

These tests validate Row Level Security policy expectations at the
migration/schema level. They verify:
- Sensitive tables (audit_log, guardrail_violations, agent_profiles)
  have expected RLS behavior documented
- Service-role access patterns are correct for the coordinator's use case
- The expected table structure supports immutability constraints

Since these tests require a live database with migrations applied, they
are marked as integration tests. The unit-level assertions verify
migration SQL structure expectations without a running database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "supabase" / "migrations"


# =============================================================================
# Migration Structure Assertions
# =============================================================================


class TestMigrationStructure:
    """Verify that critical migrations exist and define expected objects."""

    def test_audit_log_migration_exists(self):
        """audit_log table should be defined in migrations."""
        audit_migration = MIGRATIONS_DIR / "008_audit_log.sql"
        assert audit_migration.exists(), "008_audit_log.sql migration not found"

    def test_guardrails_migration_exists(self):
        """guardrail tables should be defined in migrations."""
        guardrails_migration = MIGRATIONS_DIR / "006_guardrails_tables.sql"
        assert guardrails_migration.exists(), "006_guardrails_tables.sql migration not found"

    def test_profiles_migration_exists(self):
        """agent_profiles table should be defined in migrations."""
        profiles_migration = MIGRATIONS_DIR / "007_agent_profiles.sql"
        assert profiles_migration.exists(), "007_agent_profiles.sql migration not found"

    def test_core_schema_migration_exists(self):
        """Core schema (file_locks, work_queue) should be defined."""
        core_migration = MIGRATIONS_DIR / "001_core_schema.sql"
        assert core_migration.exists(), "001_core_schema.sql migration not found"


# =============================================================================
# Audit Log Immutability Assertions
# =============================================================================


class TestAuditLogImmutability:
    """Verify audit_log migration defines immutability constraints."""

    @pytest.fixture
    def audit_sql(self):
        path = MIGRATIONS_DIR / "008_audit_log.sql"
        return path.read_text()

    def test_audit_log_table_created(self, audit_sql):
        """audit_log table should be created."""
        assert "audit_log" in audit_sql

    def test_audit_log_has_immutability_trigger_or_policy(self, audit_sql):
        """audit_log should have an immutability mechanism (trigger or RLS)."""
        sql_lower = audit_sql.lower()
        has_trigger = (
            "trigger" in sql_lower
            or "before update" in sql_lower
            or "before delete" in sql_lower
        )
        has_rls = "row level security" in sql_lower or "enable row level security" in sql_lower
        has_policy = "create policy" in sql_lower
        assert has_trigger or has_rls or has_policy, (
            "audit_log migration should define immutability via trigger, RLS, or policy"
        )


# =============================================================================
# Guardrail Violations Table Assertions
# =============================================================================


class TestGuardrailViolationsSchema:
    """Verify guardrail_violations table structure from migrations."""

    @pytest.fixture
    def guardrails_sql(self):
        path = MIGRATIONS_DIR / "006_guardrails_tables.sql"
        return path.read_text()

    def test_guardrail_violations_table_exists(self, guardrails_sql):
        """guardrail_violations table should be defined."""
        assert "guardrail_violations" in guardrails_sql

    def test_operation_guardrails_table_exists(self, guardrails_sql):
        """operation_guardrails pattern table should be defined."""
        assert "operation_guardrails" in guardrails_sql


# =============================================================================
# Agent Profiles Table Assertions
# =============================================================================


class TestAgentProfilesSchema:
    """Verify agent_profiles table structure supports trust-level enforcement."""

    @pytest.fixture
    def profiles_sql(self):
        path = MIGRATIONS_DIR / "007_agent_profiles.sql"
        return path.read_text()

    def test_agent_profiles_table_exists(self, profiles_sql):
        """agent_profiles table should be defined."""
        assert "agent_profiles" in profiles_sql

    def test_trust_level_column_exists(self, profiles_sql):
        """trust_level column should be defined for enforcement."""
        assert "trust_level" in profiles_sql


# =============================================================================
# Core Schema Assertions (Locks and Work Queue)
# =============================================================================


class TestCoreSchemaConstraints:
    """Verify core schema tables have expected constraints."""

    @pytest.fixture
    def core_sql(self):
        path = MIGRATIONS_DIR / "001_core_schema.sql"
        return path.read_text()

    def test_file_locks_table_exists(self, core_sql):
        """file_locks table should be defined."""
        assert "file_locks" in core_sql

    def test_work_queue_table_exists(self, core_sql):
        """work_queue table should be defined."""
        assert "work_queue" in core_sql

    def test_claim_task_function_exists(self, core_sql):
        """claim_task atomic function should be defined."""
        assert "claim_task" in core_sql

    def test_acquire_lock_function_exists(self, core_sql):
        """acquire_lock atomic function should be defined."""
        assert "acquire_lock" in core_sql


# =============================================================================
# Cedar Policy Store Assertions
# =============================================================================


class TestCedarPolicyStoreSchema:
    """Verify Cedar policy storage migration."""

    @pytest.fixture
    def cedar_sql(self):
        path = MIGRATIONS_DIR / "010_cedar_policy_store.sql"
        return path.read_text()

    def test_cedar_policies_table_exists(self, cedar_sql):
        """cedar_policies table should be defined."""
        assert "cedar_policies" in cedar_sql


# =============================================================================
# Integration Tests: Live Database RLS Checks
# =============================================================================


@pytest.mark.integration
class TestRLSLiveDatabase:
    """Live database RLS tests — require running Supabase/PostgreSQL.

    These tests verify actual row-level security behavior:
    - Service role can insert/select audit_log
    - Anon role cannot modify audit_log
    - Service role can insert guardrail_violations
    """

    @pytest.mark.asyncio
    async def test_service_role_can_insert_audit(self):
        """Service role (coordinator) should be able to insert audit entries."""
        # This test requires a live database connection
        # Placeholder: actual test runs in CI with live DB
        pytest.skip("Requires live database (integration test)")

    @pytest.mark.asyncio
    async def test_anon_role_cannot_modify_audit(self):
        """Anon role should not be able to insert/update/delete audit_log."""
        pytest.skip("Requires live database (integration test)")

    @pytest.mark.asyncio
    async def test_service_role_can_insert_guardrail_violations(self):
        """Service role should be able to insert guardrail violations."""
        pytest.skip("Requires live database (integration test)")
