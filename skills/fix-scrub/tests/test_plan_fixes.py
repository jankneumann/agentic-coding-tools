"""Tests for fix planner: grouping, tier separation, limits, and summaries."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from fix_models import ClassifiedFinding, Finding, FixGroup, FixPlan  # noqa: E402
from plan_fixes import plan  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    id: str = "f-1",
    source: str = "ruff",
    severity: str = "medium",
    category: str = "lint",
    title: str = "dummy finding",
    file_path: str = "src/app.py",
    line: int | None = None,
) -> Finding:
    return Finding(
        id=id,
        source=source,
        severity=severity,
        category=category,
        title=title,
        file_path=file_path,
        line=line,
    )


def _make_classified(
    *,
    id: str = "f-1",
    tier: str = "agent",
    severity: str = "medium",
    file_path: str = "src/app.py",
    fix_strategy: str = "",
    source: str = "ruff",
    category: str = "lint",
    title: str = "dummy finding",
) -> ClassifiedFinding:
    finding = _make_finding(
        id=id,
        source=source,
        severity=severity,
        category=category,
        title=title,
        file_path=file_path,
    )
    return ClassifiedFinding(
        finding=finding,
        tier=tier,
        fix_strategy=fix_strategy,
    )


# ---------------------------------------------------------------------------
# File grouping
# ---------------------------------------------------------------------------


class TestFileGrouping:
    """Findings with the same file_path are grouped together."""

    def test_auto_findings_grouped_by_file(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="src/a.py"),
            _make_classified(id="f-2", tier="auto", file_path="src/a.py"),
            _make_classified(id="f-3", tier="auto", file_path="src/b.py"),
        ]
        result = plan(classified)

        assert len(result.auto_groups) == 2
        paths = [g.file_path for g in result.auto_groups]
        assert "src/a.py" in paths
        assert "src/b.py" in paths

        a_group = next(g for g in result.auto_groups if g.file_path == "src/a.py")
        assert len(a_group.classified_findings) == 2

        b_group = next(g for g in result.auto_groups if g.file_path == "src/b.py")
        assert len(b_group.classified_findings) == 1

    def test_agent_findings_grouped_by_file(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="agent", file_path="lib/x.py"),
            _make_classified(id="f-2", tier="agent", file_path="lib/x.py"),
            _make_classified(id="f-3", tier="agent", file_path="lib/y.py"),
        ]
        result = plan(classified)

        assert len(result.agent_groups) == 2
        x_group = next(g for g in result.agent_groups if g.file_path == "lib/x.py")
        assert len(x_group.classified_findings) == 2

    def test_groups_sorted_by_file_path(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="z.py"),
            _make_classified(id="f-2", tier="auto", file_path="a.py"),
            _make_classified(id="f-3", tier="auto", file_path="m.py"),
        ]
        result = plan(classified)
        paths = [g.file_path for g in result.auto_groups]
        assert paths == ["a.py", "m.py", "z.py"]

    def test_no_file_path_uses_sentinel(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path=""),
        ]
        result = plan(classified)
        assert len(result.auto_groups) == 1
        assert result.auto_groups[0].file_path == "__no_file__"


# ---------------------------------------------------------------------------
# Auto / Agent / Manual separation
# ---------------------------------------------------------------------------


class TestTierSeparation:
    """Findings land in the correct plan section based on their tier."""

    def test_auto_goes_to_auto_groups(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
        ]
        result = plan(classified)
        assert len(result.auto_groups) == 1
        assert len(result.agent_groups) == 0
        assert len(result.manual_findings) == 0

    def test_agent_goes_to_agent_groups(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="agent", file_path="a.py"),
        ]
        result = plan(classified)
        assert len(result.auto_groups) == 0
        assert len(result.agent_groups) == 1
        assert len(result.manual_findings) == 0

    def test_manual_goes_to_manual_findings(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="manual", file_path="a.py"),
        ]
        result = plan(classified)
        assert len(result.auto_groups) == 0
        assert len(result.agent_groups) == 0
        assert len(result.manual_findings) == 1

    def test_mixed_tiers_separated_correctly(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
            _make_classified(id="f-2", tier="agent", file_path="b.py"),
            _make_classified(id="f-3", tier="manual", file_path="c.py"),
            _make_classified(id="f-4", tier="auto", file_path="a.py"),
            _make_classified(id="f-5", tier="agent", file_path="d.py"),
        ]
        result = plan(classified)
        assert len(result.auto_groups) == 1  # a.py
        assert len(result.agent_groups) == 2  # b.py, d.py
        assert len(result.manual_findings) == 1  # c.py

        auto_ids = [
            cf.finding.id
            for g in result.auto_groups
            for cf in g.classified_findings
        ]
        assert sorted(auto_ids) == ["f-1", "f-4"]


# ---------------------------------------------------------------------------
# Max agent fixes limit
# ---------------------------------------------------------------------------


class TestMaxAgentFixesLimit:
    """Agent-tier findings are capped at max_agent_fixes, highest severity first."""

    def test_limit_selects_highest_severity(self) -> None:
        classified = [
            _make_classified(id="f-lo", tier="agent", severity="low", file_path="a.py"),
            _make_classified(id="f-cr", tier="agent", severity="critical", file_path="b.py"),
            _make_classified(id="f-hi", tier="agent", severity="high", file_path="c.py"),
            _make_classified(id="f-me", tier="agent", severity="medium", file_path="d.py"),
        ]
        result = plan(classified, max_agent_fixes=2)

        agent_ids = [
            cf.finding.id
            for g in result.agent_groups
            for cf in g.classified_findings
        ]
        # Critical and high should be selected (top 2 by severity)
        assert "f-cr" in agent_ids
        assert "f-hi" in agent_ids
        assert len(agent_ids) == 2

    def test_limit_exactly_at_boundary(self) -> None:
        classified = [
            _make_classified(id=f"f-{i}", tier="agent", severity="medium", file_path="a.py")
            for i in range(5)
        ]
        result = plan(classified, max_agent_fixes=5)

        agent_count = sum(
            len(g.classified_findings) for g in result.agent_groups
        )
        assert agent_count == 5
        assert len(result.manual_findings) == 0

    def test_limit_zero_moves_all_to_manual(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="agent", severity="critical", file_path="a.py"),
            _make_classified(id="f-2", tier="agent", severity="high", file_path="b.py"),
        ]
        result = plan(classified, max_agent_fixes=0)

        assert len(result.agent_groups) == 0
        assert len(result.manual_findings) == 2

    def test_auto_and_manual_unaffected_by_limit(self) -> None:
        classified = [
            _make_classified(id="f-auto", tier="auto", file_path="a.py"),
            _make_classified(id="f-manual", tier="manual", file_path="b.py"),
            _make_classified(id="f-agent", tier="agent", severity="high", file_path="c.py"),
        ]
        result = plan(classified, max_agent_fixes=0)

        # Auto still present
        assert len(result.auto_groups) == 1
        # Original manual finding plus deferred agent finding
        assert len(result.manual_findings) == 2


# ---------------------------------------------------------------------------
# Excess agent findings moved to manual
# ---------------------------------------------------------------------------


class TestExcessAgentToManual:
    """Findings beyond max_agent_fixes are deferred to manual with explanation."""

    def test_deferred_findings_in_manual(self) -> None:
        classified = [
            _make_classified(id="f-cr", tier="agent", severity="critical", file_path="a.py"),
            _make_classified(id="f-hi", tier="agent", severity="high", file_path="b.py"),
            _make_classified(id="f-lo", tier="agent", severity="low", file_path="c.py"),
        ]
        result = plan(classified, max_agent_fixes=1)

        # Only critical should be in agent groups
        agent_ids = [
            cf.finding.id
            for g in result.agent_groups
            for cf in g.classified_findings
        ]
        assert agent_ids == ["f-cr"]

        # High and low should be deferred to manual
        assert len(result.manual_findings) == 2

    def test_deferred_findings_have_explanation(self) -> None:
        classified = [
            _make_classified(id="f-cr", tier="agent", severity="critical", file_path="a.py"),
            _make_classified(id="f-lo", tier="agent", severity="low", file_path="b.py"),
        ]
        result = plan(classified, max_agent_fixes=1)

        deferred = result.manual_findings
        assert len(deferred) == 1
        assert deferred[0].tier == "manual"
        assert "Deferred" in deferred[0].fix_strategy
        assert "max-agent-fixes" in deferred[0].fix_strategy
        assert "(1)" in deferred[0].fix_strategy

    def test_deferred_preserves_finding_data(self) -> None:
        classified = [
            _make_classified(
                id="f-keep",
                tier="agent",
                severity="critical",
                file_path="a.py",
            ),
            _make_classified(
                id="f-defer",
                tier="agent",
                severity="low",
                file_path="b.py",
                title="low sev thing",
                source="mypy",
                category="type-error",
            ),
        ]
        result = plan(classified, max_agent_fixes=1)

        deferred = result.manual_findings
        assert len(deferred) == 1
        assert deferred[0].finding.id == "f-defer"
        assert deferred[0].finding.title == "low sev thing"
        assert deferred[0].finding.source == "mypy"
        assert deferred[0].finding.category == "type-error"
        assert deferred[0].finding.file_path == "b.py"

    def test_mixed_manual_and_deferred(self) -> None:
        """Original manual findings and deferred agent findings coexist."""
        classified = [
            _make_classified(id="f-m1", tier="manual", file_path="x.py"),
            _make_classified(id="f-a1", tier="agent", severity="high", file_path="a.py"),
            _make_classified(id="f-a2", tier="agent", severity="low", file_path="b.py"),
        ]
        result = plan(classified, max_agent_fixes=1)

        manual_ids = [cf.finding.id for cf in result.manual_findings]
        assert "f-m1" in manual_ids  # original manual
        assert "f-a2" in manual_ids  # deferred agent (lower severity)
        assert len(result.manual_findings) == 2


# ---------------------------------------------------------------------------
# Dry-run flag
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry-run produces the same plan structure without changing behavior."""

    def test_dry_run_produces_same_plan(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
            _make_classified(id="f-2", tier="agent", file_path="b.py"),
            _make_classified(id="f-3", tier="manual", file_path="c.py"),
        ]
        normal = plan(classified, dry_run=False)
        dry = plan(classified, dry_run=True)

        assert normal.summary == dry.summary
        assert len(normal.auto_groups) == len(dry.auto_groups)
        assert len(normal.agent_groups) == len(dry.agent_groups)
        assert len(normal.manual_findings) == len(dry.manual_findings)

    def test_dry_run_default_is_false(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
        ]
        result = plan(classified)
        # Just verifying the function runs without requiring dry_run
        assert result.summary["auto"] == 1

    def test_dry_run_with_limits(self) -> None:
        classified = [
            _make_classified(id=f"f-{i}", tier="agent", severity="medium", file_path="a.py")
            for i in range(5)
        ]
        result = plan(classified, max_agent_fixes=2, dry_run=True)

        assert result.summary["agent"] == 2
        assert result.summary["manual"] == 3


