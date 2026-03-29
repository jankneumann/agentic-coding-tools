"""Tests for parallel_auto module — concurrent auto-fix execution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fix_models import ClassifiedFinding, Finding, FixGroup  # noqa: E402
from parallel_auto import execute_auto_fixes_parallel  # noqa: E402
from plan_fixes import assert_no_file_overlap  # noqa: E402


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
# 1. Parallel execution of non-overlapping groups
# ---------------------------------------------------------------------------

class TestParallelExecution:
    """Non-overlapping groups are dispatched concurrently."""

    @patch("execute_auto.subprocess.run")
    def test_parallel_two_groups_all_resolved(self, mock_run: MagicMock) -> None:
        """Two non-overlapping groups, all findings resolved."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/a.py:1", file_path="src/a.py", line=1))
        f2 = _classified(_make_finding("ruff-F401-src/b.py:5", file_path="src/b.py", line=5))

        group_a = _make_fix_group("src/a.py", [f1])
        group_b = _make_fix_group("src/b.py", [f2])

        resolved, persisting = execute_auto_fixes_parallel(
            [group_a, group_b], project_dir="/repo", max_workers=2,
        )

        assert len(resolved) == 2
        assert len(persisting) == 0

    @patch("execute_auto.subprocess.run")
    def test_parallel_three_groups_mixed_results(self, mock_run: MagicMock) -> None:
        """Three groups: first all resolved, second has persisting, third all resolved."""
        # Each group triggers 2 subprocess calls (fix + verify).
        # We need to handle interleaved calls from threads.
        # Use a side_effect function keyed on the file argument.
        def side_effect(args, **kwargs):
            file_arg = [a for a in args if a.endswith(".py")]
            if not file_arg:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="[]", stderr="")

            if "--output-format=json" in args and "src/b.py" in file_arg:
                remaining = json.dumps([
                    {"filename": "src/b.py", "location": {"row": 3}, "code": "W291"},
                ])
                return subprocess.CompletedProcess(args=args, returncode=1, stdout=remaining, stderr="")

            return subprocess.CompletedProcess(args=args, returncode=0, stdout="[]", stderr="")

        mock_run.side_effect = side_effect

        f1 = _classified(_make_finding("ruff-E501-src/a.py:1", file_path="src/a.py", line=1))
        f2 = _classified(_make_finding("ruff-W291-src/b.py:3", file_path="src/b.py", line=3))
        f3 = _classified(_make_finding("ruff-F401-src/c.py:10", file_path="src/c.py", line=10))

        group_a = _make_fix_group("src/a.py", [f1])
        group_b = _make_fix_group("src/b.py", [f2])
        group_c = _make_fix_group("src/c.py", [f3])

        resolved, persisting = execute_auto_fixes_parallel(
            [group_a, group_b, group_c], project_dir="/repo", max_workers=3,
        )

        assert len(resolved) == 2
        assert len(persisting) == 1
        assert persisting[0].finding.id == "ruff-W291-src/b.py:3"


# ---------------------------------------------------------------------------
# 2. Resolved and persisting findings collected correctly
# ---------------------------------------------------------------------------

