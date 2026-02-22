"""Tests for fix-scrub post-fix quality verifier."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify import VerificationResult, verify


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_to_dict(self) -> None:
        result = VerificationResult(
            passed=True,
            checks={"pytest": "pass", "mypy": "pass"},
            regressions=[],
            messages=["mypy: skipped (not available)"],
        )
        d = result.to_dict()
        assert d == {
            "passed": True,
            "checks": {"pytest": "pass", "mypy": "pass"},
            "regressions": [],
            "messages": ["mypy: skipped (not available)"],
        }

    def test_to_dict_with_regressions(self) -> None:
        result = VerificationResult(
            passed=False,
            checks={"pytest": "fail"},
            regressions=["[pytest] NEW: FAILED tests/test_x.py::test_bad"],
            messages=[],
        )
        d = result.to_dict()
        assert d["passed"] is False
        assert len(d["regressions"]) == 1


# ---------------------------------------------------------------------------
# All-pass scenario
# ---------------------------------------------------------------------------


class TestVerifyAllPass:
    """All tools return exit code 0 -- verification should pass."""

    @patch("verify.subprocess.run")
    def test_all_tools_pass(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="all good\n",
            stderr="",
        )

        result = verify("/fake/project")

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


# ---------------------------------------------------------------------------
# Regression detection
# ---------------------------------------------------------------------------


class TestVerifyRegressionDetection:
    """New failures that were NOT in the original set are flagged as regressions."""

    @patch("verify.subprocess.run")
    def test_new_failures_detected_as_regressions(self, mock_run: MagicMock) -> None:
        """pytest fails with two FAILED lines; one is new, one is original."""
        pytest_output = (
            "FAILED tests/test_a.py::test_existing - assert 1 == 2\n"
            "FAILED tests/test_b.py::test_new_break - RuntimeError\n"
        )

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout=pytest_output, stderr="")
            # All other tools pass
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "pytest": {"FAILED tests/test_a.py::test_existing - assert 1 == 2"},
        }

        result = verify("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        assert len(result.regressions) == 1
        assert "[pytest] NEW:" in result.regressions[0]
        assert "test_new_break" in result.regressions[0]

    @patch("verify.subprocess.run")
    def test_no_new_failures_means_no_regressions(self, mock_run: MagicMock) -> None:
        """pytest fails, but all failures were already known -- no regression."""
        pytest_output = "FAILED tests/test_a.py::test_known - assert 1 == 2\n"

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=1, stdout=pytest_output, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "pytest": {"FAILED tests/test_a.py::test_known - assert 1 == 2"},
        }

        result = verify("/fake/project", original_failures=original_failures)

        # pytest still fails, so passed is False (check itself failed)
        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        # But no new regressions
        assert result.regressions == []


# ---------------------------------------------------------------------------
# Partial regression: some tools pass, some fail
# ---------------------------------------------------------------------------


class TestVerifyPartialRegression:
    """Some tools pass while others fail -- mixed results."""

    @patch("verify.subprocess.run")
    def test_mixed_pass_and_fail(self, mock_run: MagicMock) -> None:
        mypy_output = "src/foo.py:10: error: Incompatible return value\n"

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "pytest":
                return MagicMock(returncode=0, stdout="3 passed\n", stderr="")
            if cmd[0] == "mypy":
                return MagicMock(returncode=1, stdout=mypy_output, stderr="")
            if cmd[0] == "ruff":
                return MagicMock(returncode=0, stdout="[]\n", stderr="")
            # openspec
            return MagicMock(returncode=0, stdout="valid\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures = {
            "mypy": {"src/bar.py:5: error: Name 'x' is not defined"},
        }

        result = verify("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["pytest"] == "pass"
        assert result.checks["mypy"] == "fail"
        assert result.checks["ruff"] == "pass"
        assert result.checks["openspec"] == "pass"
        # The mypy failure is new (different from original)
        assert len(result.regressions) == 1
        assert "[mypy] NEW:" in result.regressions[0]
        assert "Incompatible return value" in result.regressions[0]


# ---------------------------------------------------------------------------
# Tool not available (FileNotFoundError -> skip, still passes)
# ---------------------------------------------------------------------------


class TestVerifyToolNotAvailable:
    """When a tool binary is missing, it raises FileNotFoundError and is skipped."""

    @patch("verify.subprocess.run")
    def test_missing_tool_skipped_and_passes(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "openspec":
                raise FileNotFoundError("No such file or directory: 'openspec'")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify("/fake/project")

        # openspec was skipped (FileNotFoundError -> True, "not available")
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

        result = verify("/fake/project")

        assert result.passed is True
        assert result.checks["mypy"] == "pass"
        assert result.checks["ruff"] == "pass"
        assert len(result.messages) == 2


# ---------------------------------------------------------------------------
# passed flag is False when regressions exist
# ---------------------------------------------------------------------------


class TestPassedFlagWithRegressions:
    """Verify that passed is False when regressions are detected."""

    @patch("verify.subprocess.run")
    def test_passed_false_when_regressions_present(self, mock_run: MagicMock) -> None:
        ruff_json = (
            '[{"code": "F401", "filename": "src/new.py", '
            '"location": {"row": 1}, "message": "unused import"}]'
        )

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "ruff":
                return MagicMock(returncode=1, stdout=ruff_json, stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        original_failures: dict[str, set[str]] = {
            "ruff": set(),  # No original ruff failures -> everything is a regression
        }

        result = verify("/fake/project", original_failures=original_failures)

        assert result.passed is False
        assert result.checks["ruff"] == "fail"
        assert len(result.regressions) == 1
        assert "F401:src/new.py:1" in result.regressions[0]


# ---------------------------------------------------------------------------
# passed flag is False when any check fails
# ---------------------------------------------------------------------------


class TestPassedFlagWithCheckFailures:
    """Verify that passed is False even without regression tracking when a tool fails."""

    @patch("verify.subprocess.run")
    def test_passed_false_on_tool_failure_no_original(
        self, mock_run: MagicMock
    ) -> None:
        """Tool fails but no original_failures provided -- no regression tracking,
        but passed is still False because a check failed."""

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "mypy":
                return MagicMock(
                    returncode=1,
                    stdout="src/x.py:1: error: Something wrong\n",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify("/fake/project")

        assert result.passed is False
        assert result.checks["mypy"] == "fail"
        # No regression tracking since original_failures not provided for mypy
        assert result.regressions == []

    @patch("verify.subprocess.run")
    def test_passed_false_when_multiple_tools_fail(
        self, mock_run: MagicMock
    ) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] in ("pytest", "ruff"):
                return MagicMock(returncode=1, stdout="failure\n", stderr="")
            return MagicMock(returncode=0, stdout="ok\n", stderr="")

        mock_run.side_effect = side_effect

        result = verify("/fake/project")

        assert result.passed is False
        assert result.checks["pytest"] == "fail"
        assert result.checks["ruff"] == "fail"
        assert result.checks["mypy"] == "pass"
        assert result.checks["openspec"] == "pass"
