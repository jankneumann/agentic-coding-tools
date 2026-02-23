"""Tests for finding fixability classifier."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
# bug-scrub models are imported transitively via fix-scrub models

import pytest  # noqa: E402

from classify import classify, classify_finding  # noqa: E402
from fix_models import Finding  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    id: str = "test-001",
    source: str = "ruff",
    severity: str = "medium",
    category: str = "lint",
    title: str = "Test finding",
    detail: str = "",
    file_path: str = "src/app.py",
    line: int | None = 1,
) -> Finding:
    return Finding(
        id=id,
        source=source,
        severity=severity,
        category=category,
        title=title,
        detail=detail,
        file_path=file_path,
        line=line,
    )


# ---------------------------------------------------------------------------
# 1. Auto tier: ruff findings with fixable rule prefixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    ["E", "W", "I", "UP", "B", "SIM", "RUF", "D", "C4", "PT", "RSE", "RET", "TCH", "TID", "F"],
)
def test_auto_tier_ruff_fixable_prefixes(prefix: str) -> None:
    finding = _make_finding(
        id=f"ruff-{prefix}001-src/app.py:10",
        source="ruff",
        category="lint",
        title=f"Ruff {prefix}001 violation",
    )
    result = classify_finding(finding)
    assert result.tier == "auto"
    assert "ruff" in result.fix_strategy.lower()


def test_auto_tier_ruff_non_fixable_falls_through() -> None:
    finding = _make_finding(
        id="ruff-XYZ001-src/app.py:10",
        source="ruff",
        category="lint",
        title="Ruff XYZ001 violation",
    )
    result = classify_finding(finding)
    # Non-fixable ruff rules fall through to the default manual tier
    assert result.tier == "manual"


# ---------------------------------------------------------------------------
# 2. Agent tier: mypy type errors
# ---------------------------------------------------------------------------


def test_agent_tier_mypy_type_error() -> None:
    finding = _make_finding(
        id="mypy-err-src/app.py:5",
        source="mypy",
        severity="high",
        category="type-error",
        title="Incompatible return type",
        detail='error: Incompatible return type [return-value]',
    )
    result = classify_finding(finding)
    assert result.tier == "agent"
    assert "type annotation" in result.fix_strategy.lower()


# ---------------------------------------------------------------------------
# 3. Agent tier: markers with >=10 chars of context
# ---------------------------------------------------------------------------


def test_agent_tier_marker_sufficient_context() -> None:
    finding = _make_finding(
        id="marker-todo-src/app.py:20",
        source="markers",
        severity="low",
        category="code-marker",
        title="TODO marker",
        detail=": refactor this function to use async pattern",
    )
    result = classify_finding(finding)
    assert result.tier == "agent"
    assert "marker" in result.fix_strategy.lower()


def test_agent_tier_marker_exactly_10_chars() -> None:
    finding = _make_finding(
        id="marker-todo-src/app.py:30",
        source="markers",
        severity="low",
        category="code-marker",
        title="TODO marker",
        detail=": 0123456789",  # exactly 10 chars after stripping ": "
    )
    result = classify_finding(finding)
    assert result.tier == "agent"


# ---------------------------------------------------------------------------
# 4. Manual tier: markers with <10 chars of context
# ---------------------------------------------------------------------------


def test_manual_tier_marker_insufficient_context() -> None:
    finding = _make_finding(
        id="marker-todo-src/app.py:40",
        source="markers",
        severity="low",
        category="code-marker",
        title="TODO marker",
        detail=": fix",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"
    assert "insufficient context" in result.fix_strategy.lower()


def test_manual_tier_marker_empty_detail() -> None:
    finding = _make_finding(
        id="marker-fixme-src/app.py:50",
        source="markers",
        severity="low",
        category="code-marker",
        title="FIXME marker",
        detail="",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"


# ---------------------------------------------------------------------------
# 5. Agent tier: deferred findings with "proposed fix" in detail
# ---------------------------------------------------------------------------


def test_agent_tier_deferred_with_proposed_fix() -> None:
    finding = _make_finding(
        id="deferred-001",
        source="deferred:openspec",
        severity="medium",
        category="deferred-issue",
        title="Deferred schema migration",
        detail="Proposed fix: add nullable column then backfill",
    )
    result = classify_finding(finding)
    assert result.tier == "agent"
    assert "proposed fix" in result.fix_strategy.lower()


def test_agent_tier_deferred_with_resolution_keyword() -> None:
    finding = _make_finding(
        id="deferred-002",
        source="deferred:openspec",
        severity="medium",
        category="deferred-issue",
        title="Deferred API deprecation",
        detail="Resolution: replace v1 endpoint with v2 equivalent",
    )
    result = classify_finding(finding)
    assert result.tier == "agent"


# ---------------------------------------------------------------------------
# 6. Manual tier: architecture and security findings
# ---------------------------------------------------------------------------


def test_manual_tier_architecture_source() -> None:
    finding = _make_finding(
        id="arch-001",
        source="architecture",
        severity="high",
        category="architecture",
        title="Circular dependency detected",
        detail="Module A depends on Module B which depends on Module A",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"
    assert "design decision" in result.fix_strategy.lower() or "manual review" in result.fix_strategy.lower()


def test_manual_tier_security_source() -> None:
    finding = _make_finding(
        id="sec-001",
        source="security",
        severity="critical",
        category="security",
        title="Hardcoded credentials",
        detail="API key found in source code",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"


def test_manual_tier_security_category_different_source() -> None:
    finding = _make_finding(
        id="lint-sec-001",
        source="ruff",
        severity="high",
        category="security",
        title="Security-related lint finding",
        detail="S101 use of assert in production code",
    )
    # ruff source but security category -- _is_ruff_fixable won't match
    # because the id doesn't have a fixable prefix, then security category triggers manual
    result = classify_finding(finding)
    assert result.tier == "manual"


# ---------------------------------------------------------------------------
# 7. Manual tier: deferred without proposed fix
# ---------------------------------------------------------------------------


def test_manual_tier_deferred_without_proposed_fix() -> None:
    finding = _make_finding(
        id="deferred-003",
        source="deferred:openspec",
        severity="medium",
        category="deferred-issue",
        title="Deferred performance concern",
        detail="Query is slow but no clear solution yet",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"
    assert "investigation" in result.fix_strategy.lower() or "no clear proposed fix" in result.fix_strategy.lower()


# ---------------------------------------------------------------------------
# 8. Manual tier: unknown sources
# ---------------------------------------------------------------------------


def test_manual_tier_unknown_source() -> None:
    finding = _make_finding(
        id="unknown-001",
        source="custom-scanner",
        severity="medium",
        category="lint",
        title="Custom scanner finding",
        detail="Something found by a custom tool",
    )
    result = classify_finding(finding)
    assert result.tier == "manual"
    assert "unknown source" in result.fix_strategy.lower()


# ---------------------------------------------------------------------------
# 9. Severity filtering (findings below threshold excluded)
# ---------------------------------------------------------------------------


def test_severity_filter_excludes_below_threshold() -> None:
    findings = [
        _make_finding(id="high-001", severity="high", title="High severity"),
        _make_finding(id="med-001", severity="medium", title="Medium severity"),
        _make_finding(id="low-001", severity="low", title="Low severity"),
        _make_finding(id="info-001", severity="info", title="Info severity"),
    ]
    result = classify(findings, severity_filter="medium")
    assert len(result) == 2
    ids = {cf.finding.id for cf in result}
    assert ids == {"high-001", "med-001"}


def test_severity_filter_high_excludes_medium_and_below() -> None:
    findings = [
        _make_finding(id="crit-001", severity="critical", title="Critical"),
        _make_finding(id="high-001", severity="high", title="High"),
        _make_finding(id="med-001", severity="medium", title="Medium"),
        _make_finding(id="low-001", severity="low", title="Low"),
    ]
    result = classify(findings, severity_filter="high")
    assert len(result) == 2
    ids = {cf.finding.id for cf in result}
    assert ids == {"crit-001", "high-001"}


def test_severity_filter_info_includes_all() -> None:
    findings = [
        _make_finding(id="high-001", severity="high", title="High"),
        _make_finding(id="low-001", severity="low", title="Low"),
        _make_finding(id="info-001", severity="info", title="Info"),
    ]
    result = classify(findings, severity_filter="info")
    assert len(result) == 3


def test_severity_filter_critical_only_critical() -> None:
    findings = [
        _make_finding(id="crit-001", severity="critical", title="Critical"),
        _make_finding(id="high-001", severity="high", title="High"),
    ]
    result = classify(findings, severity_filter="critical")
    assert len(result) == 1
    assert result[0].finding.id == "crit-001"
