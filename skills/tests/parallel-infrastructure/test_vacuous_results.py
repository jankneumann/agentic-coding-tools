"""End-to-end pins: a vacuous or unverifiable worker result never completes a package.

These tests drive the real emitter (``PackageExecutor``), the real acceptance
decision (``accept_package_result``) and both decision points
(``DAGScheduler.mark_completed`` and ``IntegrationOrchestrator``'s gate)
together, and validate emitter output against the schema file itself rather
than a copy of it.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for

from dag_scheduler import DAGScheduler, PackageState, PackageStatus
from integration_orchestrator import IntegrationGateStatus, IntegrationOrchestrator
from package_executor import PackageExecutor
from result_validator import PackageAcceptance, accept_package_result
from validate_work_result import effective_outcome, validate_result

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "work-queue-result.schema.json"
INSTALLED_SCHEMA_PATH = (
    REPO_ROOT
    / "skills"
    / "parallel-infrastructure"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "work-queue-result.schema.json"
)

PACKAGE_ID = "wp-api"
DEPENDANT_ID = "wp-client"
ABSENT_COMMIT = "0123456789abcdef0123456789abcdef01234567"


# --- Fixtures and helpers ---


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def _schema_errors(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    return [e.message for e in validator_cls(schema).iter_errors(data)]


def _package_def(package_id: str = PACKAGE_ID) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "title": f"Package {package_id}",
        "task_type": "implement",
        "description": "Pinned package",
        "priority": 3,
        "depends_on": [],
        "locks": {"files": [], "keys": []},
        "scope": {
            "write_allow": ["src/api/**"],
            "read_allow": ["src/**"],
            "deny": [],
        },
        "worktree": {"name": package_id},
        "verification": {"tier_required": "A", "steps": []},
        "outputs": {"result_keys": ["files_modified"]},
    }


def _executor() -> PackageExecutor:
    return PackageExecutor(
        feature_id="pin-feature",
        package_def=_package_def(),
        contracts_revision=1,
        plan_revision=1,
    )


def _step(passed: bool = True) -> dict[str, Any]:
    return {
        "name": "unit-tests",
        "kind": "command",
        "command": "pytest -q",
        "exit_code": 0 if passed else 1,
        "passed": passed,
        "evidence": {"artifacts": [], "metrics": {}},
    }


def _build(
    head_commit: str,
    steps: list[dict[str, Any]],
    status: str = "completed",
) -> dict[str, Any]:
    return _executor().build_result(
        status=status,
        files_modified=["src/api/users.py"],
        git_base_ref="main",
        git_head_commit=head_commit,
        verification_steps=steps,
    )


def _accept(result: dict[str, Any], worktree: Path | None) -> PackageAcceptance:
    return accept_package_result(
        result,
        _package_def(),
        expected_contracts_revision=1,
        expected_plan_revision=1,
        worktree_path=worktree,
    )


def _scheduler(tmp_path: Path) -> DAGScheduler:
    """A two-package chain, PACKAGE_ID → DEPENDANT_ID, past preflight."""
    scheduler = DAGScheduler(tmp_path / "work-packages.yaml", tmp_path)
    scheduler.package_statuses = {
        PACKAGE_ID: PackageStatus(package_id=PACKAGE_ID, state=PackageState.READY),
        DEPENDANT_ID: PackageStatus(package_id=DEPENDANT_ID, depends_on=[PACKAGE_ID]),
    }
    return scheduler


def _orchestrator() -> IntegrationOrchestrator:
    return IntegrationOrchestrator(
        feature_id="pin-feature",
        packages=[
            {"package_id": PACKAGE_ID, "task_type": "implement"},
            {"package_id": "wp-integration", "task_type": "integrate"},
        ],
    )


def _clean_review() -> dict[str, Any]:
    return {
        "review_type": "implementation",
        "target": PACKAGE_ID,
        "reviewer_vendor": "test",
        "findings": [],
    }


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A git working tree with one commit; returns (path, HEAD SHA)."""
    path = tmp_path / "worktree"
    path.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "pin@example.com")
    git("config", "user.name", "pin")
    (path / "README").write_text("pin\n")
    git("add", "README")
    git("commit", "-q", "-m", "initial")
    return path, git("rev-parse", "HEAD")


# --- Emitters validate against the schema ---


