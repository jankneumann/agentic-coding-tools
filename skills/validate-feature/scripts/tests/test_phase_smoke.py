"""Tests for phase_smoke.py — the smoke test phase runner.

TDD tests written before implementation (task 5.3).
Tests cover:
- Loads .test-env and sets env vars
- Runs pytest subprocess
- Generates validation-report.md with correct format
- Missing .test-env produces JSON error
- Replaces existing ## Smoke Tests section (no duplicates)
- Mock subprocess.run for pytest invocation
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from phase_smoke import (
    append_smoke_section,
    load_test_env,
    main,
    parse_pytest_output,
    run_smoke_tests,
)


class TestLoadTestEnv:
    """Test loading .test-env file."""

    def test_loads_env_vars_from_file(self, tmp_path: Path) -> None:
        """Should parse .test-env and return dict of env vars."""
        test_env = tmp_path / ".test-env"
        test_env.write_text(
            "TEST_ENV_TYPE=docker\n"
            "POSTGRES_DSN=postgresql://localhost/test\n"
            "API_BASE_URL=http://localhost:8000\n"
            "SEED_STRATEGY=migrations\n"
            "STARTED_AT=2026-03-31T20:00:00Z\n"
        )

        result = load_test_env(str(test_env))

        assert result["TEST_ENV_TYPE"] == "docker"
        assert result["POSTGRES_DSN"] == "postgresql://localhost/test"
        assert result["API_BASE_URL"] == "http://localhost:8000"

    def test_missing_file_raises_file_not_found(self) -> None:
        """Missing .test-env should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_test_env("/nonexistent/.test-env")

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        """Should skip comment and blank lines."""
        test_env = tmp_path / ".test-env"
        test_env.write_text(
            "# comment\n"
            "\n"
            "KEY=value\n"
            "  \n"
        )

        result = load_test_env(str(test_env))
        assert result == {"KEY": "value"}


class TestParsePytestOutput:
    """Test parsing pytest stdout for per-test results."""

    def test_parses_passed_tests(self) -> None:
        """Should extract passed test names and durations."""
        output = (
            "test_health.py::test_health_endpoint PASSED                    [50%]\n"
            "test_auth.py::test_no_credentials PASSED                       [100%]\n"
        )

        results = parse_pytest_output(output)

        assert len(results) == 2
        assert results[0]["test"] == "test_health.py::test_health_endpoint"
        assert results[0]["status"] == "pass"

    def test_parses_failed_tests(self) -> None:
        """Should extract failed test names."""
        output = (
            "test_health.py::test_health_endpoint FAILED                    [50%]\n"
            "test_auth.py::test_no_credentials PASSED                       [100%]\n"
        )

        results = parse_pytest_output(output)

        assert len(results) == 2
        assert results[0]["status"] == "fail"
        assert results[1]["status"] == "pass"

    def test_empty_output_returns_empty_list(self) -> None:
        """No pytest output returns empty list."""
        results = parse_pytest_output("")
        assert results == []


class TestAppendSmokeSection:
    """Test appending ## Smoke Tests section to validation-report.md."""

    def test_creates_new_report_file(self, tmp_path: Path) -> None:
        """Should create validation-report.md if absent."""
        report_path = str(tmp_path / "validation-report.md")

        results = [
            {"test": "test_health.py::test_health_endpoint", "status": "pass", "duration": "0.12s"},
        ]

        append_smoke_section(
            report_path=report_path,
            status="pass",
            env_type="docker",
            duration_seconds=1.5,
            results=results,
        )

        content = Path(report_path).read_text()
        assert "## Smoke Tests" in content
        assert "**Status**: pass" in content
        assert "**Environment**: docker" in content
        assert "test_health.py::test_health_endpoint" in content

    def test_appends_to_existing_report(self, tmp_path: Path) -> None:
        """Should append to existing validation-report.md."""
        report_path = str(tmp_path / "validation-report.md")
        Path(report_path).write_text("## Spec Compliance\n\nAll requirements met.\n")

        results = [
            {"test": "test_health.py::test_health_endpoint", "status": "pass", "duration": "0.12s"},
        ]

        append_smoke_section(
            report_path=report_path,
            status="pass",
            env_type="docker",
            duration_seconds=1.5,
            results=results,
        )

        content = Path(report_path).read_text()
        assert "## Spec Compliance" in content
        assert "## Smoke Tests" in content

    def test_replaces_existing_smoke_section(self, tmp_path: Path) -> None:
        """Should replace existing ## Smoke Tests section, not duplicate it."""
        report_path = str(tmp_path / "validation-report.md")
        Path(report_path).write_text(
            "## Spec Compliance\n\nAll requirements met.\n\n"
            "## Smoke Tests\n\n- **Status**: fail\n\nOld content.\n\n"
            "## Security\n\nSecurity checks passed.\n"
        )

        results = [
            {"test": "test_health.py::test_health_endpoint", "status": "pass", "duration": "0.12s"},
        ]

        append_smoke_section(
            report_path=report_path,
            status="pass",
            env_type="docker",
            duration_seconds=2.0,
            results=results,
        )

        content = Path(report_path).read_text()
        # Only one Smoke Tests section
        assert content.count("## Smoke Tests") == 1
        # New content
        assert "**Status**: pass" in content
        # Old content gone
        assert "**Status**: fail" not in content
        # Other sections preserved
        assert "## Spec Compliance" in content
        assert "## Security" in content

    def test_includes_iso_timestamp(self, tmp_path: Path) -> None:
        """Should include ISO 8601 timestamp."""
        report_path = str(tmp_path / "validation-report.md")

        append_smoke_section(
            report_path=report_path,
            status="pass",
            env_type="docker",
            duration_seconds=1.0,
            results=[],
        )

        content = Path(report_path).read_text()
        assert "**Timestamp**:" in content

    def test_includes_duration(self, tmp_path: Path) -> None:
        """Should include duration in seconds."""
        report_path = str(tmp_path / "validation-report.md")

        append_smoke_section(
            report_path=report_path,
            status="pass",
            env_type="neon",
            duration_seconds=3.5,
            results=[],
        )

        content = Path(report_path).read_text()
        assert "**Duration**: 3.5s" in content

    def test_fail_status_includes_failures_section(self, tmp_path: Path) -> None:
        """Failed tests should produce a Failures subsection."""
        report_path = str(tmp_path / "validation-report.md")

        results = [
            {"test": "test_health.py::test_health_endpoint", "status": "fail", "duration": "0.12s"},
        ]

        append_smoke_section(
            report_path=report_path,
            status="fail",
            env_type="docker",
            duration_seconds=2.0,
            results=results,
            failure_output="FAILED test_health.py::test_health_endpoint - AssertionError",
        )

        content = Path(report_path).read_text()
        assert "### Failures" in content


