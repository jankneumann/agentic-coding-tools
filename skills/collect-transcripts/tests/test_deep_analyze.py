"""Tests for deep analysis of flagged session transcripts.

Covers:
- TranscriptFinding schema and tag generation
- Heuristic analysis detects retry storms
- Heuristic analysis detects tool error patterns
- Heuristic analysis detects scope violations
- Heuristic analysis detects user corrections
- Dry-run report generation
- Findings only on flagged sessions (above threshold)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent
from triage import TriageScore


def _make_event(
    role: EventRole = EventRole.ASSISTANT,
    text: str = "",
    tool_name: str = "",
    tool_use_id: str = "",
    is_error: bool = False,
    seq: int = 0,
) -> NormalizedEvent:
    content = []
    if text:
        if role == EventRole.TOOL:
            content.append(
                ContentBlock(
                    type=ContentType.TOOL_RESULT,
                    text=text,
                    tool_use_id=tool_use_id,
                    is_error=is_error,
                )
            )
        else:
            content.append(ContentBlock(type=ContentType.TEXT, text=text))
    if tool_name:
        content.append(
            ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name=tool_name,
                tool_use_id=tool_use_id or f"tu-{seq}",
            )
        )
    return NormalizedEvent(
        event_id=f"evt-{seq}",
        session_id="sess-test",
        sequence_number=seq,
        role=role,
        content=content,
        harness="test",
    )


class TestTranscriptFinding:
    """Test finding schema."""

    def test_to_memory_tags(self) -> None:
        from deep_analyze import TranscriptFinding

        finding = TranscriptFinding(
            session_id="s1",
            failure_type="retry_storm",
            capability_gap="Agent retried Read 5 times",
            affected_skill="implement-feature",
            severity="high",
            source="transcript-mined",
        )
        tags = finding.to_memory_tags()
        assert "failure_type:retry_storm" in tags
        assert "capability_gap:Agent retried Read 5 times" in tags
        assert "affected_skill:implement-feature" in tags
        assert "severity:high" in tags
        assert "source:transcript-mined" in tags

    def test_round_trip(self) -> None:
        from deep_analyze import TranscriptFinding

        finding = TranscriptFinding(
            session_id="s1",
            failure_type="tool_error",
            capability_gap="Missing error handling",
            affected_skill="validate-feature",
            severity="medium",
            description="Multiple errors",
            evidence=["err1", "err2"],
        )
        d = finding.to_dict()
        restored = TranscriptFinding.from_dict(d)
        assert restored.failure_type == "tool_error"
        assert restored.capability_gap == "Missing error handling"
        assert restored.evidence == ["err1", "err2"]

    def test_source_defaults_to_transcript_mined(self) -> None:
        from deep_analyze import TranscriptFinding

        finding = TranscriptFinding()
        assert finding.source == "transcript-mined"


class TestHeuristicAnalysis:
    """Test heuristic pattern analysis."""

    def test_detects_retry_storm(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(role=EventRole.ASSISTANT, tool_name="Read", seq=i)
            for i in range(5)
        ]
        score = TriageScore(
            session_id="s1",
            retry_count=4,
            tool_error_count=0,
            scope_violation_count=0,
            user_correction_count=0,
        )
        findings = analyze_session_heuristic(events, score)
        retry_findings = [f for f in findings if f.failure_type == "retry_storm"]
        assert len(retry_findings) >= 1
        assert retry_findings[0].severity in ("medium", "high")
        assert "Read" in retry_findings[0].capability_gap

    def test_detects_tool_errors(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(
                role=EventRole.TOOL,
                text="Error: file not found",
                is_error=True,
                seq=0,
            ),
            _make_event(
                role=EventRole.TOOL,
                text="Error: permission denied",
                is_error=True,
                seq=1,
            ),
        ]
        score = TriageScore(
            session_id="s1",
            tool_error_count=2,
            retry_count=0,
            scope_violation_count=0,
            user_correction_count=0,
        )
        findings = analyze_session_heuristic(events, score)
        error_findings = [f for f in findings if f.failure_type == "tool_error"]
        assert len(error_findings) >= 1

    def test_detects_scope_violations(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(
                role=EventRole.TOOL,
                text="scope violation detected",
                seq=0,
            )
        ]
        score = TriageScore(
            session_id="s1",
            scope_violation_count=1,
            retry_count=0,
            tool_error_count=0,
            user_correction_count=0,
        )
        findings = analyze_session_heuristic(events, score)
        sv_findings = [f for f in findings if f.failure_type == "scope_violation"]
        assert len(sv_findings) >= 1

    def test_detects_user_corrections(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(role=EventRole.USER, text="No, try again", seq=0),
            _make_event(role=EventRole.USER, text="That's wrong", seq=1),
        ]
        score = TriageScore(
            session_id="s1",
            user_correction_count=2,
            retry_count=0,
            tool_error_count=0,
            scope_violation_count=0,
        )
        findings = analyze_session_heuristic(events, score)
        uc_findings = [f for f in findings if f.failure_type == "user_correction"]
        assert len(uc_findings) >= 1

    def test_no_findings_for_clean_session(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(role=EventRole.USER, text="Hi", seq=0),
            _make_event(role=EventRole.ASSISTANT, text="Hello", seq=1),
        ]
        score = TriageScore(
            session_id="s1",
            retry_count=0,
            tool_error_count=0,
            scope_violation_count=0,
            user_correction_count=0,
        )
        findings = analyze_session_heuristic(events, score)
        assert findings == []

    def test_severity_scales_with_retry_count(self) -> None:
        from deep_analyze import analyze_session_heuristic

        events = [
            _make_event(role=EventRole.ASSISTANT, tool_name="Read", seq=i)
            for i in range(6)
        ]
        # 5+ retries -> high severity
        score_high = TriageScore(session_id="s1", retry_count=5)
        findings_high = analyze_session_heuristic(events, score_high)
        retry_high = [f for f in findings_high if f.failure_type == "retry_storm"]
        assert retry_high[0].severity == "high"

        # 3-4 retries -> medium severity
        score_med = TriageScore(session_id="s1", retry_count=3)
        findings_med = analyze_session_heuristic(events[:4], score_med)
        retry_med = [f for f in findings_med if f.failure_type == "retry_storm"]
        assert retry_med[0].severity == "medium"


class TestDryRunReport:
    """Test dry-run report for deep analysis."""

    def test_report_shows_finding_count(self) -> None:
        from deep_analyze import TranscriptFinding, dry_run_findings_report

        findings = [
            TranscriptFinding(
                session_id="s1",
                failure_type="retry_storm",
                capability_gap="Retried Read 5 times",
                affected_skill="implement-feature",
                severity="high",
            ),
        ]
        report = dry_run_findings_report(findings)
        assert "Findings: 1" in report
        assert "retry_storm" in report
        assert "HIGH" in report

    def test_empty_findings_report(self) -> None:
        from deep_analyze import dry_run_findings_report

        report = dry_run_findings_report([])
        assert "Findings: 0" in report

    def test_report_includes_tags(self) -> None:
        from deep_analyze import TranscriptFinding, dry_run_findings_report

        findings = [
            TranscriptFinding(
                session_id="s1",
                failure_type="tool_error",
                capability_gap="Missing error handling",
                affected_skill="validate-feature",
                severity="medium",
                source="transcript-mined",
            ),
        ]
        report = dry_run_findings_report(findings)
        assert "source:transcript-mined" in report
        assert "failure_type:tool_error" in report
