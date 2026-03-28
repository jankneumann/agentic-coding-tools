"""Tests for result_validator module (Phase C1)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from result_validator import (
    validate_output_keys,
    validate_package_result,
    validate_revision_match,
)


def _make_result(
    status: str = "completed",
    feature_id: str = "test-feature",
    package_id: str = "wp-backend",
    plan_revision: int = 1,
    contracts_revision: int = 1,
    files_modified: list[str] | None = None,
    verification_passed: bool = True,
    verification_steps: list[dict[str, Any]] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build a minimal valid work-queue result."""
    steps = verification_steps or [
        {
            "name": "unit-tests",
            "kind": "command",
            "command": "pytest tests/api/",
            "exit_code": 0,
            "passed": verification_passed,
            "evidence": {
                "artifacts": [],
                "metrics": {"test_count": 10, "pass_count": 10},
            },
        }
    ]

    result: dict[str, Any] = {
        "schema_version": 1,
        "feature_id": feature_id,
        "package_id": package_id,
        "attempt": 1,
        "plan_revision": plan_revision,
        "contracts_revision": contracts_revision,
        "status": status,
        "locks": {"files": [], "keys": []},
        "scope": {
            "write_allow": ["src/api/**", "tests/api/**"],
            "read_allow": ["src/**"],
            "deny": [],
        },
        "files_modified": files_modified or ["src/api/users.py"],
        "scope_check": {"passed": True, "violations": []},
        "git": {
            "base": {"ref": "main"},
            "head": {"commit": "abc1234def"},
        },
        "verification": {
            "tier": "A",
            "passed": verification_passed,
            "steps": steps,
        },
        "escalations": [],
    }

    if error_code:
        result["error_code"] = error_code

    return result


def _make_package_def(
    result_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal package definition."""
    return {
        "package_id": "wp-backend",
        "outputs": {"result_keys": result_keys or ["files_modified", "test_count"]},
    }


# --- Tests: validate_revision_match ---


class TestValidateRevisionMatch:
    def test_matching_revisions(self) -> None:
        result = _make_result(contracts_revision=2, plan_revision=3)
        errors = validate_revision_match(result, expected_contracts_revision=2, expected_plan_revision=3)
        assert errors == []

    def test_contracts_revision_mismatch(self) -> None:
        result = _make_result(contracts_revision=1, plan_revision=1)
        errors = validate_revision_match(result, expected_contracts_revision=2, expected_plan_revision=1)
        assert len(errors) == 1
        assert "contracts_revision mismatch" in errors[0]

    def test_plan_revision_mismatch(self) -> None:
        result = _make_result(contracts_revision=1, plan_revision=1)
        errors = validate_revision_match(result, expected_contracts_revision=1, expected_plan_revision=2)
        assert len(errors) == 1
        assert "plan_revision mismatch" in errors[0]

    def test_both_mismatch(self) -> None:
        result = _make_result(contracts_revision=1, plan_revision=1)
        errors = validate_revision_match(result, expected_contracts_revision=2, expected_plan_revision=3)
        assert len(errors) == 2


# --- Tests: validate_output_keys ---


class TestValidateOutputKeys:
    def test_keys_present_in_metrics(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=["test_count"])
        errors = validate_output_keys(result, pkg)
        assert errors == []

    def test_files_modified_always_available(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=["files_modified"])
        errors = validate_output_keys(result, pkg)
        assert errors == []

    def test_missing_key(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=["files_modified", "merge_commit"])
        errors = validate_output_keys(result, pkg)
        assert len(errors) == 1
        assert "merge_commit" in errors[0]

    def test_empty_declared_keys(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=[])
        errors = validate_output_keys(result, pkg)
        assert errors == []

    def test_no_outputs_key(self) -> None:
        result = _make_result()
        pkg: dict[str, Any] = {"package_id": "wp-x"}
        errors = validate_output_keys(result, pkg)
        assert errors == []

    def test_multiple_steps_with_different_metrics(self) -> None:
        result = _make_result(verification_steps=[
            {
                "name": "lint",
                "kind": "command",
                "command": "ruff check",
                "exit_code": 0,
                "passed": True,
                "evidence": {"artifacts": [], "metrics": {"lint_passed": True}},
            },
            {
                "name": "test",
                "kind": "command",
                "command": "pytest",
                "exit_code": 0,
                "passed": True,
                "evidence": {"artifacts": [], "metrics": {"test_count": 42}},
            },
        ])
        pkg = _make_package_def(result_keys=["test_count", "lint_passed", "files_modified"])
        # lint_passed is in metrics, not top-level, but we check metrics
        errors = validate_output_keys(result, pkg)
        assert errors == []


# --- Tests: validate_package_result (full validation) ---


class TestValidatePackageResult:
    def test_valid_result(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=["files_modified", "test_count"])
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        assert validation["valid"] is True
        assert validation["checks"]["schema"]["passed"] is True
        assert validation["checks"]["revision_match"]["passed"] is True
        assert validation["checks"]["output_keys"]["passed"] is True

    def test_schema_failure(self) -> None:
        result = _make_result()
        del result["feature_id"]  # Remove required field
        pkg = _make_package_def()
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        assert validation["valid"] is False
        assert validation["checks"]["schema"]["passed"] is False

    def test_revision_failure_makes_invalid(self) -> None:
        result = _make_result(contracts_revision=1)
        pkg = _make_package_def(result_keys=["files_modified", "test_count"])
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=2,
            expected_plan_revision=1,
        )
        assert validation["valid"] is False
        assert validation["checks"]["revision_match"]["passed"] is False

    def test_output_key_failure_makes_invalid(self) -> None:
        result = _make_result()
        pkg = _make_package_def(result_keys=["nonexistent_key"])
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        assert validation["valid"] is False
        assert validation["checks"]["output_keys"]["passed"] is False

    def test_all_checks_present(self) -> None:
        result = _make_result()
        pkg = _make_package_def()
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        expected_checks = [
            "schema",
            "scope_compliance",
            "verification_consistency",
            "revision_match",
            "output_keys",
        ]
        for check in expected_checks:
            assert check in validation["checks"], f"Missing check: {check}"

    def test_verification_consistency_failure(self) -> None:
        result = _make_result(verification_passed=True)
        # Override with a failing step but passed=True overall
        result["verification"]["steps"][0]["passed"] = False
        pkg = _make_package_def(result_keys=["files_modified", "test_count"])
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        assert validation["valid"] is False
        assert validation["checks"]["verification_consistency"]["passed"] is False

    def test_scope_compliance_failure(self) -> None:
        result = _make_result(files_modified=["src/frontend/bad.tsx"])
        pkg = _make_package_def(result_keys=["files_modified"])
        validation = validate_package_result(
            result, pkg,
            expected_contracts_revision=1,
            expected_plan_revision=1,
        )
        assert validation["valid"] is False
        assert validation["checks"]["scope_compliance"]["passed"] is False
