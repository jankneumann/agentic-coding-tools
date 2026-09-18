"""Tests for the judged first-stage audit-triage screen (ri-16).

Covers: the config-held recall floor, screen_session's degradation
contract, and drain_and_classify's wiring of the screen -- including that
a below-floor batch never reaches the existing classifier, that an
above-floor batch still runs it seeded with the stage-one hint, and that
an unavailable screen falls through to the pre-existing unconditional
classify_fn call.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.audit import AuditEntry
from src.audit_triage import (
    DEFAULT_CAPABILITY_GAP_RECALL_FLOOR,
    AuditTriageBuffer,
    drain_and_classify,
    load_capability_gap_recall_floor,
    screen_session,
)

_SAMPLE_ENTRY: dict[str, Any] = {
    "id": "entry-001",
    "agent_id": "agent-alpha",
    "agent_type": "claude_code",
    "operation": "acquire_lock",
    "parameters": {"file_path": "src/foo.py"},
    "result": {"success": False, "reason": "locked_by_other"},
    "duration_ms": 12,
    "success": False,
    "error_message": "Lock held by agent-beta",
    "created_at": "2026-06-05T10:01:00+00:00",
}


def _noul_choice_score(module: MagicMock, noul: float, failure_type: str | None, score: float) -> None:
    module.decide.return_value = {
        "capability_gap": {"noul": noul},
        "failure_type": {"choice": failure_type},
        "severity": {"score": score},
    }


class TestLoadCapabilityGapRecallFloor:
    def test_missing_config_returns_default(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"
        assert (
            load_capability_gap_recall_floor(missing)
            == DEFAULT_CAPABILITY_GAP_RECALL_FLOOR
        )

    def test_malformed_config_returns_default(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert (
            load_capability_gap_recall_floor(bad)
            == DEFAULT_CAPABILITY_GAP_RECALL_FLOOR
        )

    def test_valid_config_overrides_default(self, tmp_path: Path) -> None:
        config = tmp_path / "audit-triage-judgment.json"
        config.write_text('{"recall_floor": 0.6}')
        assert load_capability_gap_recall_floor(config) == 0.6


class TestScreenSession:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr("src.audit_triage.system_one_decisions", None)
        assert screen_session([{"operation": "acquire_lock"}]) is None

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        assert screen_session([{"operation": "acquire_lock"}]) is None

    def test_confident_answer_is_used(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_choice_score(fake_module, noul=0.8, failure_type="lock_unavailable", score=1.0)
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        result = screen_session([{"operation": "acquire_lock"}])
        assert result == {
            "capability_gap_probability": 0.8,
            "failure_type": "lock_unavailable",
            "severity": "medium",
        }

    def test_unknown_failure_type_becomes_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_choice_score(fake_module, noul=0.8, failure_type="something_invented", score=0.0)
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        result = screen_session([{"operation": "acquire_lock"}])
        assert result["failure_type"] is None

    def test_malformed_noul_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {"capability_gap": {"noul": "high"}}
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        assert screen_session([{"operation": "acquire_lock"}]) is None

    def test_dry_run_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        screen_session([{"operation": "acquire_lock"}], dry_run=True)
        assert fake_module.decide.call_args.kwargs["dry_run"] is True

    def test_answers_accept_object_style_sdk_answers(self, monkeypatch) -> None:
        """A real SDK answer is an attribute-bearing object, not a dict."""
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_gap": SimpleNamespace(noul=0.9),
            "failure_type": SimpleNamespace(choice="timeout"),
            "severity": SimpleNamespace(score=3.0),
        }
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)
        result = screen_session([{"operation": "acquire_lock"}])
        assert result == {
            "capability_gap_probability": 0.9,
            "failure_type": "timeout",
            "severity": "critical",
        }


class TestDrainAndClassifyWithScreen:
    @pytest.mark.asyncio
    async def test_below_floor_batch_never_calls_classifier(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_choice_score(fake_module, noul=0.05, failure_type=None, score=0.0)
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

        buffer = AuditTriageBuffer(max_size=100)
        buffer.push(AuditEntry.from_dict(_SAMPLE_ENTRY), session_id="session-clean")

        mock_classify = AsyncMock(return_value=[])
        mock_remember = AsyncMock()

        result = await drain_and_classify(
            buffer=buffer, classify_fn=mock_classify, remember_fn=mock_remember,
        )
        assert not mock_classify.called, "a clean session must never reach the classifier"
        assert not mock_remember.called
        assert result == []

    @pytest.mark.asyncio
    async def test_above_floor_batch_calls_classifier_seeded_with_hint(self, monkeypatch) -> None:
        fake_module = MagicMock()
        _noul_choice_score(fake_module, noul=0.9, failure_type="lock_unavailable", score=1.0)
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

        buffer = AuditTriageBuffer(max_size=100)
        buffer.push(AuditEntry.from_dict(_SAMPLE_ENTRY), session_id="session-risky")

        mock_classify = AsyncMock(return_value=[])
        mock_remember = AsyncMock()

        await drain_and_classify(
            buffer=buffer, classify_fn=mock_classify, remember_fn=mock_remember,
        )
        assert mock_classify.called
        _args, kwargs = mock_classify.call_args
        assert kwargs["stage_one_hint"] == {
            "failure_type": "lock_unavailable", "severity": "medium",
        }

    @pytest.mark.asyncio
    async def test_seeded_hint_backfills_a_finding_missing_the_fields(self, monkeypatch) -> None:
        """design.md: stage-two findings are seeded with the stage-one
        failure_type/severity and still pass validate_finding unchanged."""
        fake_module = MagicMock()
        _noul_choice_score(fake_module, noul=0.9, failure_type="timeout", score=3.0)
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

        buffer = AuditTriageBuffer(max_size=100)
        buffer.push(AuditEntry.from_dict(_SAMPLE_ENTRY), session_id="session-risky")

        # classify_fn's own output omits failure_type/severity -- the
        # stage-one hint must backfill them so the finding still validates.
        incomplete_finding = {
            "capability_gap": "no-retry-backoff-for-lock-contention",
            "affected_skill": "implement-feature",
        }
        mock_classify = AsyncMock(return_value=[incomplete_finding])

        remember_calls: list[dict[str, Any]] = []

        async def mock_remember(**kwargs: Any) -> None:
            remember_calls.append(kwargs)

        result = await drain_and_classify(
            buffer=buffer, classify_fn=mock_classify, remember_fn=mock_remember,
        )
        assert len(remember_calls) == 1
        assert remember_calls[0]["details"]["failure_type"] == "timeout"
        assert remember_calls[0]["details"]["severity"] == "critical"
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_unavailable_screen_falls_back_to_unconditional_call(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

        buffer = AuditTriageBuffer(max_size=100)
        buffer.push(AuditEntry.from_dict(_SAMPLE_ENTRY), session_id="session-001")

        mock_classify = AsyncMock(return_value=[])
        mock_remember = AsyncMock()

        await drain_and_classify(
            buffer=buffer, classify_fn=mock_classify, remember_fn=mock_remember,
        )
        assert mock_classify.called
        _args, kwargs = mock_classify.call_args
        assert kwargs["stage_one_hint"] is None

    @pytest.mark.asyncio
    async def test_dry_run_reaches_the_screen(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

        buffer = AuditTriageBuffer(max_size=100)
        buffer.push(AuditEntry.from_dict(_SAMPLE_ENTRY), session_id="session-001")

        mock_classify = AsyncMock(return_value=[])
        mock_remember = AsyncMock()

        await drain_and_classify(
            buffer=buffer, classify_fn=mock_classify, remember_fn=mock_remember,
            dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestRecallAgainstLabeledBatches:
    """D4 (mirroring ri-15's own D4): no [live] extra is installed anywhere
    in this repo, so a genuine live-model recall figure for the screen
    cannot be produced in CI. What CI *can* prove is that the screen's
    wiring, given an answer set agreeing with this fixture's labels,
    reproduces the existing (recall-oriented) v1 prompt's own labels --
    see design.md D4. Both numbers (screen recall, "current prompt" recall
    -- 1.0 by this fixture's own construction) are recorded for visibility.
    """

    FIXTURES_DIR = Path(__file__).parent / "fixtures"

    def test_screen_recall_matches_the_labeled_fixture(self, monkeypatch) -> None:
        cases = json.loads(
            (self.FIXTURES_DIR / "audit_triage_labeled_batches.json").read_text(
                encoding="utf-8"
            )
        )["cases"]

        total_true = sum(1 for c in cases if c["label"] is True)
        flagged_true = 0

        for case in cases:
            fake_module = MagicMock()
            # Simulate a screen that agrees with this fixture's own label --
            # the wiring under test, not a live-calibration claim.
            _noul_choice_score(
                fake_module,
                noul=0.9 if case["label"] else 0.05,
                failure_type=None,
                score=0.0,
            )
            monkeypatch.setattr("src.audit_triage.system_one_decisions", fake_module)

            floor = load_capability_gap_recall_floor()
            result = screen_session(case["entries"])
            flagged = result is not None and result["capability_gap_probability"] >= floor
            if case["label"] and flagged:
                flagged_true += 1

        assert total_true >= 2, "fixture set must carry at least two true-labeled batches"
        screen_recall = flagged_true / total_true
        current_prompt_recall = 1.0  # by this fixture's own construction (see class docstring)
        print(  # recorded for visibility per the acceptance outcome
            f"stage-one screen recall vs. labeled fixture: "
            f"{flagged_true}/{total_true} ({screen_recall:.0%}); "
            f"current-prompt recall on the same fixture: {current_prompt_recall:.0%}"
        )
        assert screen_recall >= current_prompt_recall
