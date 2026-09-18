"""Tests for the pure, private confidence-routing helper.

Spec: specs/system-one-decisions/spec.md
  "_route() implements confidence-based routing over a distribution"
Design: design.md D1.
"""

from __future__ import annotations

from system_one_decisions._core import _route


def test_below_act_floor_routes_to_human_intent() -> None:
    d = _route(
        distribution={"a": 0.4, "b": 0.3, "c": 0.3},
        intents={"a": "...", "b": "...", "c": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset(),
        approve_floor=0.9,
    )
    assert d.intent == "ask_human"
    assert d.degraded is False


def test_at_or_above_act_floor_and_not_irreversible_returns_top_intent() -> None:
    d = _route(
        distribution={"a": 0.8, "b": 0.2},
        intents={"a": "...", "b": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset(),
        approve_floor=0.9,
    )
    assert d.intent == "a"


def test_irreversible_below_approve_floor_is_flagged() -> None:
    d = _route(
        distribution={"delete": 0.75, "keep": 0.25},
        intents={"delete": "...", "keep": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset({"delete"}),
        approve_floor=0.9,
    )
    assert d.intent == "delete"
    assert d.needs_approval is True


def test_irreversible_at_or_above_approve_floor_is_not_flagged() -> None:
    d = _route(
        distribution={"delete": 0.95, "keep": 0.05},
        intents={"delete": "...", "keep": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset({"delete"}),
        approve_floor=0.9,
    )
    assert d.intent == "delete"
    assert d.needs_approval is False


def test_boundary_probability_equal_to_act_floor_meets_it() -> None:
    d = _route(
        distribution={"a": 0.6, "b": 0.4},
        intents={"a": "...", "b": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset(),
        approve_floor=0.9,
    )
    assert d.intent == "a"


def test_boundary_probability_equal_to_approve_floor_is_not_flagged() -> None:
    d = _route(
        distribution={"delete": 0.9, "keep": 0.1},
        intents={"delete": "...", "keep": "..."},
        human_intent="ask_human",
        act_floor=0.6,
        irreversible=frozenset({"delete"}),
        approve_floor=0.9,
    )
    assert d.needs_approval is False
