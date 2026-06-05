"""Tests for run_architecture_linters.py — the CLI runner for structural linters.

Tests cover:
- File discovery via --files flag
- JSON output conformance
- Exit code 0 when no critical/high findings
- Exit code 1 when critical/high findings exist
- Empty file list produces clean output
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_RUNNER_SCRIPT = str(
    Path(__file__).resolve().parents[1] / "run_architecture_linters.py"
)


class TestRunArchitectureLinters:
    """Test the CLI runner script."""

    def test_clean_files_exit_zero(self, tmp_path: Path) -> None:
        """Clean files should produce exit code 0 and empty findings."""
        good_file = tmp_path / "skills" / "my-skill" / "scripts" / "helper.py"
        good_file.parent.mkdir(parents=True)
        good_file.write_text("import os\nprint('hi')\n")

        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(good_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["review_type"] == "implementation"
        assert output["reviewer_vendor"] == "structural-linter"
        assert output["findings"] == []

    def test_bad_import_exit_one(self, tmp_path: Path) -> None:
        """Files with dependency direction violations should produce exit code 1."""
        bad_file = tmp_path / "skills" / "test-skill" / "scripts" / "bad.py"
        bad_file.parent.mkdir(parents=True)
        bad_file.write_text("from agent_coordinator.src.locks import acquire_lock\n")

        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(bad_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert len(output["findings"]) >= 1
        # Should have a high-criticality finding (blocking)
        assert any(f["criticality"] == "high" for f in output["findings"])

    def test_medium_finding_exit_zero(self, tmp_path: Path) -> None:
        """Files with only medium findings (file-size) should exit 0."""
        big_file = tmp_path / "skills" / "my-skill" / "scripts" / "big_file.py"
        big_file.parent.mkdir(parents=True)
        big_file.write_text("x = 1\n" * 600)

        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(big_file), "--max-lines", "500"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["findings"]) >= 1
        # All findings should be medium (non-blocking)
        assert all(f["criticality"] == "medium" for f in output["findings"])

    def test_nonexistent_files_exit_zero(self, tmp_path: Path) -> None:
        """Nonexistent files should exit 0 with empty findings."""
        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(tmp_path / "does_not_exist.py")],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["findings"] == []

    def test_custom_target(self, tmp_path: Path) -> None:
        """Custom --target should appear in the output."""
        good_file = tmp_path / "skills" / "my-skill" / "scripts" / "ok.py"
        good_file.parent.mkdir(parents=True)
        good_file.write_text("import os\n")

        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(good_file), "--target", "my-pkg"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["target"] == "my-pkg"

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        """Output should always be valid JSON on stdout."""
        mixed_file = tmp_path / "skills" / "bad_skill" / "scripts" / "analyze-stuff.py"
        mixed_file.parent.mkdir(parents=True)
        mixed_file.write_text("from agent_coordinator.src.locks import x\n" + "y = 1\n" * 550)

        result = subprocess.run(
            [sys.executable, _RUNNER_SCRIPT, "--files", str(mixed_file)],
            capture_output=True,
            text=True,
        )

        # Must parse as JSON regardless of exit code
        output = json.loads(result.stdout)
        assert "review_type" in output
        assert "findings" in output
        assert isinstance(output["findings"], list)
