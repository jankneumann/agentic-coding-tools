"""Text contract for migration 046 (cross-host review queue)."""

from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "database/migrations/046_review_queue.sql"

_RPCS = (
    "submit_review_job",
    "record_review_lanes",
    "get_review_round",
    "claim_review_publication",
    "finish_review_publication",
)


def test_one_job_per_pr_head_and_round() -> None:
    sql = MIGRATION.read_text()

    assert "UNIQUE (repo, pr, head_sha, round)" in sql
    assert "PRIMARY KEY (job_id, vendor)" in sql
    assert "CHECK (status IN ('active', 'quorum_met', 'unreachable', 'superseded'))" in sql


def test_every_rpc_is_locked_down_to_the_service_role() -> None:
    sql = MIGRATION.read_text()

    for fn in _RPCS:
        assert f"CREATE OR REPLACE FUNCTION {fn}(" in sql
        assert f"REVOKE ALL ON FUNCTION {fn}(" in sql
        assert f"GRANT EXECUTE ON FUNCTION {fn}(" in sql
    assert "SECURITY DEFINER" not in sql
    assert sql.count("SET search_path = public, pg_temp") == sql.count(
        "CREATE OR REPLACE FUNCTION"
    )


def test_lane_recording_names_each_rejection() -> None:
    sql = MIGRATION.read_text()

    for reason in (
        "invalid_lanes",
        "task_not_found",
        "not_claimant",
        "job_not_found",
        "superseded",
        "stale_pass",
    ):
        assert f"'{reason}'" in sql
