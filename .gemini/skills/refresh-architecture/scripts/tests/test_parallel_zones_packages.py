"""Tests for parallel_zones.py --validate-packages mode."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parent.parent / "parallel_zones.py"


class TestValidatePackagesCLI:
    def test_valid_packages_text(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-packages", str(FIXTURES / "sample-work-packages.yaml")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "VALID" in result.stderr  # logger output goes to stderr

    def test_valid_packages_json(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--validate-packages",
                str(FIXTURES / "sample-work-packages.yaml"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["scope_overlap"]["passed"] is True
        assert data["lock_overlap"]["passed"] is True
        assert len(data["parallel_pairs"]) > 0

    def test_parallel_pairs_detected(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--validate-packages",
                str(FIXTURES / "sample-work-packages.yaml"),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        pair_set = {tuple(sorted(p)) for p in data["parallel_pairs"]}
        assert ("wp-backend", "wp-frontend") in pair_set

    def test_missing_file(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-packages", "/nonexistent/file.yaml"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_overlap_detected(self, tmp_path):
        import yaml

        data = {
            "schema_version": 1,
            "feature": {"id": "TEST", "title": "Test", "plan_revision": 1},
            "packages": [
                {
                    "package_id": "a",
                    "title": "A",
                    "task_type": "implement",
                    "description": "A",
                    "priority": 1,
                    "depends_on": [],
                    "locks": {"files": ["src/shared.py"], "keys": []},
                    "scope": {"write_allow": ["src/**"]},
                    "worktree": {"name": "a"},
                    "timeout_minutes": 30,
                    "retry_budget": 0,
                    "min_trust_level": 2,
                    "verification": {
                        "tier_required": "C",
                        "steps": [],
                    },
                    "outputs": {"result_keys": []},
                },
                {
                    "package_id": "b",
                    "title": "B",
                    "task_type": "implement",
                    "description": "B",
                    "priority": 1,
                    "depends_on": [],
                    "locks": {"files": ["src/shared.py"], "keys": []},
                    "scope": {"write_allow": ["src/**"]},
                    "worktree": {"name": "b"},
                    "timeout_minutes": 30,
                    "retry_budget": 0,
                    "min_trust_level": 2,
                    "verification": {
                        "tier_required": "C",
                        "steps": [],
                    },
                    "outputs": {"result_keys": []},
                },
            ],
        }
        wp_file = tmp_path / "wp.yaml"
        with open(wp_file, "w") as f:
            yaml.dump(data, f)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-packages", str(wp_file), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        out = json.loads(result.stdout)
        assert out["valid"] is False
        assert not out["scope_overlap"]["passed"] or not out["lock_overlap"]["passed"]
