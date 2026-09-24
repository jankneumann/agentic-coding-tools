"""Tests for decide_intent()'s always-fallback behavior in this item.

Spec: specs/system-one-decisions/spec.md
  "decide_intent() always takes the fallback branch in this item"
  "decide_intent records one event through a caller-supplied sink"
Design: design.md D1, D2.
"""

from __future__ import annotations

import pytest
from system_one_decisions import decide_intent


def test_decide_intent_falls_back_with_degraded_true() -> None:
    d = decide_intent(
        state={"anything": "goes"},
        intents={"a": "...", "b": "..."},
        fallback=lambda state: "my_default_intent",
        human_intent="ask_human",
        site="test-site",
    )
    assert d.intent == "my_default_intent"
    assert d.degraded is True
    assert d.evidence_class == "judgment"


def test_decide_intent_never_raises_beyond_the_fallbacks_own_exception() -> None:
    class MyError(RuntimeError):
        pass

    def raising_fallback(state: dict) -> str:
        raise MyError("caller's own bug")

    with pytest.raises(MyError, match="caller's own bug"):
        decide_intent(
            state={},
            intents={},
            fallback=raising_fallback,
            human_intent="ask_human",
            site="test-site",
        )


def test_event_sink_receives_exactly_one_matching_call() -> None:
    # A synthetic list shaped like loop-state.json's phase_history array —
    # proving the event dict is appendable there without importing autopilot.
    phase_history: list[dict] = []

    d = decide_intent(
        state={"k": "v"},
        intents={"a": "..."},
        fallback=lambda state: "fallback_intent",
        human_intent="ask_human",
        site="phase-outcome-adjudication",
        event_sink=phase_history.append,
    )

    assert len(phase_history) == 1
    event = phase_history[0]
    assert event["intent"] == d.intent
    assert event["degraded"] == d.degraded
    assert event["evidence_class"] == d.evidence_class
    assert event["site"] == "phase-outcome-adjudication"


def test_omitting_event_sink_is_safe() -> None:
    d = decide_intent(
        state={},
        intents={},
        fallback=lambda state: "x",
        human_intent="ask_human",
        site="test-site",
    )
    assert d.intent == "x"