class TestRunSmokeTests:
    """Test the smoke test subprocess invocation."""

    @patch("phase_smoke.subprocess.run")
    def test_runs_pytest_with_env_vars(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Should run pytest with env vars from .test-env loaded into environment."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test_health.py::test_health_endpoint PASSED [100%]\n",
            stderr="",
        )

        env_vars = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }

        returncode, stdout, stderr = run_smoke_tests(env_vars)

        assert returncode == 0
        mock_run.assert_called_once()
        # Verify env vars were passed
        call_kwargs = mock_run.call_args
        passed_env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert passed_env["POSTGRES_DSN"] == "postgresql://localhost/test"
        assert passed_env["API_BASE_URL"] == "http://localhost:8000"

    @patch("phase_smoke.subprocess.run")
    def test_returns_failure_exit_code(self, mock_run: MagicMock) -> None:
        """Should return non-zero exit code on test failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="test_health.py::test_health_endpoint FAILED [100%]\n",
            stderr="",
        )

        returncode, stdout, stderr = run_smoke_tests({})
        assert returncode == 1


class TestMainCLI:
    """Test the main() CLI entry point."""

    @patch("phase_smoke.run_smoke_tests")
    def test_missing_test_env_produces_json_error(
        self, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Missing .test-env should produce JSON error on stderr and exit 1."""
        with patch(
            "sys.argv",
            ["phase_smoke.py", "--test-env", "/nonexistent/.test-env"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        error_data = json.loads(captured.err)
        assert "error" in error_data
        assert error_data["phase"] == "smoke"

    @patch("phase_smoke.run_smoke_tests")
    def test_success_writes_report(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Successful tests should write validation-report.md."""
        # Create .test-env
        test_env = tmp_path / ".test-env"
        test_env.write_text(
            "TEST_ENV_TYPE=docker\n"
            "POSTGRES_DSN=postgresql://localhost/test\n"
            "API_BASE_URL=http://localhost:8000\n"
        )

        mock_run.return_value = (
            0,
            "test_health.py::test_health_endpoint PASSED [100%]\n",
            "",
        )

        report_path = str(tmp_path / "validation-report.md")

        with patch(
            "sys.argv",
            [
                "phase_smoke.py",
                "--test-env",
                str(test_env),
                "--report",
                report_path,
            ],
        ):
            main()

        assert Path(report_path).exists()
        content = Path(report_path).read_text()
        assert "## Smoke Tests" in content
        assert "**Status**: pass" in content

    @patch("phase_smoke.run_smoke_tests")
    def test_failure_writes_fail_status(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Failed tests should write Status: fail."""
        test_env = tmp_path / ".test-env"
        test_env.write_text(
            "TEST_ENV_TYPE=docker\n"
            "POSTGRES_DSN=postgresql://localhost/test\n"
            "API_BASE_URL=http://localhost:8000\n"
        )

        mock_run.return_value = (
            1,
            "test_health.py::test_health_endpoint FAILED [100%]\n",
            "FAILED test_health.py",
        )

        report_path = str(tmp_path / "validation-report.md")

        with patch(
            "sys.argv",
            [
                "phase_smoke.py",
                "--test-env",
                str(test_env),
                "--report",
                report_path,
            ],
        ):
            # Should not raise SystemExit on test failures — it writes the report
            main()

        content = Path(report_path).read_text()
        assert "**Status**: fail" in content
