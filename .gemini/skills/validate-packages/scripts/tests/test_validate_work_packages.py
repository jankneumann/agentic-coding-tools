"""Tests for validate_work_packages.py."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_work_packages import (
    detect_cycles,
    get_parallel_pairs,
    load_schema,
    validate_depends_on_refs,
    validate_lock_keys,
    validate_lock_overlap,
    validate_schema,
    validate_scope_overlap,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def valid_packages():
    with open(FIXTURES / "sample-work-packages.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def packages_list(valid_packages):
    return valid_packages["packages"]


# --- Schema validation ---


class TestSchemaValidation:
    def test_valid_packages_pass(self, schema, valid_packages):
        errors = validate_schema(valid_packages, schema)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_required_field(self, schema, valid_packages):
        data = deepcopy(valid_packages)
        del data["feature"]
        errors = validate_schema(data, schema)
        assert any("feature" in e for e in errors)

    def test_invalid_package_id_pattern(self, schema, valid_packages):
        data = deepcopy(valid_packages)
        data["packages"][0]["package_id"] = "INVALID_uppercase"
        errors = validate_schema(data, schema)
        assert len(errors) > 0

    def test_missing_schema_version(self, schema, valid_packages):
        data = deepcopy(valid_packages)
        del data["schema_version"]
        errors = validate_schema(data, schema)
        assert any("schema_version" in e for e in errors)

    def test_wrong_schema_version(self, schema, valid_packages):
        data = deepcopy(valid_packages)
        data["schema_version"] = 99
        errors = validate_schema(data, schema)
        assert len(errors) > 0


# --- DAG cycle detection ---


class TestCycleDetection:
    def test_no_cycles(self, packages_list):
        cycles = detect_cycles(packages_list)
        assert cycles == []

    def test_self_cycle(self):
        packages = [
            {"package_id": "a", "depends_on": ["a"]},
        ]
        cycles = detect_cycles(packages)
        assert len(cycles) > 0

    def test_two_node_cycle(self):
        packages = [
            {"package_id": "a", "depends_on": ["b"]},
            {"package_id": "b", "depends_on": ["a"]},
        ]
        cycles = detect_cycles(packages)
        assert len(cycles) > 0

    def test_three_node_cycle(self):
        packages = [
            {"package_id": "a", "depends_on": ["b"]},
            {"package_id": "b", "depends_on": ["c"]},
            {"package_id": "c", "depends_on": ["a"]},
        ]
        cycles = detect_cycles(packages)
        assert len(cycles) > 0

    def test_linear_chain_no_cycle(self):
        packages = [
            {"package_id": "a", "depends_on": []},
            {"package_id": "b", "depends_on": ["a"]},
            {"package_id": "c", "depends_on": ["b"]},
        ]
        cycles = detect_cycles(packages)
        assert cycles == []

    def test_diamond_no_cycle(self):
        packages = [
            {"package_id": "a", "depends_on": []},
            {"package_id": "b", "depends_on": ["a"]},
            {"package_id": "c", "depends_on": ["a"]},
            {"package_id": "d", "depends_on": ["b", "c"]},
        ]
        cycles = detect_cycles(packages)
        assert cycles == []


# --- Lock key validation ---


class TestLockKeyValidation:
    def test_valid_keys(self, packages_list):
        errors = validate_lock_keys(packages_list)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_api_key_lowercase_method(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["api:get /v1/users"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert len(errors) > 0
        assert "canonicalization" in errors[0]

    def test_db_schema_uppercase(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["db:schema:Users"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert len(errors) > 0

    def test_event_uppercase(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["event:User.Created"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert len(errors) > 0

    def test_unknown_prefix(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["unknown:something"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert len(errors) > 0
        assert "unrecognized" in errors[0]

    def test_valid_feature_pause_key(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["feature:FEAT-123:pause"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert errors == []

    def test_valid_contract_key(self):
        packages = [
            {
                "package_id": "test",
                "locks": {"keys": ["contract:openapi/v1.yaml"]},
            }
        ]
        errors = validate_lock_keys(packages)
        assert errors == []


# --- depends_on reference validation ---


class TestDependsOnRefs:
    def test_valid_refs(self, packages_list):
        errors = validate_depends_on_refs(packages_list)
        assert errors == []

    def test_missing_ref(self):
        packages = [
            {"package_id": "a", "depends_on": ["nonexistent"]},
        ]
        errors = validate_depends_on_refs(packages)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]


# --- Parallel pair detection ---


class TestParallelPairs:
    def test_sample_parallel_pairs(self, packages_list):
        pairs = get_parallel_pairs(packages_list)
        pair_set = {tuple(sorted(p)) for p in pairs}
        # wp-backend and wp-frontend should be parallel (both depend on wp-contracts)
        assert ("wp-backend", "wp-frontend") in pair_set

    def test_linear_chain_no_pairs(self):
        packages = [
            {"package_id": "a", "depends_on": []},
            {"package_id": "b", "depends_on": ["a"]},
            {"package_id": "c", "depends_on": ["b"]},
        ]
        pairs = get_parallel_pairs(packages)
        assert pairs == []

    def test_all_independent(self):
        packages = [
            {"package_id": "a", "depends_on": []},
            {"package_id": "b", "depends_on": []},
            {"package_id": "c", "depends_on": []},
        ]
        pairs = get_parallel_pairs(packages)
        assert len(pairs) == 3  # a-b, a-c, b-c


# --- Scope overlap ---


class TestScopeOverlap:
    def test_no_overlap(self, packages_list):
        errors = validate_scope_overlap(packages_list)
        assert errors == [], f"Unexpected overlap: {errors}"

    def test_overlap_detected(self):
        packages = [
            {
                "package_id": "a",
                "depends_on": [],
                "scope": {"write_allow": ["src/api/**"]},
            },
            {
                "package_id": "b",
                "depends_on": [],
                "scope": {"write_allow": ["src/api/**"]},
            },
        ]
        errors = validate_scope_overlap(packages)
        assert len(errors) > 0

    def test_wp_integration_exempt(self):
        packages = [
            {
                "package_id": "a",
                "depends_on": [],
                "scope": {"write_allow": ["src/**"]},
            },
            {
                "package_id": "wp-integration",
                "depends_on": ["a"],
                "scope": {"write_allow": ["**"]},
            },
        ]
        # wp-integration overlaps with everything but is exempt
        errors = validate_scope_overlap(packages)
        assert errors == []


# --- Lock overlap ---


class TestLockOverlap:
    def test_no_overlap(self, packages_list):
        errors = validate_lock_overlap(packages_list)
        assert errors == [], f"Unexpected overlap: {errors}"

    def test_key_overlap_detected(self):
        packages = [
            {
                "package_id": "a",
                "depends_on": [],
                "locks": {"files": [], "keys": ["api:GET /v1/users"]},
            },
            {
                "package_id": "b",
                "depends_on": [],
                "locks": {"files": [], "keys": ["api:GET /v1/users"]},
            },
        ]
        errors = validate_lock_overlap(packages)
        assert len(errors) > 0

    def test_file_overlap_detected(self):
        packages = [
            {
                "package_id": "a",
                "depends_on": [],
                "locks": {"files": ["src/shared.py"], "keys": []},
            },
            {
                "package_id": "b",
                "depends_on": [],
                "locks": {"files": ["src/shared.py"], "keys": []},
            },
        ]
        errors = validate_lock_overlap(packages)
        assert len(errors) > 0


# --- CLI integration ---


class TestCLI:
    def test_help(self, tmp_path):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "validate_work_packages.py"), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "work-packages.yaml" in result.stdout

    def test_valid_file(self, tmp_path):
        import subprocess
        import shutil

        shutil.copy(FIXTURES / "sample-work-packages.yaml", tmp_path / "wp.yaml")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "validate_work_packages.py"), str(tmp_path / "wp.yaml")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "VALID" in result.stdout

    def test_json_output(self, tmp_path):
        import subprocess
        import shutil

        shutil.copy(FIXTURES / "sample-work-packages.yaml", tmp_path / "wp.yaml")
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_packages.py"),
                str(tmp_path / "wp.yaml"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
