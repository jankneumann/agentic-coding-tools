"""Tests for validate_work_result.py."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_work_result import (
    load_schema,
    validate_result,
    validate_schema,
    validate_scope_compliance,
    validate_verification_consistency,
)


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def valid_result():
    """A minimal valid work-queue result payload."""
    return {
        "schema_version": 1,
        "feature_id": "FEAT-test-001",
        "package_id": "wp-backend",
        "plan_revision": 1,
        "contracts_revision": 1,
        "status": "completed",
        "locks": {
            "files": ["src/api/users.py"],
            "keys": ["api:GET /v1/users"],
        },
        "scope": {
            "write_allow": ["src/api/**", "tests/api/**"],
            "read_allow": ["src/**"],
            "deny": ["src/frontend/**"],
        },
        "files_modified": ["src/api/users.py", "tests/api/test_users.py"],
        "git": {
            "base": {"ref": "main"},
            "head": {"commit": "abc1234", "branch": "openspec/feat-test"},
        },
        "verification": {
            "tier": "A",
            "passed": True,
            "steps": [
                {
                    "name": "unit-tests",
                    "kind": "command",
                    "passed": True,
                    "command": "pytest tests/api/ -v",
                    "exit_code": 0,
                    "evidence": {
                        "artifacts": ["artifacts/wp-backend/pytest.xml"],
                        "metrics": {"test_count": 12, "pass_count": 12},
                    },
                }
            ],
        },
        "escalations": [],
    }


# --- Schema validation ---


class TestSchemaValidation:
    def test_valid_result(self, schema, valid_result):
        errors = validate_schema(valid_result, schema)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_required_field(self, schema, valid_result):
        data = deepcopy(valid_result)
        del data["package_id"]
        errors = validate_schema(data, schema)
        assert any("package_id" in e for e in errors)

    def test_invalid_status(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "unknown"
        errors = validate_schema(data, schema)
        assert len(errors) > 0

    def test_invalid_commit_hash(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = "not-a-hash!"
        errors = validate_schema(data, schema)
        assert len(errors) > 0

    def test_failed_result_with_error_code(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "failed"
        data["error_code"] = "VERIFICATION_FAILED"
        errors = validate_schema(data, schema)
        assert errors == []

    def test_verification_tier_invalid(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["tier"] = "X"
        errors = validate_schema(data, schema)
        assert len(errors) > 0


# --- Scope compliance ---


class TestScopeCompliance:
    def test_valid_scope(self, valid_result):
        errors = validate_scope_compliance(valid_result)
        assert errors == []

    def test_file_outside_write_allow(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("config/settings.yaml")
        errors = validate_scope_compliance(data)
        assert len(errors) == 1
        assert "config/settings.yaml" in errors[0]

    def test_file_in_deny(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("src/frontend/App.tsx")
        errors = validate_scope_compliance(data)
        assert len(errors) == 1
        assert "deny" in errors[0]

    def test_empty_files_modified(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"] = []
        errors = validate_scope_compliance(data)
        assert errors == []


# --- Verification consistency ---


class TestVerificationConsistency:
    def test_consistent_pass(self, valid_result):
        errors = validate_verification_consistency(valid_result)
        assert errors == []

    def test_overall_pass_but_step_failed(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["passed"] = False
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "verification.passed=true" in errors[0]

    def test_overall_fail_but_all_steps_pass(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "verification.passed=false" in errors[0]

    def test_consistent_fail(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["passed"] = False
        errors = validate_verification_consistency(data)
        assert errors == []


# --- Full validation ---


class TestFullValidation:
    def test_valid_result(self, schema, valid_result):
        results = validate_result(valid_result, schema)
        assert results["valid"] is True
        assert all(c["passed"] for c in results["checks"].values())

    def test_invalid_schema_reports(self, schema, valid_result):
        data = deepcopy(valid_result)
        del data["status"]
        results = validate_result(data, schema)
        assert results["valid"] is False
        assert not results["checks"]["schema"]["passed"]

    def test_scope_violation_reports(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("outside/scope.txt")
        results = validate_result(data, schema)
        assert results["valid"] is False
        assert not results["checks"]["scope_compliance"]["passed"]


# --- CLI ---


class TestCLI:
    def test_valid_json_output(self, tmp_path, valid_result):
        import subprocess

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(valid_result))

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_result.py"),
                str(result_file),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_text_output(self, tmp_path, valid_result):
        import subprocess

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(valid_result))

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_result.py"),
                str(result_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "VALID" in result.stdout
