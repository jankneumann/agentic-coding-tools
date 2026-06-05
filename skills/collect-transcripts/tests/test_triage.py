"""Tests for triage pass on session transcripts.

Covers:
- Signal extraction: retry_count, tool_error_count, scope_violation_count,
  user_correction_count
- Struggle classification: none/low/medium/high
- Composite score calculation
- Flagging for deep analysis based on threshold
- Dry-run report generation
- Multi-session triage
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from normalize import ContentBlock, ContentType, EventRole, NormalizedEvent


def _make_user_event(text: str = "Do something", seq: int = 0) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"u-{seq}",
        session_id="sess-001",
        sequence_number=seq,
        role=EventRole.USER,
        content=[ContentBlock(type=ContentType.TEXT, text=text)],
        harness="test",
    )


def _make_assistant_event(
    text: str = "Done.",
    tool_name: str = "",
    seq: int = 0,
) -> NormalizedEvent:
    content = [ContentBlock(type=ContentType.TEXT, text=text)]
    if tool_name:
        content.append(
            ContentBlock(
                type=ContentType.TOOL_USE,
                tool_name=tool_name,
                tool_use_id=f"tu-{seq}",
            )
        )
    return NormalizedEvent(
        event_id=f"a-{seq}",
        session_id="sess-001",
        sequence_number=seq,
        role=EventRole.ASSISTANT,
        content=content,
        harness="test",
    )


def _make_tool_result(
    text: str = "OK",
    is_error: bool = False,
    seq: int = 0,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"t-{seq}",
        session_id="sess-001",
        sequence_number=seq,
        role=EventRole.TOOL,
        content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=text,
                tool_use_id=f"tu-{seq}",
                is_error=is_error,
            )
        ],
        harness="test",
    )


class TestRetryCount:
    """Test retry detection (consecutive same tool calls)."""

    def test_no_retries_with_different_tools(self) -> None:
        from triage import _count_retries

        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_assistant_event(tool_name="Edit", seq=1),
            _make_assistant_event(tool_name="Bash", seq=2),
        ]
        assert _count_retries(events) == 0

    def test_counts_consecutive_same_tool(self) -> None:
        from triage import _count_retries

        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_assistant_event(tool_name="Read", seq=1),
            _make_assistant_event(tool_name="Read", seq=2),
        ]
        assert _count_retries(events) == 2

    def test_resets_on_different_tool(self) -> None:
        from triage import _count_retries

        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_assistant_event(tool_name="Read", seq=1),
            _make_assistant_event(tool_name="Edit", seq=2),
            _make_assistant_event(tool_name="Read", seq=3),
        ]
        assert _count_retries(events) == 1


class TestToolErrorCount:
    """Test tool error counting."""

    def test_no_errors(self) -> None:
        from triage import _count_tool_errors

        events = [_make_tool_result(is_error=False)]
        assert _count_tool_errors(events) == 0

    def test_counts_errors(self) -> None:
        from triage import _count_tool_errors

        events = [
            _make_tool_result(is_error=True, seq=0),
            _make_tool_result(is_error=False, seq=1),
            _make_tool_result(is_error=True, seq=2),
        ]
        assert _count_tool_errors(events) == 2


class TestScopeViolationCount:
    """Test scope violation heuristic."""

    def test_detects_scope_violation_keywords(self) -> None:
        from triage import _count_scope_violations

        events = [
            _make_tool_result(
                text="Error: permission denied for /etc/passwd", seq=0
            ),
            _make_tool_result(
                text="Warning: out of scope file access", seq=1
            ),
        ]
        assert _count_scope_violations(events) == 2

    def test_no_violations_in_clean_text(self) -> None:
        from triage import _count_scope_violations

        events = [
            _make_tool_result(text="File read successfully", seq=0),
        ]
        assert _count_scope_violations(events) == 0


class TestUserCorrectionCount:
    """Test user correction detection."""

    def test_counts_user_after_error(self) -> None:
        from triage import _count_user_corrections

        events = [
            _make_tool_result(is_error=True, seq=0),
            _make_user_event("No, that's wrong", seq=1),
        ]
        assert _count_user_corrections(events) == 1

    def test_no_correction_without_error(self) -> None:
        from triage import _count_user_corrections

        events = [
            _make_tool_result(is_error=False, seq=0),
            _make_user_event("Good job", seq=1),
        ]
        assert _count_user_corrections(events) == 0

    def test_resets_after_assistant_reply(self) -> None:
        from triage import _count_user_corrections

        events = [
            _make_tool_result(is_error=True, seq=0),
            _make_assistant_event("Let me try again", seq=1),
            _make_user_event("Here is more context", seq=2),
        ]
        assert _count_user_corrections(events) == 0


class TestStruggleClassification:
    """Test composite score and struggle level."""

    def test_no_struggle(self) -> None:
        from triage import _classify_struggle

        level, score = _classify_struggle(0, 0, 0, 0)
        assert level == "none"
        assert score == 0.0

    def test_low_struggle(self) -> None:
        from triage import _classify_struggle

        level, score = _classify_struggle(1, 0, 0, 0)
        assert level == "low"
        assert score == 1.0

    def test_medium_struggle(self) -> None:
        from triage import _classify_struggle

        level, score = _classify_struggle(1, 2, 0, 0)
        assert level == "medium"
        assert score == 5.0

    def test_high_struggle(self) -> None:
        from triage import _classify_struggle

        level, score = _classify_struggle(2, 2, 1, 1)
        assert level == "high"
        # 2*1 + 2*2 + 1*3 + 1*2.5 = 2 + 4 + 3 + 2.5 = 11.5
        assert score == 11.5


class TestTriageSession:
    """Test full session triage."""

    def test_clean_session(self) -> None:
        from triage import triage_session

        events = [
            _make_user_event("Do something", seq=0),
            _make_assistant_event("Done.", seq=1),
        ]
        score = triage_session(events, session_id="s1")
        assert score.struggle_level == "none"
        assert not score.flagged_for_deep_analysis

    def test_struggling_session(self) -> None:
        from triage import triage_session

        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_tool_result(is_error=True, seq=1),
            _make_assistant_event(tool_name="Read", seq=2),
            _make_tool_result(is_error=True, seq=3),
            _make_assistant_event(tool_name="Read", seq=4),
            _make_tool_result(
                text="Error: permission denied", is_error=True, seq=5
            ),
            _make_user_event("Try a different approach", seq=6),
        ]
        score = triage_session(events, session_id="s1", threshold=5.0)
        assert score.tool_error_count == 3
        assert score.retry_count == 2
        assert score.flagged_for_deep_analysis

    def test_empty_session(self) -> None:
        from triage import triage_session

        score = triage_session([], session_id="empty")
        assert score.struggle_level == "none"
        assert score.event_count == 0

    def test_threshold_controls_flagging(self) -> None:
        from triage import triage_session

        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_tool_result(is_error=True, seq=1),
        ]
        # Low threshold -> flagged
        score_low = triage_session(events, session_id="s1", threshold=1.0)
        assert score_low.flagged_for_deep_analysis

        # High threshold -> not flagged
        score_high = triage_session(events, session_id="s1", threshold=100.0)
        assert not score_high.flagged_for_deep_analysis


class TestTriageSessions:
    """Test multi-session triage."""

    def test_scores_multiple_sessions(self) -> None:
        from triage import triage_sessions

        sessions = {
            "s1": [_make_user_event("Hi", seq=0)],
            "s2": [
                _make_assistant_event(tool_name="Read", seq=0),
                _make_tool_result(is_error=True, seq=1),
            ],
        }
        scores = triage_sessions(sessions, threshold=1.0)
        assert len(scores) == 2


class TestDryRunReport:
    """Test dry-run report generation."""

    def test_report_shows_session_count(self) -> None:
        from triage import TriageScore, dry_run_report

        scores = [
            TriageScore(session_id="s1", harness="test", event_count=10,
                        composite_score=3.0, struggle_level="low"),
            TriageScore(session_id="s2", harness="test", event_count=20,
                        composite_score=8.0, struggle_level="high",
                        flagged_for_deep_analysis=True),
        ]
        report = dry_run_report(scores)
        assert "Sessions analyzed: 2" in report
        assert "Sessions flagged for deep analysis: 1" in report

    def test_report_mentions_no_api_calls(self) -> None:
        from triage import TriageScore, dry_run_report

        scores = [
            TriageScore(session_id="s1", composite_score=0.0, struggle_level="none"),
        ]
        report = dry_run_report(scores)
        assert "no API calls" in report.lower() or "dry-run" in report.lower()

    def test_empty_scores_report(self) -> None:
        from triage import dry_run_report

        report = dry_run_report([])
        assert "Sessions analyzed: 0" in report
