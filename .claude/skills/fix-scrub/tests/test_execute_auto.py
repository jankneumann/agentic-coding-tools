"""Tests for execute_auto module — auto-fix execution via ruff --fix."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from execute_auto import execute_auto_fixes  # noqa: E402
from fix_models import ClassifiedFinding, Finding, FixGroup  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    finding_id: str,
    file_path: str = "src/app.py",
    line: int = 10,
    severity: str = "low",
) -> Finding:
    """Create a minimal Finding for testing."""
    return Finding(
        id=finding_id,
        source="ruff",
        severity=severity,  # type: ignore[arg-type]
        category="lint",
        title=f"Violation {finding_id}",
        file_path=file_path,
        line=line,
    )


def _make_fix_group(
    file_path: str,
    findings: list[ClassifiedFinding],
) -> FixGroup:
    return FixGroup(file_path=file_path, classified_findings=findings)


def _classified(finding: Finding) -> ClassifiedFinding:
    return ClassifiedFinding(finding=finding, tier="auto", fix_strategy="ruff --fix")


# ---------------------------------------------------------------------------
# 1. Test ruff --fix invocation
# ---------------------------------------------------------------------------

class TestRuffFixInvocation:
    """Verify that ruff check --fix is called with the correct arguments."""

    @patch("execute_auto.subprocess.run")
    def test_calls_ruff_fix_with_sorted_file_list(self, mock_run: MagicMock) -> None:
        """ruff check --fix should receive sorted unique file paths."""
        # Return a successful CompletedProcess for both calls
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/b.py:5", file_path="src/b.py", line=5))
        f2 = _classified(_make_finding("ruff-F401-src/a.py:1", file_path="src/a.py", line=1))

        group_b = _make_fix_group("src/b.py", [f1])
        group_a = _make_fix_group("src/a.py", [f2])

        execute_auto_fixes([group_b, group_a], project_dir="/repo")

        # First call: ruff check --fix with sorted files
        first_call = mock_run.call_args_list[0]
        assert first_call == call(
            ["ruff", "check", "--fix", "src/a.py", "src/b.py"],
            capture_output=True,
            text=True,
            cwd="/repo",
        )

    @patch("execute_auto.subprocess.run")
    def test_deduplicates_files_across_groups(self, mock_run: MagicMock) -> None:
        """Multiple groups referencing the same file should only list it once."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/app.py:1", file_path="src/app.py", line=1))
        f2 = _classified(_make_finding("ruff-E501-src/app.py:2", file_path="src/app.py", line=2))

        group1 = _make_fix_group("src/app.py", [f1])
        group2 = _make_fix_group("src/app.py", [f2])

        execute_auto_fixes([group1, group2], project_dir="/repo")

        first_call_args = mock_run.call_args_list[0][0][0]
        # "src/app.py" should appear exactly once
        assert first_call_args.count("src/app.py") == 1


# ---------------------------------------------------------------------------
# 2. Test verification re-run after fix
# ---------------------------------------------------------------------------

