"""Core types and logic for the system_one_decisions helper.

This module implements every check `decide_intent` documents, but makes no
network call: there is no live TypeSafe client wired in this item (that is a
later roadmap item's job — see design.md D1 and D3). See
docs/proposals/jev-system-one-integration-assessment.md and
docs/proposals/jev-twelve-factor-decision-loops.md for the origin of this
contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Decision:
    """The outcome of one calibrated (or fallback) decision.

    `evidence_class` defaults to "judgment": a Decision is never treated as a
    deterministic fact by a caller, whether it came from a real model or from
    a fallback rule.
    """

    intent: str
    p: float
    distribution: dict[str, float] = field(default_factory=dict)
    degraded: bool = False
    evidence_class: str = "judgment"
    needs_approval: bool = False


def decide(state: dict[str, Any], questions: dict[str, Any], *, site: str) -> None:
    """Unconditional stub. Always returns None.

    There is no live client, no `TYPESAFE_API_KEY` check, and no token-budget
    check in this item (design.md D3) — those arrive with the roadmap item
    that wires the live TypeSafe client. Calling this now is always safe and
    always degrades; every caller of `decide_intent` already treats `None`
    (and every other unavailable signal) as the fallback trigger.
    """
    return


def _route(
    distribution: dict[str, float],
    intents: dict[str, str],
    *,
    human_intent: str,
    act_floor: float,
    irreversible: frozenset[str],
    approve_floor: float,
) -> Decision:
    """Pure, synchronous confidence-routing over an already-obtained distribution.

    No I/O. See design.md D1 for why this is split out from `decide_intent`.

    Rules, in order:
    1. If the top probability is below `act_floor`, route to `human_intent`.
    2. Otherwise, if the top intent is in `irreversible` and its probability
       is below `approve_floor`, return it with `needs_approval=True`.
    3. Otherwise, return the top intent unmodified.

    Boundary rule: "below" is strict (`<`), so a probability exactly equal to
    a floor meets it.
    """
    top_intent = max(distribution, key=lambda k: distribution[k])
    top_p = distribution[top_intent]

    if top_p < act_floor:
        return Decision(
            intent=human_intent,
            p=top_p,
            distribution=distribution,
            degraded=False,
        )

    needs_approval = top_intent in irreversible and top_p < approve_floor
    return Decision(
        intent=top_intent,
        p=top_p,
        distribution=distribution,
        degraded=False,
        needs_approval=needs_approval,
    )


def decide_intent(
    state: dict[str, Any],
    intents: dict[str, str],
    *,
    fallback: Callable[[dict[str, Any]], str],
    human_intent: str,
    act_floor: float = 0.6,
    irreversible: frozenset[str] = frozenset(),
    approve_floor: float = 0.9,
    site: str,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> Decision:
    """The public confidence-routed decision entry point.

    In this item, the internal acquisition step always yields "unavailable"
    — there is no live client yet (design.md D1) — so this function always
    takes the fallback branch: `fallback(state)` is called, and the result is
    wrapped as a degraded Decision. `_route`'s confidence-routing logic
    (act_floor / irreversible / approve_floor) exists and is fully
    unit-tested (see test_route.py) even though this item's `decide_intent`
    cannot yet reach it through a live call — a later roadmap item wires the
    real acquisition step and hands its distribution to this same `_route`.

    `fallback`'s own exceptions are never suppressed: this function
    introduces no new failure mode of its own.
    """
    intent = fallback(state)
    decision = Decision(
        intent=intent,
        p=1.0,
        distribution={},
        degraded=True,
        evidence_class="judgment",
    )

    if event_sink is not None:
        event_sink(
            {
                "site": site,
                "intent": decision.intent,
                "p": decision.p,
                "distribution": decision.distribution,
                "degraded": decision.degraded,
                "evidence_class": decision.evidence_class,
            }
        )

    return decision
