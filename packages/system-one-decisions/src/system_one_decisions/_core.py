"""Core types and logic for the system_one_decisions helper.

`decide()` calls the live TypeSafe API behind an optional `live` extra
(design.md D1/D4 of `wire-the-live-typesafe-client-thresholds-and-telemetry`);
`decide_intent()`'s own acquisition step is unchanged from the prior item —
it still always takes the fallback branch (see design.md's non-goals). See
docs/proposals/jev-system-one-integration-assessment.md and
docs/proposals/jev-twelve-factor-decision-loops.md for the origin of this
contract.
"""

from __future__ import annotations

import functools
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ._config import DEFAULT_ACT_FLOOR, DEFAULT_APPROVE_FLOOR

if TYPE_CHECKING:
    import typesafe_sdk

# ~4 chars/token, the same heuristic already used by
# skills/autopilot/scripts/token_budget_check.py::_estimate_tokens.
# Reimplemented locally rather than imported cross-package, to keep this
# package dependency-free of `skills/`.
_CHARS_PER_TOKEN = 4
_TOKEN_BUDGET = 32_000


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


@functools.lru_cache(maxsize=1)
def _get_client() -> typesafe_sdk.TypeSafeClient:
    """Lazily construct and cache the one live client, reused across calls.

    Never imported or constructed at module load time (design D1/D4) — this
    is the only place `typesafe_sdk` is imported in this module, and it runs
    only once a caller has already passed the extra-not-installed and
    key-absent checks in `decide()`.
    """
    import typesafe_sdk as _typesafe_sdk

    return _typesafe_sdk.TypeSafeClient()


def _estimate_tokens(state: dict[str, Any], questions: dict[str, Any]) -> int:
    """Cheap token estimate over `state` plus the single longest serialized
    question, using the repo's ~4-chars/token heuristic (design D1)."""
    state_chars = len(json.dumps(state, default=str))
    longest_question_chars = max((len(repr(q)) for q in questions.values()), default=0)
    return (state_chars + longest_question_chars) // _CHARS_PER_TOKEN


def decide(
    state: dict[str, Any],
    questions: dict[str, Any],
    *,
    site: str,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    """Call the live TypeSafe API, or return `None` on any of four ordered
    unavailability branches (design D1) — never raises:

    1. The `live` extra isn't installed (`typesafe_sdk` import fails).
    2. `TYPESAFE_API_KEY` isn't set.
    3. The estimated token count of `state` plus the longest question
       exceeds the 32K-token budget.
    4. `client.system_one(...)` raises any `typesafe_sdk.TypeSafeError`.

    On success, returns `response.answers` unchanged (the real SDK answer
    dict — no repackaging), and invokes `event_sink` exactly once with the
    call's telemetry (design D2). `event_sink` is never invoked on any
    unavailability branch — there is nothing to report yet.
    """
    try:
        import typesafe_sdk
    except ImportError:
        return None

    if not os.environ.get("TYPESAFE_API_KEY"):
        return None

    if _estimate_tokens(state, questions) > _TOKEN_BUDGET:
        return None

    client = _get_client()
    started = time.monotonic()
    try:
        response = client.system_one(state=state, questions=questions)
    except typesafe_sdk.TypeSafeError:
        return None
    latency_ms = (time.monotonic() - started) * 1000

    if event_sink is not None:
        event_sink(
            {
                "site": site,
                "latency_ms": latency_ms,
                "usage_input_tokens": response.usage.input_tokens,
                "probabilities": {
                    key: (
                        answer.probabilities
                        if hasattr(answer, "probabilities")
                        else {"noul": answer.noul}
                    )
                    for key, answer in response.answers.items()
                },
            }
        )

    return response.answers


def _route(
    distribution: dict[str, float],
    intents: dict[str, str],
    *,
    human_intent: str,
    act_floor: float = DEFAULT_ACT_FLOOR,
    irreversible: frozenset[str],
    approve_floor: float = DEFAULT_APPROVE_FLOOR,
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
    act_floor: float = DEFAULT_ACT_FLOOR,
    irreversible: frozenset[str] = frozenset(),
    approve_floor: float = DEFAULT_APPROVE_FLOOR,
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
