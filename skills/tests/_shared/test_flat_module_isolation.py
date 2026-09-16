"""Regression coverage for flat skill-module isolation during collection."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]


def test_skills_root_owns_both_isolation_hooks():
    source = (SKILLS_ROOT / "conftest.py").read_text()

    assert "def pytest_collectstart(" in source
    assert "def pytest_runtest_setup(" in source


def test_colliding_flat_modules_are_isolated_between_skill_test_packages():
    """Sibling skill suites must not inherit another suite's flat modules."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/project-context-runtime",
            "tests/plan-roadmap",
            "tests/autopilot",
            "tests/playwright-validator",
            "tests/project-context-refresh",
        ],
        cwd=SKILLS_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr



def test_unrelated_flat_module_remains_registered_after_later_collection():
    """A later suite may evict collisions, but not unrelated imported modules."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/supervise/test_cycle_state.py::TestImportIsolation::"
            "test_cycle_state_survives_a_foreign_models_module",
            "tests/autopilot-roadmap/test_host_assisted_invariant.py::"
            "test_guard_actually_runs",
        ],
        cwd=SKILLS_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_script_level_suites_reactivate_after_tests_tree_collection():
    """Top-level ``scripts/tests`` suites must survive later ``tests/`` imports."""
    cases = (
        (
            "coordination-bridge/scripts/tests/test_github_issues.py::"
            "test_bridge_dispatches_to_github_when_configured",
            "tests/roadmap-runtime/test_models.py::TestRoadmapItem::test_round_trip",
        ),
        (
            "refresh-architecture/scripts/tests/test_context_runtime_adapter.py::"
            "test_adapter_rejects_non_architecture_result",
            "tests/roadmap-runtime/test_models.py::TestRoadmapItem::test_round_trip",
        ),
    )

    for first, second in cases:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", first, second],
            cwd=SKILLS_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
