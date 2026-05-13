"""Per-phase token-budget CI gate.

For each of the 7 sub-agent-dispatching phases (PLAN_ITERATE, PLAN_REVIEW,
IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, VALIDATE, VAL_REVIEW), this script
computes the size of the joined ``system_prompt + SEPARATOR + phase_prompt``
that ``build_phase_dispatch_kwargs`` would emit, then compares it against
the resolved model's context window.

Thresholds (uniform across proposal, design, tasks, spec):
  - >75% of context → exit 1 (fail the build).
  - 60–75% → emit a warning to stderr but exit 0.
  - <60% → silent pass.

The check is run in a hermetic mode: it does NOT contact the coordinator.
Instead, it iterates the phases, builds the *unfolded* phase prompt from
``phase_agent._build_prompt`` against a synthetic state_dict and a
synthetic system_prompt, then estimates the joined token count via a
simple character-based heuristic (``ceil(len(text) / 4)``) — sufficient
for a CI gate that's measuring orders of magnitude, not exact billing.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "Joined prompt token budget is enforced"
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import phase_agent  # type: ignore[import-not-found]  # noqa: E402
from phase_record import PhaseRecord  # type: ignore[import-not-found]  # noqa: E402

# 7 sub-agent-dispatching phases per the design's "Phase-by-phase
# dispatch matrix" (canonical source of truth — D1).
_DISPATCHING_PHASES: tuple[str, ...] = (
    "PLAN_ITERATE",
    "PLAN_REVIEW",
    "IMPLEMENT",
    "IMPL_ITERATE",
    "IMPL_REVIEW",
    "VALIDATE",
    "VAL_REVIEW",
)

# Default model→context-window map. Values are conservative public defaults
# (Claude 4 series base context). Operators can override via --context-window.
_DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
    "opus": 200_000,
    "sonnet": 200_000,
    "haiku": 200_000,
    # Generic fallback for unknown model names — matches the Claude family
    # default; if a vendor with a smaller window is added, callers should
    # pass --context-window explicitly.
    "default": 200_000,
}

# Phase → fallback model when the bridge can't resolve. Pulled from the
# default phase_mapping in archetypes.yaml so the CI gate measures the
# realistic worst case.
_FALLBACK_MODEL_BY_PHASE: dict[str, str] = {
    "PLAN_ITERATE":  "opus",
    "PLAN_REVIEW":   "opus",
    "IMPLEMENT":     "opus",   # implementer escalates to opus on size signals
    "IMPL_ITERATE":  "opus",
    "IMPL_REVIEW":   "opus",
    "VALIDATE":      "sonnet",
    "VAL_REVIEW":    "opus",
}


@dataclass
class PhaseReport:
    phase: str
    model: str
    chars: int
    estimated_tokens: int
    context_window: int
    pct: float
    severity: str  # "ok", "warn", "fail"


def _estimate_tokens(text: str) -> int:
    """Cheap token estimator. ~4 chars/token is the Claude/GPT family heuristic."""
    return math.ceil(len(text) / 4)


def _synthetic_system_prompt() -> str:
    """A synthetic worst-case system prompt for the gate.

    We can't query the live coordinator from CI (the gate runs without
    network), so we use a representative system prompt sized to the
    longest archetype prompt in the archetypes.yaml shipped with the
    repo. The reviewer archetype is currently the longest at ~600 chars.
    Multiplying by 5 gives a comfortable upper bound that catches
    pathological growth.
    """
    body = (
        "You are a code reviewer. Evaluate correctness, security, performance, "
        "and adherence to contracts. Identify issues by severity. Be specific "
        "about locations and fixes. Do not rewrite code — describe what should "
        "change.\n"
    )
    return body * 5


def _build_phase_prompt(phase: str) -> str:
    """Build the unfolded phase prompt for *phase* against a synthetic state."""
    state_dict: dict[str, Any] = {
        "change_id": "synthetic-change",
        "current_phase": phase,
        "iteration": 1,
        "total_iterations": 1,
        "max_phase_iterations": 3,
        "previous_phase": None,
    }
    incoming = PhaseRecord(
        change_id="synthetic-change",
        phase_name="synthetic_predecessor",
        agent_type="autopilot",
        summary="synthetic incoming handoff for token-budget CI gate",
    )
    return phase_agent._build_prompt(phase, state_dict, incoming, artifacts_manifest=None)


def _evaluate_phase(
    phase: str,
    *,
    context_window_override: int | None,
) -> PhaseReport:
    system_prompt = _synthetic_system_prompt()
    phase_prompt = _build_phase_prompt(phase)
    # Reuse phase_agent's canonical separator so a future change to the
    # constant propagates here automatically (closes IMPL_ITERATE finding
    # SC#1: hardcoded literal would let CI silently pass broken builds).
    joined = f"{system_prompt}{phase_agent._PROMPT_SEPARATOR}{phase_prompt}"

    model = _FALLBACK_MODEL_BY_PHASE.get(phase, "default")
    context_window = (
        context_window_override
        if context_window_override is not None
        else _DEFAULT_CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOWS["default"])
    )
    estimated_tokens = _estimate_tokens(joined)
    pct = (estimated_tokens / context_window) * 100.0

    if pct > 75.0:
        severity = "fail"
    elif pct >= 60.0:
        severity = "warn"
    else:
        severity = "ok"

    return PhaseReport(
        phase=phase,
        model=model,
        chars=len(joined),
        estimated_tokens=estimated_tokens,
        context_window=context_window,
        pct=pct,
        severity=severity,
    )


def run(*, context_window_override: int | None = None) -> int:
    reports = [
        _evaluate_phase(phase, context_window_override=context_window_override)
        for phase in _DISPATCHING_PHASES
    ]

    fails = [r for r in reports if r.severity == "fail"]
    warns = [r for r in reports if r.severity == "warn"]

    for r in reports:
        sys.stdout.write(
            f"phase={r.phase:<13} model={r.model:<7} "
            f"tokens~={r.estimated_tokens:>6} window={r.context_window:>7} "
            f"pct={r.pct:6.2f}% severity={r.severity}\n"
        )

    if fails:
        sys.stderr.write(
            "token_budget_check FAILED: "
            f"{len(fails)} phase(s) exceed 75% of model context window:\n"
        )
        for r in fails:
            sys.stderr.write(
                f"  - {r.phase}: ~{r.estimated_tokens} tokens at "
                f"{r.pct:.2f}% of {r.context_window}-token window ({r.model})\n"
            )
        return 1

    if warns:
        sys.stderr.write(
            f"token_budget_check WARN: {len(warns)} phase(s) at 60-75% of context window:\n"
        )
        for r in warns:
            sys.stderr.write(
                f"  - {r.phase}: ~{r.estimated_tokens} tokens at "
                f"{r.pct:.2f}% of {r.context_window}-token window ({r.model})\n"
            )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-phase token-budget CI gate for autopilot dispatching phases.",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=None,
        help=(
            "Override the model context-window size (tokens) for every phase. "
            "Useful for testing the gate with smaller windows."
        ),
    )
    args = parser.parse_args(argv)
    return run(context_window_override=args.context_window)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