class TestResultCollection:
    """Results from all groups are aggregated into the returned tuple."""

    @patch("execute_auto.subprocess.run")
    def test_findings_from_all_groups_present(self, mock_run: MagicMock) -> None:
        """Every finding from every group appears in either resolved or persisting."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        findings = []
        groups = []
        for i in range(4):
            fp = f"src/file{i}.py"
            f = _classified(_make_finding(f"ruff-E501-{fp}:{i}", file_path=fp, line=i))
            findings.append(f)
            groups.append(_make_fix_group(fp, [f]))

        resolved, persisting = execute_auto_fixes_parallel(
            groups, project_dir="/repo", max_workers=4,
        )

        all_ids = {cf.finding.id for cf in resolved} | {cf.finding.id for cf in persisting}
        expected_ids = {f.finding.id for f in findings}
        assert all_ids == expected_ids


# ---------------------------------------------------------------------------
# 3. Overlap assertion
# ---------------------------------------------------------------------------

class TestAssertNoFileOverlap:
    """assert_no_file_overlap validates that no file appears in multiple groups."""

    def test_raises_on_overlapping_groups(self) -> None:
        f1 = _classified(_make_finding("ruff-E501-src/app.py:1", line=1))
        f2 = _classified(_make_finding("ruff-F401-src/app.py:5", line=5))

        group1 = _make_fix_group("src/app.py", [f1])
        group2 = _make_fix_group("src/app.py", [f2])

        with pytest.raises(AssertionError, match="File overlap detected"):
            assert_no_file_overlap([group1, group2])

    def test_passes_on_non_overlapping_groups(self) -> None:
        f1 = _classified(_make_finding("ruff-E501-src/a.py:1", file_path="src/a.py", line=1))
        f2 = _classified(_make_finding("ruff-F401-src/b.py:1", file_path="src/b.py", line=1))

        group_a = _make_fix_group("src/a.py", [f1])
        group_b = _make_fix_group("src/b.py", [f2])

        # Should not raise
        assert_no_file_overlap([group_a, group_b])

    def test_empty_groups_passes(self) -> None:
        assert_no_file_overlap([])

    def test_single_group_passes(self) -> None:
        f1 = _classified(_make_finding("ruff-E501-src/app.py:1"))
        group = _make_fix_group("src/app.py", [f1])
        assert_no_file_overlap([group])

    def test_error_message_lists_overlapping_files(self) -> None:
        f1 = _classified(_make_finding("ruff-E501-src/app.py:1", line=1))
        f2 = _classified(_make_finding("ruff-F401-src/app.py:5", line=5))

        group1 = _make_fix_group("src/app.py", [f1])
        group2 = _make_fix_group("src/app.py", [f2])

        with pytest.raises(AssertionError, match="src/app.py"):
            assert_no_file_overlap([group1, group2])


# ---------------------------------------------------------------------------
# 4. Single group (degenerate case)
# ---------------------------------------------------------------------------

class TestSingleGroup:
    """A single group should work correctly through the parallel path."""

    @patch("execute_auto.subprocess.run")
    def test_single_group_resolved(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        group = _make_fix_group("src/app.py", [f1])

        resolved, persisting = execute_auto_fixes_parallel(
            [group], project_dir="/repo", max_workers=1,
        )

        assert len(resolved) == 1
        assert len(persisting) == 0

    @patch("execute_auto.subprocess.run")
    def test_single_group_persisting(self, mock_run: MagicMock) -> None:
        remaining = json.dumps([
            {"filename": "src/app.py", "location": {"row": 10}, "code": "E501"},
        ])
        fix_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        verify_result = subprocess.CompletedProcess(args=[], returncode=1, stdout=remaining, stderr="")
        mock_run.side_effect = [fix_result, verify_result]

        f1 = _classified(_make_finding("ruff-E501-src/app.py:10"))
        group = _make_fix_group("src/app.py", [f1])

        resolved, persisting = execute_auto_fixes_parallel(
            [group], project_dir="/repo", max_workers=1,
        )

        assert len(resolved) == 0
        assert len(persisting) == 1


# ---------------------------------------------------------------------------
# 5. Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Empty auto_groups should short-circuit."""

    def test_empty_list_returns_empty_tuples(self) -> None:
        resolved, persisting = execute_auto_fixes_parallel([], project_dir="/repo")
        assert resolved == []
        assert persisting == []

    @patch("execute_auto.subprocess.run")
    def test_subprocess_not_called_for_empty_groups(self, mock_run: MagicMock) -> None:
        execute_auto_fixes_parallel([], project_dir="/repo")
        mock_run.assert_not_called()