# ---------------------------------------------------------------------------
# Summary counts
# ---------------------------------------------------------------------------


class TestSummaryCounts:
    """Plan summary dict has correct auto/agent/manual/total counts."""

    def test_summary_all_tiers(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
            _make_classified(id="f-2", tier="auto", file_path="a.py"),
            _make_classified(id="f-3", tier="agent", file_path="b.py"),
            _make_classified(id="f-4", tier="manual", file_path="c.py"),
        ]
        result = plan(classified)

        assert result.summary["auto"] == 2
        assert result.summary["agent"] == 1
        assert result.summary["manual"] == 1
        assert result.summary["total"] == 4

    def test_summary_with_deferred(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="agent", severity="critical", file_path="a.py"),
            _make_classified(id="f-2", tier="agent", severity="high", file_path="b.py"),
            _make_classified(id="f-3", tier="agent", severity="low", file_path="c.py"),
        ]
        result = plan(classified, max_agent_fixes=1)

        assert result.summary["agent"] == 1
        assert result.summary["manual"] == 2  # deferred
        assert result.summary["total"] == 3

    def test_summary_only_manual(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="manual", file_path="a.py"),
            _make_classified(id="f-2", tier="manual", file_path="b.py"),
        ]
        result = plan(classified)

        assert result.summary["auto"] == 0
        assert result.summary["agent"] == 0
        assert result.summary["manual"] == 2
        assert result.summary["total"] == 2

    def test_summary_only_auto(self) -> None:
        classified = [
            _make_classified(id="f-1", tier="auto", file_path="a.py"),
        ]
        result = plan(classified)

        assert result.summary["auto"] == 1
        assert result.summary["agent"] == 0
        assert result.summary["manual"] == 0
        assert result.summary["total"] == 1


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """Plan handles empty classified findings list gracefully."""

    def test_empty_list_returns_empty_plan(self) -> None:
        result = plan([])

        assert result.auto_groups == []
        assert result.agent_groups == []
        assert result.manual_findings == []

    def test_empty_list_summary_all_zeros(self) -> None:
        result = plan([])

        assert result.summary["auto"] == 0
        assert result.summary["agent"] == 0
        assert result.summary["manual"] == 0
        assert result.summary["total"] == 0

    def test_empty_list_with_dry_run(self) -> None:
        result = plan([], dry_run=True)

        assert result.summary["total"] == 0

    def test_empty_list_with_max_agent_fixes(self) -> None:
        result = plan([], max_agent_fixes=5)

        assert result.summary["total"] == 0
