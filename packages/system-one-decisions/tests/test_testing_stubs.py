"""Tests for system_one_decisions.testing's reusable stub helpers.

Spec: specs/system-one-decisions/spec.md
  "system_one_decisions.testing provides reusable stubs for decide/decide_intent"

Every test here calls through `system_one_decisions.<name>` (the module
object), never via `from system_one_decisions import <name>` -- the stubs
patch the module attribute, so a name already bound by a plain `from ...
import` *before* the patch runs would keep pointing at the original
function (a general monkeypatch gotcha, not specific to this package; see
`testing.py`'s module docstring).
"""

from __future__ import annotations

import pytest

import system_one_decisions
from system_one_decisions.testing import stub_decide, stub_decide_intent


def test_stub_decide_lets_the_callers_fallback_rule_run_when_it_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """decide() is the primitive that can genuinely return None (design D1 of
    ri-02). A caller built directly on decide() -- not decide_intent() -- runs
    its own fallback when decide() is unavailable; this proves the stub lets
    that be tested without any real client or key."""
    stub_decide(monkeypatch, returns=None)

    def caller_classify(state: dict[str, object]) -> str:
        result = system_one_decisions.decide(state, {"category": "..."}, site="test-site")
        if result is None:
            return "fallback_category"
        return result["category"].choice  # type: ignore[index]

    assert caller_classify({"doc": "hi"}) == "fallback_category"


def test_stub_decide_intent_returns_the_configured_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """decide_intent() never returns None itself (it always wraps a Decision,
    even in the unavailable case -- ri-01's contract). A caller unit-testing
    its own downstream logic wants decide_intent to return a specific,
    caller-chosen Decision deterministically, without depending on
    decide_intent's real fallback machinery."""
    configured = system_one_decisions.Decision(
        intent="billing", p=0.95, distribution={"billing": 0.95}, degraded=False,
    )
    stub_decide_intent(monkeypatch, returns=configured)

    result = system_one_decisions.decide_intent(
        {"doc": "hi"},
        {"billing": "...", "technical": "..."},
        fallback=lambda _state: "human_review",
        human_intent="human_review",
        site="test-site",
    )
    assert result is configured


def test_stub_decide_default_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_decide(monkeypatch)
    assert system_one_decisions.decide({"doc": "hi"}, {}, site="test-site") is None
