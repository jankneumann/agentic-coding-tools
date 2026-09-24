"""Tests for convergence_disposition.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[2] / "autopilot" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import convergence_disposition as cd


def _blocking_item(item_id: int, **overrides) -> dict:
    item = {
        "id": item_id,
        "status": "open",
        "criticality": "high",
        "description": f"finding {item_id}",
        "axis": "correctness",
        "first_seen_round": 1,
        "last_seen_round": 1,
    }
    item.update(overrides)
    return item


class TestClassifyRoundUnavailable:
    def test_no_module_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setattr(cd, "system_one_decisions", None)
        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {}

    def test_no_blocking_items_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setattr(cd, "system_one_decisions", MagicMock())
        result = cd.classify_round(
            [], trend=[], last_fix_diff="", change_id="c",
        )
        assert result == {}

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)
        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {}


class TestClassifyRoundAvailable:
    def test_one_decide_call_for_the_whole_round(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {"choice": "fix_now", "confidence": 0.9},
            "disposition_2": {"choice": "needs_human", "confidence": 0.9},
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1), _blocking_item(2)],
            trend=[2],
            last_fix_diff="diff text",
            change_id="c",
        )

        assert fake_module.decide.call_count == 1
        _state, questions = fake_module.decide.call_args[0]
        assert set(questions) == {"continue", "disposition_1", "disposition_2"}
        assert questions["continue"]["type"] == "noul"
        assert questions["disposition_1"]["type"] == "choice"
        assert result == {1: "fix_now", 2: "needs_human"}

    def test_unknown_choice_value_is_dropped(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {"choice": "not_a_real_disposition", "confidence": 0.9},
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {}

    def test_missing_answer_for_an_item_is_dropped(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {"choice": "reject_out_of_scope", "confidence": 0.9},
            # no "disposition_2" key at all
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1), _blocking_item(2)],
            trend=[2],
            last_fix_diff="",
            change_id="c",
        )
        assert result == {1: "reject_out_of_scope"}


class TestConfidenceFloor:
    """A low-confidence disposition answer must never park a real blocker
    (Codex P1): the item is left out of the result, so the caller's
    DEFAULT_DISPOSITION fallback (fix_now) applies instead."""

    def test_low_probability_choice_is_not_acted_on(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {
                "choice": "reject_out_of_scope",
                "probabilities": {
                    "fix_now": 0.3,
                    "defer_to_followup": 0.25,
                    "reject_out_of_scope": 0.26,
                    "needs_human": 0.19,
                },
            },
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {}

    def test_high_probability_choice_is_acted_on(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {
                "choice": "needs_human",
                "probabilities": {
                    "fix_now": 0.05,
                    "defer_to_followup": 0.05,
                    "reject_out_of_scope": 0.05,
                    "needs_human": 0.85,
                },
            },
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {1: "needs_human"}

    def test_missing_confidence_signal_is_not_acted_on(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "continue": {"noul": 0.8},
            "disposition_1": {"choice": "needs_human"},
        }
        monkeypatch.setattr(cd, "system_one_decisions", fake_module)

        result = cd.classify_round(
            [_blocking_item(1)], trend=[1], last_fix_diff="", change_id="c",
        )
        assert result == {}


class TestParkReasonMapping:
    def test_every_non_fix_now_disposition_has_a_reason(self) -> None:
        for disposition in ("defer_to_followup", "reject_out_of_scope", "needs_human"):
            assert disposition in cd.PARK_REASON_BY_DISPOSITION
        assert "fix_now" not in cd.PARK_REASON_BY_DISPOSITION


class TestReplayDispatchCounts:
    def test_fewer_dispatches_for_same_terminal_blocking_count(self) -> None:
        # A finding that keeps getting rejected stays "blocking" (raw trend
        # is unaffected by disposition) across three rounds, alongside one
        # finding fixed each round.
        rounds = [
            [
                {"id": 1, "disposition": "fix_now"},
                {"id": 2, "disposition": "reject_out_of_scope"},
            ],
            [
                {"id": 3, "disposition": "fix_now"},
                {"id": 2, "disposition": "reject_out_of_scope"},
            ],
            [
                {"id": 2, "disposition": "reject_out_of_scope"},
            ],
        ]

        replay = cd.replay_dispatch_counts(rounds)

        assert replay["terminal_blocking_count"] == 1
        assert replay["old_dispatch_count"] == 5
        assert replay["new_dispatch_count"] == 2
        assert replay["new_dispatch_count"] < replay["old_dispatch_count"]

    def test_missing_disposition_defaults_to_fix_now(self) -> None:
        rounds = [[{"id": 1}]]
        replay = cd.replay_dispatch_counts(rounds)
        assert replay["old_dispatch_count"] == 1
        assert replay["new_dispatch_count"] == 1

    def test_empty_rounds(self) -> None:
        replay = cd.replay_dispatch_counts([])
        assert replay == {
            "old_dispatch_count": 0,
            "new_dispatch_count": 0,
            "terminal_blocking_count": 0,
        }