class TestVerificationReRun:
    """After applying fixes, ruff is re-run with --output-format=json."""

    @patch("execute_auto.subprocess.run")
    def test_second_call_uses_json_output_format(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/app.py:10", file_path="src/app.py"))
        group = _make_fix_group("src/app.py", [f1])

        execute_auto_fixes([group], project_dir="/repo")

        assert mock_run.call_count == 2
        second_call = mock_run.call_args_list[1]
        assert second_call == call(
            ["ruff", "check", "--output-format=json", "src/app.py"],
            capture_output=True,
            text=True,
            cwd="/repo",
        )

    @patch("execute_auto.subprocess.run")
    def test_all_resolved_when_verification_returns_empty(
        self, mock_run: MagicMock
    ) -> None:
        """When re-run returns no violations, all findings are resolved."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        f2 = _classified(_make_finding("ruff-F401-src/app.py:1", line=1))
        group = _make_fix_group("src/app.py", [f1, f2])

        resolved, persisting = execute_auto_fixes([group], project_dir="/repo")

        assert len(resolved) == 2
        assert len(persisting) == 0


# ---------------------------------------------------------------------------
# 3. Test handling when ruff not available (FileNotFoundError)
# ---------------------------------------------------------------------------

class TestRuffNotAvailable:
    """When ruff is not installed, all findings persist."""

    @patch("execute_auto.subprocess.run", side_effect=FileNotFoundError("ruff"))
    def test_returns_all_findings_as_persisting(self, mock_run: MagicMock) -> None:
        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        f2 = _classified(_make_finding("ruff-W291-src/app.py:20", line=20))
        group = _make_fix_group("src/app.py", [f1, f2])

        resolved, persisting = execute_auto_fixes([group], project_dir="/repo")

        assert len(resolved) == 0
        assert len(persisting) == 2
        assert persisting[0].finding.id == "ruff-E501-src/app.py:10"
        assert persisting[1].finding.id == "ruff-W291-src/app.py:20"

    @patch("execute_auto.subprocess.run", side_effect=FileNotFoundError("ruff"))
    def test_ruff_not_found_calls_subprocess_once(self, mock_run: MagicMock) -> None:
        """Only the first ruff call should be attempted; bail immediately."""
        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        group = _make_fix_group("src/app.py", [f1])

        execute_auto_fixes([group], project_dir="/repo")

        # subprocess.run is called once (the --fix call), then FileNotFoundError
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# 4. Test partial fix resolution
# ---------------------------------------------------------------------------

class TestPartialFixResolution:
    """Some findings are resolved by ruff --fix, others persist."""

    @patch("execute_auto.subprocess.run")
    def test_mixed_resolved_and_persisting(self, mock_run: MagicMock) -> None:
        """E501 persists (still reported), F401 is resolved (not reported)."""
        remaining_json = json.dumps([
            {
                "filename": "src/app.py",
                "location": {"row": 10},
                "code": "E501",
            },
        ])

        # First call (--fix): success
        fix_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        # Second call (--output-format=json): one remaining violation
        verify_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=remaining_json, stderr=""
        )
        mock_run.side_effect = [fix_result, verify_result]

        f_e501 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        f_f401 = _classified(_make_finding("ruff-F401-src/app.py:1", line=1))
        group = _make_fix_group("src/app.py", [f_e501, f_f401])

        resolved, persisting = execute_auto_fixes([group], project_dir="/repo")

        assert len(persisting) == 1
        assert persisting[0].finding.id == "ruff-E501-src/app.py:10"

        assert len(resolved) == 1
        assert resolved[0].finding.id == "ruff-F401-src/app.py:1"

    @patch("execute_auto.subprocess.run")
    def test_multiple_files_partial_resolution(self, mock_run: MagicMock) -> None:
        """Findings across multiple files: some resolved, some not."""
        remaining_json = json.dumps([
            {
                "filename": "src/a.py",
                "location": {"row": 5},
                "code": "E501",
            },
            {
                "filename": "src/b.py",
                "location": {"row": 3},
                "code": "W291",
            },
        ])

        fix_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        verify_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=remaining_json, stderr=""
        )
        mock_run.side_effect = [fix_result, verify_result]

        f1 = _classified(_make_finding("ruff-E501-src/a.py:5", file_path="src/a.py", line=5))
        f2 = _classified(_make_finding("ruff-F401-src/a.py:10", file_path="src/a.py", line=10))
        f3 = _classified(_make_finding("ruff-W291-src/b.py:3", file_path="src/b.py", line=3))

        group_a = _make_fix_group("src/a.py", [f1, f2])
        group_b = _make_fix_group("src/b.py", [f3])

        resolved, persisting = execute_auto_fixes(
            [group_a, group_b], project_dir="/repo"
        )

        persisting_ids = {cf.finding.id for cf in persisting}
        resolved_ids = {cf.finding.id for cf in resolved}

        assert "ruff-E501-src/a.py:5" in persisting_ids
        assert "ruff-W291-src/b.py:3" in persisting_ids
        assert "ruff-F401-src/a.py:10" in resolved_ids

    @patch("execute_auto.subprocess.run")
    def test_verification_json_decode_error_treats_all_as_resolved(
        self, mock_run: MagicMock
    ) -> None:
        """If verification JSON is unparseable, remaining_violations is empty
        and all findings are treated as resolved."""
        fix_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        verify_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not valid json", stderr=""
        )
        mock_run.side_effect = [fix_result, verify_result]

        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        group = _make_fix_group("src/app.py", [f1])

        resolved, persisting = execute_auto_fixes([group], project_dir="/repo")

        # JSONDecodeError caught => remaining_violations = set()
        # => all findings resolved
        assert len(resolved) == 1
        assert len(persisting) == 0


# ---------------------------------------------------------------------------
# 5. Test empty auto_groups
# ---------------------------------------------------------------------------

class TestEmptyAutoGroups:
    """An empty auto_groups list should short-circuit with empty results."""

    def test_empty_list_returns_empty_tuples(self) -> None:
        resolved, persisting = execute_auto_fixes([], project_dir="/repo")
        assert resolved == []
        assert persisting == []

    @patch("execute_auto.subprocess.run")
    def test_subprocess_not_called_for_empty_groups(
        self, mock_run: MagicMock
    ) -> None:
        execute_auto_fixes([], project_dir="/repo")
        mock_run.assert_not_called()

    @patch("execute_auto.subprocess.run")
    def test_no_file_groups_returns_all_persisting(
        self, mock_run: MagicMock
    ) -> None:
        """Groups with __no_file__ sentinel have no files to fix."""
        f1 = _classified(
            _make_finding("ruff-E501-__no_file__:0", file_path="__no_file__", line=0)
        )
        group = _make_fix_group("__no_file__", [f1])

        resolved, persisting = execute_auto_fixes([group], project_dir="/repo")

        # No real files => short-circuit with all findings persisting
        assert len(resolved) == 0
        assert len(persisting) == 1
        mock_run.assert_not_called()
