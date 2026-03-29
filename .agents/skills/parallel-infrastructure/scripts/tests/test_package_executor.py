"""Tests for package_executor module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from package_executor import PackageExecutor, make_pause_lock_key


def _make_package_def(
    pid: str = "wp-backend",
    write_allow: list[str] | None = None,
    deny: list[str] | None = None,
    file_locks: list[str] | None = None,
    key_locks: list[str] | None = None,
    verification_tier: str = "A",
) -> dict[str, Any]:
    """Create a minimal package definition."""
    return {
        "package_id": pid,
        "title": f"Package {pid}",
        "task_type": "implement",
        "description": f"Test package {pid}",
        "priority": 3,
        "depends_on": [],
        "locks": {
            "files": file_locks or [],
            "keys": key_locks or [],
        },
        "scope": {
            "write_allow": write_allow or ["src/api/**", "tests/api/**"],
            "read_allow": ["src/**", "contracts/**"],
            "deny": deny or [],
        },
        "worktree": {"name": pid},
        "timeout_minutes": 60,
        "retry_budget": 1,
        "min_trust_level": 2,
        "verification": {
            "tier_required": verification_tier,
            "steps": [
                {
                    "name": "test",
                    "kind": "command",
                    "command": "pytest tests/api/",
                    "evidence": {"artifacts": [], "result_keys": ["test_count"]},
                }
            ],
        },
        "outputs": {"result_keys": ["files_modified"]},
    }


def _make_executor(**kwargs: Any) -> PackageExecutor:
    """Create a PackageExecutor with defaults."""
    return PackageExecutor(
        feature_id=kwargs.get("feature_id", "test-feature"),
        package_def=kwargs.get("package_def", _make_package_def()),
        contracts_revision=kwargs.get("contracts_revision", 1),
        plan_revision=kwargs.get("plan_revision", 1),
        attempt=kwargs.get("attempt", 1),
    )


class TestMakePauseLockKey:
    def test_format(self) -> None:
        assert make_pause_lock_key("add-auth") == "feature:add-auth:pause"

    def test_with_dots(self) -> None:
        assert make_pause_lock_key("my.feature") == "feature:my.feature:pause"


class TestPauseLockCheck:
    def test_not_paused(self) -> None:
        executor = _make_executor()
        assert executor.check_pause_lock(["feature:other:pause", "api:GET /v1/users"]) is False

    def test_paused(self) -> None:
        executor = _make_executor(feature_id="my-feature")
        assert executor.check_pause_lock(["feature:my-feature:pause"]) is True

    def test_empty_locks(self) -> None:
        executor = _make_executor()
        assert executor.check_pause_lock([]) is False


class TestComputeLockOrder:
    def test_sorted_order(self) -> None:
        pkg = _make_package_def(
            file_locks=["src/api/routes.py", "src/api/auth.py"],
            key_locks=["api:POST /v1/users", "api:GET /v1/users"],
        )
        executor = _make_executor(package_def=pkg)
        order = executor.compute_lock_order()
        assert order == sorted(order)

    def test_deduplicates(self) -> None:
        pkg = _make_package_def(
            file_locks=["src/api/users.py"],
            key_locks=["src/api/users.py"],  # Duplicate across categories
        )
        executor = _make_executor(package_def=pkg)
        order = executor.compute_lock_order()
        assert len(order) == len(set(order))

    def test_empty_locks(self) -> None:
        pkg = _make_package_def(file_locks=[], key_locks=[])
        executor = _make_executor(package_def=pkg)
        assert executor.compute_lock_order() == []

    def test_mixed_lock_types(self) -> None:
        pkg = _make_package_def(
            file_locks=["src/api/users.py"],
            key_locks=["api:GET /v1/users", "db:schema:users"],
        )
        executor = _make_executor(package_def=pkg)
        order = executor.compute_lock_order()
        assert len(order) == 3
        # All should be sorted lexicographically
        assert order == sorted(order)


class TestLockTracking:
    def test_record_and_get(self) -> None:
        executor = _make_executor()
        executor.record_lock_acquired("src/api/users.py")
        executor.record_lock_acquired("api:GET /v1/users")
        assert executor.get_acquired_locks() == ["src/api/users.py", "api:GET /v1/users"]

    def test_no_duplicates(self) -> None:
        executor = _make_executor()
        executor.record_lock_acquired("src/api/users.py")
        executor.record_lock_acquired("src/api/users.py")
        assert len(executor.get_acquired_locks()) == 1


class TestScopeCheck:
    def test_files_in_scope(self) -> None:
        executor = _make_executor()
        result = executor.check_scope(["src/api/users.py", "tests/api/test_users.py"])
        assert result["compliant"] is True

    def test_file_outside_scope(self) -> None:
        executor = _make_executor()
        result = executor.check_scope(["src/frontend/App.tsx"])
        assert result["compliant"] is False

    def test_file_in_deny(self) -> None:
        pkg = _make_package_def(
            write_allow=["src/**"],
            deny=["src/frontend/**"],
        )
        executor = _make_executor(package_def=pkg)
        result = executor.check_scope(["src/frontend/App.tsx"])
        assert result["compliant"] is False


class TestBuildResult:
    def _build_default_result(self, executor: PackageExecutor | None = None) -> dict[str, Any]:
        if executor is None:
            executor = _make_executor()
        executor.mark_started()
        return executor.build_result(
            status="completed",
            files_modified=["src/api/users.py"],
            git_base_ref="main",
            git_head_commit="abc1234def",
            verification_steps=[{
                "name": "unit-tests",
                "kind": "command",
                "command": "pytest tests/api/",
                "exit_code": 0,
                "passed": True,
                "evidence": {"artifacts": [], "metrics": {"test_count": 10}},
            }],
            git_branch="openspec/test-feature",
            git_worktree="wp-backend",
        )

    def test_required_fields_present(self) -> None:
        result = self._build_default_result()
        required = [
            "schema_version", "feature_id", "package_id", "plan_revision",
            "contracts_revision", "status", "locks", "scope", "files_modified",
            "git", "verification", "escalations",
        ]
        for field in required:
            assert field in result, f"Missing required field: {field}"

    def test_schema_version(self) -> None:
        result = self._build_default_result()
        assert result["schema_version"] == 1

    def test_feature_and_package_ids(self) -> None:
        result = self._build_default_result()
        assert result["feature_id"] == "test-feature"
        assert result["package_id"] == "wp-backend"

    def test_revisions(self) -> None:
        result = self._build_default_result()
        assert result["plan_revision"] == 1
        assert result["contracts_revision"] == 1

    def test_status_completed(self) -> None:
        result = self._build_default_result()
        assert result["status"] == "completed"

    def test_scope_echo(self) -> None:
        result = self._build_default_result()
        assert "write_allow" in result["scope"]
        assert "read_allow" in result["scope"]
        assert "deny" in result["scope"]

    def test_scope_check_included(self) -> None:
        result = self._build_default_result()
        assert result["scope_check"]["passed"] is True
        assert result["scope_check"]["violations"] == []

    def test_git_info(self) -> None:
        result = self._build_default_result()
        assert result["git"]["base"]["ref"] == "main"
        assert result["git"]["head"]["commit"] == "abc1234def"
        assert result["git"]["head"]["branch"] == "openspec/test-feature"
        assert result["git"]["head"]["worktree"] == "wp-backend"

    def test_verification_summary(self) -> None:
        result = self._build_default_result()
        assert result["verification"]["tier"] == "A"
        assert result["verification"]["passed"] is True
        assert len(result["verification"]["steps"]) == 1

    def test_timestamps_present(self) -> None:
        result = self._build_default_result()
        assert "timestamps" in result
        assert "started_at" in result["timestamps"]
        assert "finished_at" in result["timestamps"]

    def test_escalations_empty_by_default(self) -> None:
        result = self._build_default_result()
        assert result["escalations"] == []

    def test_escalations_included(self) -> None:
        executor = _make_executor()
        executor.add_escalation({
            "escalation_id": "esc-001",
            "feature_id": "test-feature",
            "package_id": "wp-backend",
            "type": "SCOPE_VIOLATION",
            "severity": "HIGH",
            "summary": "File outside scope",
            "detected_at": "2026-01-01T00:00:00Z",
        })
        result = self._build_default_result(executor)
        assert len(result["escalations"]) == 1
        assert result["escalations"][0]["type"] == "SCOPE_VIOLATION"

    def test_error_code_on_failure(self) -> None:
        executor = _make_executor()
        executor.mark_started()
        result = executor.build_result(
            status="failed",
            files_modified=[],
            git_base_ref="main",
            git_head_commit="abc1234def",
            verification_steps=[{
                "name": "unit-tests",
                "kind": "command",
                "command": "pytest",
                "exit_code": 1,
                "passed": False,
                "evidence": {"artifacts": [], "metrics": {}},
            }],
            error_code="VERIFICATION_FAILED",
        )
        assert result["status"] == "failed"
        assert result["error_code"] == "VERIFICATION_FAILED"
        assert result["verification"]["passed"] is False

    def test_attempt_tracking(self) -> None:
        executor = _make_executor(attempt=3)
        result = self._build_default_result(executor)
        assert result["attempt"] == 3

    def test_scope_violation_in_result(self) -> None:
        executor = _make_executor()
        executor.mark_started()
        result = executor.build_result(
            status="completed",
            files_modified=["src/frontend/bad.tsx"],
            git_base_ref="main",
            git_head_commit="abc1234def",
            verification_steps=[{
                "name": "test",
                "kind": "command",
                "command": "pytest",
                "exit_code": 0,
                "passed": True,
                "evidence": {"artifacts": [], "metrics": {}},
            }],
        )
        assert result["scope_check"]["passed"] is False
        assert "src/frontend/bad.tsx" in result["scope_check"]["violations"]


class TestBuildFailureResult:
    def test_failure_result(self) -> None:
        executor = _make_executor()
        executor.mark_started()
        result = executor.build_failure_result(
            error_code="LOCK_UNAVAILABLE",
            git_base_ref="main",
            git_head_commit="abc1234def",
            notes="Could not acquire lock on src/api/users.py",
        )
        assert result["status"] == "failed"
        assert result["error_code"] == "LOCK_UNAVAILABLE"
        assert result["files_modified"] == []
        assert result["verification"]["passed"] is False
        assert result["notes"] == "Could not acquire lock on src/api/users.py"

    def test_failure_result_has_required_fields(self) -> None:
        executor = _make_executor()
        result = executor.build_failure_result(
            error_code="TIMEOUT",
            git_base_ref="main",
            git_head_commit="abc1234def",
        )
        required = [
            "schema_version", "feature_id", "package_id", "plan_revision",
            "contracts_revision", "status", "locks", "scope", "files_modified",
            "git", "verification", "escalations",
        ]
        for field in required:
            assert field in result, f"Missing required field: {field}"
