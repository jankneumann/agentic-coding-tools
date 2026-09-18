"""Phase-outcome shadow adjudication (OpenSpec
`adjudicate-phase-outcomes-in-shadow-mode`, roadmap item `ri-07` of
`roadmap-jev-system-one-integration-assessment`).

Applies the shadow-recording architecture `ri-06` established for
GATEKEEPER to every other phase transition: a second, calibrated judgment
of whether the evidence supports a phase sub-agent's claimed outcome, run
alongside (never instead of) the claimed outcome `apply_phase_outcome`
already records. See design.md's D1 for why this lives inside
`apply_phase_outcome` itself, on the real production path, from the start
-- the exact lesson `ri-06` learned by review rather than by design.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

# Reuse ri-06's shared shadow-record envelope and answer-snapshot helpers
# (design D4) rather than duplicating their shape.
from gatekeeper_shadow import (  # noqa: E402
    _answer_field,
    _choice_snapshot,
    _shadow_entry_dict,
)

_SHADOW_PHASE = "PHASE_OUTCOME_SHADOW"


def git_diff_stat(worktree_path: Path) -> str | None:
    """`git diff --stat` of *worktree_path* against its upstream merge base.

    Best-effort (design D3): a missing worktree, a `git` failure, or a
    timeout all degrade to `None` -- never raises.
    """
    if not worktree_path.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "main...HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    stat = result.stdout.strip()
    return stat or None


def test_output_tail(change_dir: Path, *, lines: int = 40) -> str | None:
    """The last *lines* lines of `validation-report.md`, when present.

    The only test-output artifact already established by convention in
    this codebase (design D3) -- no other file is invented for this.
    """
    report_path = change_dir / "validation-report.md"
    if not report_path.is_file():
        return None
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return None
    tail_lines = text.splitlines()[-lines:]
    tail = "\n".join(tail_lines).strip()
    return tail or None


def read_local_handoff(
    change_dir: Path, phase: str, handoff_id: str | None
) -> dict[str, Any] | None:
    """The most recent local-fallback handoff file for *phase*, if any.

    The coordinator has no read-by-`handoff_id` lookup (design grounding),
    so this reads `handoffs/<phase-slug>-<n>.json` -- written only when the
    sub-agent's own coordinator write failed. `handoff_id` is accepted for
    a future exact match but not required today; absence of a match (no
    handoffs directory, no file for this phase's slug, or a parse failure)
    degrades to `None`.
    """
    handoffs_dir = change_dir / "handoffs"
    if not handoffs_dir.is_dir():
        return None
    phase_slug = phase.lower().replace(" ", "-").replace("_", "-")
    candidates = sorted(handoffs_dir.glob(f"{phase_slug}-*.json"))
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_outcome_adjudication_entry(
    *,
    phase: str,
    claimed_outcome: str,
    expected_outcomes: list[str],
    handoff_record: dict[str, Any] | None,
    diff_stat: str | None,
    test_output_tail: str | None,
) -> dict[str, Any] | None:
    """The phase-outcome shadow adjudication step (design D1). Pure -- no
    `LoopState` dependency, so both a Python-level caller and the real
    `apply_phase_outcome` production path can call it identically.

    Returns `None` (appends nothing) when `system_one_decisions` is
    unavailable, every signal is `None` (nothing to adjudicate), `decide()`
    returns `None`, or the returned answer set is malformed. Never raises;
    never influences `claimed_outcome` or `transition()`.
    """
    if system_one_decisions is None:
        return None
    if not expected_outcomes and handoff_record is None and diff_stat is None and test_output_tail is None:
        return None

    state_payload: dict[str, Any] = {
        "phase": phase,
        "claimed_outcome": claimed_outcome,
        "expected_outcomes": list(expected_outcomes),
    }
    if handoff_record is not None:
        state_payload["handoff_record"] = handoff_record
    if diff_stat is not None:
        state_payload["worktree_diff_stat"] = diff_stat
    if test_output_tail is not None:
        state_payload["test_output_tail"] = test_output_tail

    outcome_criteria = {o: o for o in expected_outcomes} or {claimed_outcome: claimed_outcome}
    questions = {
        "outcome": {
            "type": "choice",
            "instructions": (
                "Which of this phase's allowed outcomes does the evidence "
                "actually support?"
            ),
            "criteria": outcome_criteria,
        },
        "evidence_supports_outcome": {
            "type": "noul",
            "instructions": (
                f"The evidence supports the claimed outcome {claimed_outcome!r}."
            ),
        },
    }

    answers = system_one_decisions.decide(
        state_payload, questions, site="autopilot.phase_outcome_shadow"
    )
    if not answers:
        return None

    try:
        outcome_answer = answers["outcome"]
        evidence_answer = answers["evidence_supports_outcome"]
        judged_outcome = _answer_field(outcome_answer, "choice")
        evidence_noul = float(_answer_field(evidence_answer, "noul"))
    except (KeyError, TypeError, ValueError):
        return None
    if judged_outcome is None:
        return None

    return _shadow_entry_dict(
        phase=_SHADOW_PHASE,
        acting_outcome=claimed_outcome,
        judged_outcome=judged_outcome,
        judgment={
            "phase": phase,
            "outcome_distribution": _choice_snapshot(outcome_answer),
            "evidence_noul": evidence_noul,
        },
    )


def attribute_disagreements(
    entries: list[dict[str, Any]],
    review_findings: dict[int, bool],
) -> list[dict[str, Any]]:
    """Attribute each disagreement to the side a later review vindicated.

    `entries` are `"PHASE_OUTCOME_SHADOW"` phase_history entries.
    `review_findings` maps an entry's index in `entries` to whether a later
    review round found the *claimed* outcome wrong (`True`) or upheld it
    (`False`). Only entries present in `review_findings` are attributed --
    real-sprint wiring of this mapping from actual review rounds is out of
    scope for this item (design D5, Non-goals); this function is exercised
    against a caller-constructed fixture.
    """
    attributed: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if entry.get("acting_outcome") == entry.get("judged_outcome"):
            continue  # not a disagreement
        if index not in review_findings:
            continue
        claimed_was_wrong = review_findings[index]
        vindicated = "judged" if claimed_was_wrong else "claimed"
        attributed.append(
            {
                "claimed_outcome": entry.get("acting_outcome"),
                "judged_outcome": entry.get("judged_outcome"),
                "vindicated": vindicated,
            }
        )
    return attributed
