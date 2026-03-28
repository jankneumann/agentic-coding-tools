"""Tests for fix-scrub parallel quality verifier."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parallel_verify import verify_parallel
from verify import VerificationResult, verify


# ---------------------------------------------------------------------------
# All checks run and results collected
# ---------------------------------------------------------------------------


class TestAllChecksRun:
    """All four tools are invoked and results collected."""

    @patch("verify.subprocess.run")
    def test_all_tools_pass(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="all good\n",
            stderr="",
        )

        result = verify_parallel("/fake/project")

        assert result.passed is True
        assert result.checks == {
            "pytest": "pass",
            "mypy": "pass",
            "ruff": "pass",
            "openspec": "pass",
        }
        assert result.regressions == []
        assert result.messages == []
        assert mock_run.call_count == 4

    @patch("verify.subprocess.run")
    def test_all_tools_fail(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="failure\n",
            stderr="",
        )

        result = verify_parallel("/fake/project")

        assert result.passed is False
        assert all(v == "fail" for v in result.checks.values())
        assert len(result.checks) == 4


# ---------------------------------------------------------------------------
# Failed check doesn't abort others
# ---------------------------------------------------------------------------


class TestNoFailFast:
    """A failing check must not prevent other checks from running."""

    @patch("verify.subprocess.run")
    def test_pytest_fails_others_still_run(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout="FAILED test_x.py\n", stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify_parallel("/fake/project")

        assert result.checks["pytest"] == "fail"
        assert result.checks["mypy"] == "pass"
        assert result.checks["ruff"] == "pass"
        assert result.checks["openspec"] == "pass"
        assert mock_run.call_count == 4

    @patch("verify.subprocess.run")
    def test_multiple_failures_all_collected(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] in ("pytest", "ruff"):
                return MagicMock(returncode=1, stdout="failure\n", stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify_parallel("/fake/project")

        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        assert result.checks["ruff"] == "fail"
        assert result.checks["mypy"] == "pass"
        assert result.checks["openspec"] == "pass"


# ---------------------------------------------------------------------------
# Regression detection
# ---------------------------------------------------------------------------


class TestRegressionDetection:
    """Regression detection with original_failures works correctly."""

    @patch("verify.subprocess.run")
    def test_new_failures_detected_as_regressions(self, mock_run: MagicMock) -> None:
        pytest_output = (
            "FAILED tests/test_a.py::test_existing - assert 1 == 2\n"
            "FAILED tests/test_b.py::test_new_break - RuntimeError\n"
        )

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout=pytest_output, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "pytest": {"FAILED tests/test_a.py::test_existing - assert 1 == 2"},
        }

        result = verify_parallel("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        assert len(result.regressions) == 1
        assert "[pytest] NEW:" in result.regressions[0]
        assert "test_new_break" in result.regressions[0]

    @patch("verify.subprocess.run")
    def test_no_new_failures_means_no_regressions(self, mock_run: MagicMock) -> None:
        pytest_output = "FAILED tests/test_a.py::test_known - assert 1 == 2\n"

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout=pytest_output, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "pytest": {"FAILED tests/test_a.py::test_known - assert 1 == 2"},
        }

        result = verify_parallel("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        assert result.regressions == []

    @patch("verify.subprocess.run")
    def test_ruff_regression_detection(self, mock_run: MagicMock) -> None:
        ruff_json = (
            '[{"code": "F401", "filename": "src/new.py", '
            '"location": {"row": 1}, "message": "unused import"}]'
        )

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "ruff":
                return MagicMock(returncode=1, stdout=ruff_json, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures: dict[str, set[str]] = {"ruff": set()}

        result = verify_parallel("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["ruff"] == "fail"
        assert len(result.regressions) == 1
        assert "F401:src/new.py:1" in result.regressions[0]


# ---------------------------------------------------------------------------
# Tool unavailable handled gracefully
# ---------------------------------------------------------------------------


class TestToolUnavailable:
    """Missing tools are skipped gracefully."""

    @patch("verify.subprocess.run")
    def test_missing_tool_skipped_and_passes(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "openspec":
                raise FileNotFoundError("No such file or directory: 'openspec'")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify_parallel("/fake/project")

        assert result.checks["openspec"] == "pass"
        assert any("openspec" in msg and "skipped" in msg for msg in result.messages)
        assert result.passed is True

    @patch("verify.subprocess.run")
    def test_multiple_tools_missing_still_passes(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] in ("mypy", "ruff"):
                raise FileNotFoundError(f"No such file or directory: '{cmd[0]}'")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify_parallel("/fake/project")

        assert result.passed is True
        assert result.checks["mypy"] == "pass"
        assert result.checks["ruff"] == "pass"
        assert len(result.messages) == 2

    @patch("verify.subprocess.run")
    def test_timeout_handled(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "mypy":
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=300)
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify_parallel("/fake/project")

        assert result.checks["mypy"] == "fail"
        assert result.passed is False


# ---------------------------------------------------------------------------
# Equivalence with sequential verify()
# ---------------------------------------------------------------------------


class TestEquivalenceWithSequentialVerify:
    """parallel verify_parallel() produces the same VerificationResult as verify()."""

    @patch("verify.subprocess.run")
    def test_equivalent_all_pass(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="all good\n",
            stderr="",
        )

        seq_result = verify("/fake/project")
        par_result = verify_parallel("/fake/project")

        assert seq_result.to_dict() == par_result.to_dict()

    @patch("verify.subprocess.run")
    def test_equivalent_with_failures(self, mock_run: MagicMock) -> None:
        pytest_output = (
            "FAILED tests/test_a.py::test_existing - assert 1 == 2\n"
            "FAILED tests/test_b.py::test_new_break - RuntimeError\n"
        )

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout=pytest_output, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "pytest": {"FAILED tests/test_a.py::test_existing - assert 1 == 2"},
        }

        seq_result = verify("/fake/project", original_failures=original_failures)
        par_result = verify_parallel(
            "/fake/project", original_failures=original_failures
        )

        assert seq_result.to_dict() == par_result.to_dict()

    @patch("verify.subprocess.run")
    def test_equivalent_mixed_scenario(self, mock_run: MagicMock) -> None:
        mypy_output = "src/foo.py:10: error: Incompatible return value\n"

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=0, stdout="3 passed\n", stderr="")
            if cmd[0] == "mypy":
                return MagicMock(returncode=1, stdout=mypy_output, stderr="")
            if cmd[0] == "ruff":
                return MagicMock(returncode=0, stdout="[]\n", stderr="")
            return MagicMock(returncode=0, stdout="valid\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "mypy": {"src/bar.py:5: error: Name 'x' is not defined"},
        }

        seq_result = verify("/fake/project", original_failures=original_failures)
        par_result = verify_parallel(
            "/fake/project", original_failures=original_failures
        )

        assert seq_result.to_dict() == par_result.to_dict()

    @patch("verify.subprocess.run")
    def test_equivalent_tool_not_available(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "openspec":
                raise FileNotFoundError("No such file or directory: 'openspec'")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        seq_result = verify("/fake/project")
        par_result = verify_parallel("/fake/project")

        assert seq_result.to_dict() == par_result.to_dict()
