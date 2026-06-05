"""Test that /improve-harness surfaces transcript-sourced findings.

Verifies end-to-end: transcript-mined findings flow through the
multi-source pipeline unchanged — they appear in reports with
``source:transcript-mined`` in their source set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Path setup for both improve-harness and collect-transcripts scripts
IMPROVE_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
COLLECT_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent
    / "collect-transcripts"
    / "scripts"
)
sys.path.insert(0, str(IMPROVE_SCRIPTS))
sys.path.insert(0, str(COLLECT_SCRIPTS))


def _make_transcript_mined_memory_entry(
    *,
    capability_gap: str = "Agent retried Read 5 times",
    failure_type: str = "retry_storm",
    affected_skill: str = "implement-feature",
    severity: str = "high",
    session_id: str = "session-transcript-001",
) -> dict[str, Any]:
    """Create a memory entry that would have been written by deep_analyze."""
    return {
        "id": f"mem-{session_id}-transcript",
        "summary": f"Transcript finding: {capability_gap}",
        "timestamp": "2026-05-01T12:00:00Z",
        "tags": [
            f"failure_type:{failure_type}",
            f"capability_gap:{capability_gap}",
            f"affected_skill:{affected_skill}",
            f"severity:{severity}",
            "source:transcript-mined",
        ],
        "session_id": session_id,
    }


class TestTranscriptFindingsInReport:
    """Test that transcript-mined findings appear in /improve-harness reports."""

    def test_transcript_mined_entry_appears_in_ranked_findings(self) -> None:
        from analyze_failures import rank_findings

        entries = [
            _make_transcript_mined_memory_entry(
                capability_gap="retry storm on Read",
            ),
            _make_transcript_mined_memory_entry(
                capability_gap="retry storm on Read",
                session_id="session-002",
            ),
        ]
        ranked = rank_findings(entries)
        assert len(ranked) >= 1
        # Check that transcript-mined source is captured
        assert "transcript-mined" in ranked[0]["sources"]

    def test_transcript_mined_entry_in_multi_source_report(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "retry storm on Read",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "sources": ["transcript-mined"],
                "severity": "high",
                "failure_type": "retry_storm",
            },
            {
                "capability_gap": "retry storm on Read",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "sources": ["self-reported"],
                "severity": "high",
                "failure_type": "retry_storm",
            },
        ]
        report = generate_report_multi_source(findings)
        assert "transcript-mined" in report

    def test_transcript_mined_dedupes_with_other_sources(self) -> None:
        from analyze_failures import deduplicate_findings

        findings = [
            {
                "capability_gap": "retry storm on Read",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "transcript-mined",
                "severity": "high",
                "failure_type": "retry_storm",
            },
            {
                "capability_gap": "retry storm on Read",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "source": "self-reported",
                "severity": "high",
                "failure_type": "retry_storm",
            },
        ]
        deduped = deduplicate_findings(findings)
        assert len(deduped) == 1
        assert "transcript-mined" in deduped[0]["sources"]
        assert "self-reported" in deduped[0]["sources"]

    def test_cross_source_agreement_includes_transcript_mined(self) -> None:
        from generate_report import generate_report_multi_source

        findings = [
            {
                "capability_gap": "retry storm on Read",
                "affected_skill": "implement-feature",
                "session_id": "s1",
                "sources": ["transcript-mined", "self-reported"],
                "severity": "high",
                "failure_type": "retry_storm",
            },
        ]
        report = generate_report_multi_source(findings)
        assert "100.0%" in report or "surfaced in 2+ sources" in report

    def test_findings_from_deep_analyze_match_report_schema(self) -> None:
        """Verify deep_analyze TranscriptFinding tags are compatible
        with analyze_failures tag extraction."""
        from deep_analyze import TranscriptFinding
        from analyze_failures import _extract_tag

        finding = TranscriptFinding(
            session_id="s1",
            failure_type="retry_storm",
            capability_gap="Agent retried Read 5 times",
            affected_skill="implement-feature",
            severity="high",
            source="transcript-mined",
        )
        tags = finding.to_memory_tags()

        # Verify tags are extractable by analyze_failures helpers
        assert _extract_tag(tags, "failure_type") == "retry_storm"
        assert _extract_tag(tags, "capability_gap") == "Agent retried Read 5 times"
        assert _extract_tag(tags, "affected_skill") == "implement-feature"
        assert _extract_tag(tags, "severity") == "high"
        assert _extract_tag(tags, "source") == "transcript-mined"
