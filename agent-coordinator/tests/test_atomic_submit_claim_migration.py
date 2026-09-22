"""Contract checks for atomic submit-and-claim queue persistence."""

from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "database/migrations/043_atomic_submit_claim.sql"


def test_atomic_submit_claim_migration_claims_the_inserted_row() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE OR REPLACE FUNCTION submit_claimed_task(" in sql
    assert "p_agent_id TEXT" in sql
    assert "status" in sql
    assert "'claimed'" in sql
    assert "claimed_by" in sql
    assert "p_agent_id" in sql
    assert "claimed_at" in sql
    assert "attempt_count" in sql
    assert "RETURNING id,status" in sql
    assert "SECURITY INVOKER" in sql
    assert "SET search_path = public, pg_temp" in sql
    assert "reserved_projection_key" in sql
    assert "REVOKE ALL ON FUNCTION submit_claimed_task" in sql
    assert "FROM PUBLIC" in sql
    assert "GRANT EXECUTE ON FUNCTION submit_claimed_task" in sql
    assert "TO service_role" in sql
