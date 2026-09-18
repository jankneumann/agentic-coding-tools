"""Tests for the judged triage classification in triage.py.

Covers: transcript compaction (excludes tool payloads, respects the char
budget), _classify_session's degradation contract, the config-held
deep-analysis floor, sanitization before any text reaches the judgment,
and triage_session()'s judged-override wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "collect-transcripts" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

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


class TestCompactTranscript:
    """_compact_transcript excludes tool payloads and respects the budget."""

    def test_includes_user_assistant_and_tool_result_text(self) -> None:
        from triage import _compact_transcript

        events = [
            _make_user_event("Please fix the bug", seq=0),
            _make_assistant_event("Looking into it.", tool_name="Read", seq=1),
            _make_tool_result(text="file contents here", seq=2),
        ]
        text = _compact_transcript(events)
        assert "Please fix the bug" in text
        assert "Looking into it." in text
        assert "file contents here" in text

    def test_excludes_tool_use_payload(self) -> None:
        from triage import _compact_transcript

        events = [_make_assistant_event("Looking into it.", tool_name="Bash", seq=0)]
        text = _compact_transcript(events)
        assert "Bash" not in text  # tool_name never appears -- it's the payload
        assert "Looking into it." in text

    def test_truncates_to_char_budget(self) -> None:
        from triage import _compact_transcript

        events = [_make_user_event("x" * 100, seq=0)]
        text = _compact_transcript(events, max_chars=20)
        assert len(text) <= 20 + len("...(truncated)\n")
        assert "...(truncated)" in text

    def test_empty_events_yields_empty_text(self) -> None:
        from triage import _compact_transcript

        assert _compact_transcript([]) == ""


class TestClassifySession:
    """_classify_session degrades to {} on every unavailability branch."""

    def test_no_module_returns_empty(self, monkeypatch) -> None:
        import triage

        monkeypatch.setattr(triage, "system_one_decisions", None)
        result = triage._classify_session({}, "", session_id="s1")
        assert result == {}

    def test_decide_returns_none(self, monkeypatch) -> None:
        import triage
        from unittest.mock import MagicMock

        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        result = triage._classify_session({}, "", session_id="s1", dry_run=False)
        assert result == {}

    def test_available_answers_are_read(self, monkeypatch) -> None:
        import triage
        from unittest.mock import MagicMock

        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "struggle_level": {"choice": "high"},
            "deep_analysis": {"noul": 0.9},
            "user_redirected": {"noul": 0.8},
            "out_of_scope": {"noul": 0.1},
        }
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        result = triage._classify_session({}, "", session_id="s1", dry_run=False)
        assert result == {
            "struggle_level": "high",
            "flagged_for_deep_analysis": True,
            "redirected_by_user": True,
            "out_of_scope_work": False,
        }

    def test_unknown_choice_is_dropped(self, monkeypatch) -> None:
        import triage
        from unittest.mock import MagicMock

        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "struggle_level": {"choice": "catastrophic"},
        }
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        result = triage._classify_session({}, "", session_id="s1", dry_run=False)
        assert "struggle_level" not in result

    def test_dry_run_default_is_threaded_into_decide(self, monkeypatch) -> None:
        """The CLI's --dry-run default (True) must reach decide()'s own
        short-circuit -- Codex P1: this call previously bypassed it,
        breaking the documented "no API calls in dry-run" promise."""
        import triage
        from unittest.mock import MagicMock

        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        triage._classify_session({}, "", session_id="s1")  # dry_run defaults True
        assert fake_module.decide.call_args.kwargs["dry_run"] is True

    def test_dry_run_false_is_threaded_into_decide(self, monkeypatch) -> None:
        import triage
        from unittest.mock import MagicMock

        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        triage._classify_session({}, "", session_id="s1", dry_run=False)
        assert fake_module.decide.call_args.kwargs["dry_run"] is False

    def test_deep_analysis_floor_reads_from_config(self, monkeypatch, tmp_path) -> None:
        import triage
        from unittest.mock import MagicMock

        config_path = tmp_path / "triage-judgment.json"
        config_path.write_text('{"deep_analysis_floor": 0.9}')
        monkeypatch.setattr(triage, "_TRIAGE_JUDGMENT_CONFIG_PATH", config_path)

        fake_module = MagicMock()
        fake_module.decide.return_value = {"deep_analysis": {"noul": 0.7}}
        monkeypatch.setattr(triage, "system_one_decisions", fake_module)
        # 0.7 is below the configured 0.9 floor -- must NOT flag.
        result = triage._classify_session({}, "", session_id="s1", dry_run=False)
        assert result["flagged_for_deep_analysis"] is False


class TestLoadDeepAnalysisFloor:
    def test_missing_config_returns_default(self, tmp_path) -> None:
        from triage import DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR, load_deep_analysis_floor

        missing = tmp_path / "does-not-exist.json"
        assert load_deep_analysis_floor(missing) == DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR

    def test_malformed_config_returns_default(self, tmp_path) -> None:
        from triage import DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR, load_deep_analysis_floor

        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert load_deep_analysis_floor(bad) == DEFAULT_DEEP_ANALYSIS_PROBABILITY_FLOOR

    def test_valid_config_overrides_default(self, tmp_path) -> None:
        from triage import load_deep_analysis_floor

        config = tmp_path / "triage-judgment.json"
        config.write_text('{"deep_analysis_floor": 0.75}')
        assert load_deep_analysis_floor(config) == 0.75


class TestSanitizationBeforeJudgment:
    """The capability spec's 'Sanitization precedes any LLM analysis'
    requirement must hold for the new judged call (Codex P1)."""

    def test_secret_is_redacted_before_compaction(self, monkeypatch) -> None:
        import triage

        captured: dict = {}

        def _fake_classify(counters, transcript, *, session_id, dry_run=True):
            captured["transcript"] = transcript
            return {}

        monkeypatch.setattr(triage, "_classify_session", _fake_classify)
        events = [
            _make_user_event(
                "here is my key: sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGH",
                seq=0,
            ),
        ]
        triage.triage_session(events, session_id="s1")
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGH" not in captured["transcript"]


class TestTriageSessionJudgedOverride:
    """triage_session() uses the judgment when available, falling back
    otherwise (D4) -- degradation is exercised via monkeypatched
    _classify_session directly, matching D4's "unaffected below" contract."""

    def test_judged_answer_overrides_deterministic_defaults(self, monkeypatch) -> None:
        import triage

        monkeypatch.setattr(
            triage,
            "_classify_session",
            lambda counters, transcript, *, session_id, dry_run=True: {
                "struggle_level": "high",
                "flagged_for_deep_analysis": True,
                "redirected_by_user": True,
                "out_of_scope_work": False,
            },
        )
        events = [_make_user_event("Hi", seq=0)]
        score = triage.triage_session(events, session_id="s1", threshold=100.0)
        # threshold=100.0 would leave the deterministic rule unflagged --
        # the judged override must win.
        assert score.struggle_level == "high"
        assert score.flagged_for_deep_analysis is True
        assert score.redirected_by_user is True
        assert score.out_of_scope_work is False

    def test_unavailable_judgment_leaves_deterministic_behavior_unchanged(
        self, monkeypatch,
    ) -> None:
        import triage

        monkeypatch.setattr(
            triage,
            "_classify_session",
            lambda counters, transcript, *, session_id, dry_run=True: {},
        )
        events = [
            _make_assistant_event(tool_name="Read", seq=0),
            _make_tool_result(is_error=True, seq=1),
        ]
        score = triage.triage_session(events, session_id="s1", threshold=1.0)
        assert score.flagged_for_deep_analysis
        assert score.redirected_by_user is None
        assert score.out_of_scope_work is None