class TestEmittersValidate:
    def test_passing_build_result_validates(self, schema: dict[str, Any]) -> None:
        result = _build("abc1234", [_step(True)])
        assert _schema_errors(schema, result) == []
        assert result["outcome"] == "PASS"

    def test_failing_build_result_validates(self, schema: dict[str, Any]) -> None:
        result = _build("abc1234", [_step(False)])
        assert _schema_errors(schema, result) == []
        assert result["outcome"] == "ISSUES"

    def test_build_failure_result_validates(self, schema: dict[str, Any]) -> None:
        result = _executor().build_failure_result(
            error_code="timeout", git_base_ref="main", git_head_commit="abc1234"
        )
        assert _schema_errors(schema, result) == []
        assert result["outcome"] == "BLOCKED"
        assert result["verification"]["steps"][0]["method"] == "not_run"

    def test_zero_step_build_result_is_not_a_pass(
        self, schema: dict[str, Any]
    ) -> None:
        # The emitter no longer claims a pass, and the schema and the checker
        # both refuse an empty step list rather than letting it through.
        result = _build("abc1234", [])
        assert result["verification"]["passed"] is False
        assert result["outcome"] != "PASS"
        assert _schema_errors(schema, result) != []
        verdict = validate_result(result, schema)
        assert verdict["valid"] is False
        assert verdict["checks"]["verification_consistency"]["passed"] is False

    def test_legacy_result_validates_and_derives_pass(
        self, schema: dict[str, Any]
    ) -> None:
        legacy = _build("abc1234", [_step(True)])
        del legacy["outcome"]
        for step in legacy["verification"]["steps"]:
            step.pop("method", None)
        assert _schema_errors(schema, legacy) == []
        assert effective_outcome(legacy) == "PASS"
        assert validate_result(legacy, schema)["valid"] is True

    def test_schema_copies_are_byte_identical(self) -> None:
        assert SCHEMA_PATH.read_bytes() == INSTALLED_SCHEMA_PATH.read_bytes()


# --- End-to-end: emitter → acceptance → scheduler and gate ---


class TestVacuousResultEndToEnd:
    def test_zero_steps_never_complete_the_package(
        self, tmp_path: Path, repo: tuple[Path, str]
    ) -> None:
        worktree, head = repo
        result = _build(head, [])

        acceptance = _accept(result, worktree)
        assert acceptance.accepted is False
        assert acceptance.outcome != "PASS"

        scheduler = _scheduler(tmp_path)
        assert scheduler.mark_completed(PACKAGE_ID, acceptance) is False
        assert scheduler.package_statuses[PACKAGE_ID].state == PackageState.FAILED
        assert DEPENDANT_ID not in scheduler.get_ready_packages()

        orch = _orchestrator()
        orch.record_package_result(PACKAGE_ID, result, acceptance)
        orch.record_review_findings(PACKAGE_ID, _clean_review())
        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.BLOCKED_NOT_PASSING.value
        assert [entry["package_id"] for entry in gate["not_passing"]] == [PACKAGE_ID]

    def test_absent_commit_is_refused(
        self, tmp_path: Path, repo: tuple[Path, str]
    ) -> None:
        worktree, _head = repo
        result = _build(ABSENT_COMMIT, [_step(True)])
        assert result["outcome"] == "PASS"  # the claim alone looks clean

        acceptance = _accept(result, worktree)
        assert acceptance.accepted is False
        assert any("commit_resolves" in reason for reason in acceptance.reasons)

        scheduler = _scheduler(tmp_path)
        assert scheduler.mark_completed(PACKAGE_ID, acceptance) is False
        assert DEPENDANT_ID not in scheduler.get_ready_packages()

    def test_unchecked_commit_is_refused(self, repo: tuple[Path, str]) -> None:
        _worktree, head = repo
        acceptance = _accept(_build(head, [_step(True)]), None)
        assert acceptance.accepted is False
        assert any("not checked" in reason for reason in acceptance.reasons)

    def test_upgraded_outcome_is_refused(
        self, repo: tuple[Path, str]
    ) -> None:
        worktree, head = repo
        result = _executor().build_result(
            status="completed",
            files_modified=["src/api/users.py"],
            git_base_ref="main",
            git_head_commit=head,
            verification_steps=[_step(False)],
            outcome="PASS",
        )
        acceptance = _accept(result, worktree)
        assert acceptance.accepted is False

    def test_validated_pass_completes_and_passes_the_gate(
        self, tmp_path: Path, repo: tuple[Path, str]
    ) -> None:
        worktree, head = repo
        result = _build(head, [_step(True)])

        acceptance = _accept(result, worktree)
        assert acceptance.accepted is True, acceptance.reasons
        assert acceptance.outcome == "PASS"

        scheduler = _scheduler(tmp_path)
        assert scheduler.mark_completed(PACKAGE_ID, acceptance) is True
        assert scheduler.package_statuses[PACKAGE_ID].state == PackageState.COMPLETED
        assert DEPENDANT_ID in scheduler.get_ready_packages()

        orch = _orchestrator()
        orch.record_package_result(PACKAGE_ID, copy.deepcopy(result), acceptance)
        orch.record_review_findings(PACKAGE_ID, _clean_review())
        gate = orch.check_integration_gate()
        assert gate["status"] == IntegrationGateStatus.PASS.value
        assert gate["not_passing"] == []
        assert gate["overrides"] == []
