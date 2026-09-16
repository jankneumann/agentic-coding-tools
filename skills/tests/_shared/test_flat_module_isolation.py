"""Regression coverage for flat skill-module isolation during collection."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]


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
