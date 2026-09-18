"""Per-finding disposition routing for the review-fix convergence loop
(OpenSpec `route-review-convergence-on-per-finding-dispositions`, roadmap
item `ri-14` of `roadmap-jev-system-one-integration-assessment`).

Classifies each blocking ledger item as `fix_now`, `defer_to_followup`,
`reject_out_of_scope`, or `needs_human` instead of unconditionally
dispatching every blocking item to `fix_callback` every round. Non-`fix_now`
dispositions route through the existing `park_item(ledger, item,
reason=...)` call (see design.md D3) -- no new ledger mutation surface.

Degrades to an empty classification (every item defaults to `fix_now`,
today's behavior) whenever `system_one_decisions` is unavailable, `decide()`
returns no usable answer, or there is nothing to classify. This judgment is
load-bearing (it decides what gets dispatched), unlike the purely
observational GATEKEEPER/phase-outcome shadow judgments, so the safe
default must reproduce the pre-existing unconditional-dispatch behavior
exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

# Reuse the answer-field accessor already established by gatekeeper_shadow
# (D4-style reuse, as ri-07's phase_outcome_shadow.py also did).
from gatekeeper_shadow import _answer_field  # noqa: E402

DEFAULT_DISPOSITION = "fix_now"

_DISPOSITIONS = (
    "fix_now",
    "defer_to_followup",
    "reject_out_of_scope",
    "needs_human",
)

_DISPOSITION_CRITERIA = {
    "fix_now": (
        "Dispatch a fix this round -- likely to reduce blocking findings."
    ),
    "defer_to_followup": (
        "Real but not worth fixing this round -- park for a follow-up "
        "change."
    ),
    "reject_out_of_scope": (
        "Not actually in scope for this change -- park as out of scope."
    ),
    "needs_human": (
        "Contested or high-impact enough that a human should decide."
    ),
}

_CONTINUE_QUESTION_NAME = "continue"
_DISPOSITION_QUESTION_PREFIX = "disposition_"

# park_item's `reason=` string per disposition. `fix_now` never parks.
PARK_REASON_BY_DISPOSITION = {
    "needs_human": "disagreement",
    "defer_to_followup": "deferred_to_followup",
    "reject_out_of_scope": "out_of_scope",
}


def _disposition_question_name(item_id: int) -> str:
    return f"{_DISPOSITION_QUESTION_PREFIX}{item_id}"


def classify_round(
    blocking: list[dict[str, Any]],
    *,
    trend: list[int],
    last_fix_diff: str,
    change_id: str,
) -> dict[int, str]:
    """Classify each blocking item's disposition for this round.

    Returns a dict of ``{item_id: disposition}`` covering only the items an
    answer was actually obtained for. Callers must read it with
    ``.get(item_id, DEFAULT_DISPOSITION)`` -- a missing key (including the
    case where this function returns ``{}`` entirely) means "classify as
    fix_now", exactly today's unconditional-dispatch behavior.

    Never raises. Degrades to ``{}`` when: the helper module is
    unavailable, there are no blocking items, ``decide()`` returns no
    answers, or the round-continuation answer cannot be read.
    """
    if system_one_decisions is None or not blocking:
        return {}

    state_payload: dict[str, Any] = {
        "change_id": change_id,
        "trend": list(trend),
        "last_fix_diff": (last_fix_diff or "")[:4000],
        "blocking_items": [
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "criticality": item.get("criticality"),
                "axis": item.get("axis"),
                "file_path": item.get("file_path"),
                "first_seen_round": item.get("first_seen_round"),
                "last_seen_round": item.get("last_seen_round"),
                "resolution": item.get("resolution"),
            }
            for item in blocking
        ],
    }

    questions: dict[str, Any] = {
        _CONTINUE_QUESTION_NAME: {
            "type": "noul",
            "instructions": (
                "Is another fix round likely to reduce blocking findings?"
            ),
        },
    }
    for item in blocking:
        item_id = item.get("id")
        if item_id is None:
            continue
        questions[_disposition_question_name(int(item_id))] = {
            "type": "choice",
            "instructions": (
                "Given the ledger trend, the last fix diff, and this "
                "finding's history, what should happen to it this round?"
            ),
            "criteria": _DISPOSITION_CRITERIA,
        }

    answers = system_one_decisions.decide(
        state_payload, questions, site="autopilot.convergence_disposition"
    )
    if not answers:
        return {}

    result: dict[int, str] = {}
    for item in blocking:
        item_id = item.get("id")
        if item_id is None:
            continue
        key = _disposition_question_name(int(item_id))
        answer = answers.get(key) if hasattr(answers, "get") else None
        if answer is None:
            continue
        choice = _answer_field(answer, "choice")
        if choice in _DISPOSITIONS:
            result[int(item_id)] = choice
    return result


def replay_dispatch_counts(
    rounds_blocking: list[list[dict[str, Any]]],
) -> dict[str, int]:
    """Compare disposition-aware dispatch volume against unconditional
    dispatch, over a caller-supplied (fixture) sequence of rounds.

    Each round is a list of blocking-item dicts; an item's ``"disposition"``
    key (defaulting to ``fix_now`` when absent, mirroring
    :func:`classify_round`'s degradation contract) determines whether the
    new rule would have dispatched it. The old rule dispatches every item in
    every round unconditionally, matching `converge()`'s behavior before
    this capability existed.

    Returns ``{"old_dispatch_count", "new_dispatch_count",
    "terminal_blocking_count"}``. ``terminal_blocking_count`` is the raw
    blocking count of the final round -- disposition never changes the
    measured trend, only what gets dispatched.
    """
    old_dispatch_count = 0
    new_dispatch_count = 0
    terminal_blocking_count = 0
    for round_items in rounds_blocking:
        terminal_blocking_count = len(round_items)
        old_dispatch_count += len(round_items)
        for item in round_items:
            disposition = item.get("disposition") or DEFAULT_DISPOSITION
            if disposition == "fix_now":
                new_dispatch_count += 1
    return {
        "old_dispatch_count": old_dispatch_count,
        "new_dispatch_count": new_dispatch_count,
        "terminal_blocking_count": terminal_blocking_count,
    }
