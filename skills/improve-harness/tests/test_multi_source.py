"""Tests for multi-source mining and source attribution in /improve-harness.

Covers:
- analyze_failures.py reads from BOTH episodic memory AND session-log.md
  Capability Gaps Observed sections
- Dedup on (capability_gap, affected_skill, session_id) keeping multi-source list
- Report includes per-finding source attribution
- Report includes cross-source agreement summary
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_memory_entry(
    *,
    failure_type: str = "timeout",
    capability_gap: str = "slow lock acquisition",
    affected_skill: str = "implement-feature",
    severity: str = "high",
    source: str = "self-reported",
    session_id: str = "session-001",
) -> dict[str, Any]:
    return {
        "id": f"mem-{session_id}-{capability_gap[:10]}",
        "summary": f"Failure: {capability_gap}",
        "timestamp": "2026-05-01T12:00:00Z",
        "tags": [
            f"failure_type:{failure_type}",
            f"capability_gap:{capability_gap}",
            f"affected_skill:{affected_skill}",
            f"severity:{severity}",
            f"source:{source}",
        ],
        "session_id": session_id,
    }


SAMPLE_SESSION_LOG = textwrap.dedent("""\
    # Session Log

    ## Phase: Implementation

    ### Decisions
    - Used existing pattern

    ### Capability Gaps Observed
    - **timeout**: slow lock acquisition (skill: implement-feature, severity: high)
    - **scope_violation**: agent modified out-of-scope file (skill: validate-feature, severity: medium)

    ### Relevant Files
    - `src/foo.py` — updated
""")

SAMPLE_SESSION_LOG_EMPTY_GAPS = textwrap.dedent("""\
    # Session Log

    ## Phase: Review

    ### Decisions
    - Approved changes

    ### Relevant Files
    - `src/bar.py`
""")


# ---------------------------------------------------------------------------
# Tests for session-log parsing
# ---------------------------------------------------------------------------

class TestSessionLogParsing:
    """Test parsing Capability Gaps Observed sections from session-log.md files."""

    def test_extracts_gaps_from_session_log(self) -> None:
        from analyze_failures import parse_session_log_gaps

        gaps = parse_session_log_gaps(SAMPLE_SESSION_LOG, session_id="sess-abc")
        assert len(gaps) == 2
        assert gaps[0]["capability_gap"] == "slow lock acquisition"
        assert gaps[0]["failure_type"] == "timeout"
        assert gaps[0]["affected_skill"] == "implement-feature"
        assert gaps[0]["severity"] == "high"
        assert gaps[0]["session_id"] == "sess-abc"
        assert gaps[0]["source"] == "session-log"

    def test_returns_empty_for_no_gaps_section(self) -> None:
        from analyze_failures import parse_session_log_gaps

        gaps = parse_session_log_gaps(SAMPLE_SESSION_LOG_EMPTY_GAPS, session_id="s1")
        assert gaps == []

    def test_returns_empty_for_empty_content(self) -> None:
        from analyze_failures import parse_session_log_gaps

        gaps = parse_session_log_gaps("", session_id="s1")
        assert gaps == []


class TestScanSessionLogs:
    """Test scanning openspec/changes/**/session-log.md files."""

    def test_discovers_and_parses_session_log_files(self, tmp_path: Path) -> None:
        from analyze_failures import scan_session_logs

        # Create a fake openspec directory structure
        change_dir = tmp_path / "openspec" / "changes" / "test-change"
        change_dir.mkdir(parents=True)
        log_file = change_dir / "session-log.md"
        log_file.write_text(SAMPLE_SESSION_LOG)

        gaps = scan_session_logs(str(tmp_path))
        assert len(gaps) == 2
        assert gaps[0]["source"] == "session-log"

    def test_handles_missing_openspec_dir(self, tmp_path: Path) -> None:
        from analyze_failures import scan_session_logs

        gaps = scan_session_logs(str(tmp_path))
        assert gaps == []


# ---------------------------------------------------------------------------
# Tests for deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Test dedup on (capability_gap, affected_skill, session_id)."""

    def test_dedup_same_gap_different_sources(self) -> None:
        from analyze_failures import deduplicate_findings

        entries = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "timeout",
            },
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "session-log",
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        deduped = deduplicate_findings(entries)
        assert len(deduped) == 1
        assert set(deduped[0]["sources"]) == {"self-reported", "session-log"}

    def test_dedup_keeps_different_sessions(self) -> None:
        from analyze_failures import deduplicate_findings

        entries = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "timeout",
            },
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s2",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        deduped = deduplicate_findings(entries)
        assert len(deduped) == 2

    def test_dedup_keeps_different_skills(self) -> None:
        from analyze_failures import deduplicate_findings

        entries = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "timeout",
            },
            {
                "capability_gap": "slow lock",
                "affected_skill": "validate-feature",
                "session_id": "s1",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        deduped = deduplicate_findings(entries)
        assert len(deduped) == 2


# ---------------------------------------------------------------------------
# Tests for source attribution in report
# ---------------------------------------------------------------------------

class TestSourceAttribution:
    """Test that report includes per-finding source attribution."""

    def test_report_includes_source_column(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "self-reported",
                "sources": ["self-reported", "session-log"],
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        report = generate_report_multi_source(findings)
        assert "| Sources |" in report or "| Source |" in report

    def test_report_shows_multi_source_entries(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "sources": ["self-reported", "session-log"],
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        report = generate_report_multi_source(findings)
        assert "self-reported" in report
        assert "session-log" in report


class TestCrossSourceAgreement:
    """Test cross-source agreement summary line."""

    def test_agreement_summary_included(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "slow lock",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "sources": ["self-reported", "session-log"],
                "severity": "high",
                "failure_type": "timeout",
            },
            {
                "capability_gap": "missing dep",
                "affected_skill": "validate-feature",
                "session_id": "s2",
                "sources": ["self-reported"],
                "severity": "medium",
                "failure_type": "scope_violation",
            },
            {
                "capability_gap": "context too big",
                "affected_skill": "plan-feature",
                "session_id": "s3",
                "sources": ["coordinator-emitted", "transcript-mined"],
                "severity": "low",
                "failure_type": "context_exhaustion",
            },
        ]
        report = generate_report_multi_source(findings)
        # 2 out of 3 have 2+ sources = 66.7%
        assert "cross-source agreement" in report.lower() or "surfaced in 2+ sources" in report

    def test_agreement_summary_zero_when_all_single_source(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "gap-a",
                "affected_skill": "skill-a",
                "session_id": "s1",
                "sources": ["self-reported"],
                "severity": "high",
                "failure_type": "timeout",
            },
        ]
        report = generate_report_multi_source(findings)
        assert "0%" in report or "0.0%" in report
