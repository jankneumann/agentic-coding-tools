"""workflow.prototype-recommended advisory emitter for /iterate-on-plan.

Per D8, when an iterate-on-plan refinement batch produces ≥3 high-
criticality findings in clarity OR feasibility (combined), emit a
single ``workflow.prototype-recommended`` advisory finding. The
finding is **non-actionable** — humans decide whether to invoke
/prototype-feature in response.

Why these dimensions: prototyping addresses *uncertainty in shape*,
which manifests as clarity gaps (ambiguous requirements) and
feasibility doubts (unclear how to do it). Other dimensions (security,
performance) signal different problems with their own remediations.

Spec scenarios:
  - PrototypeRecommendationSignal.threshold-met
  - PrototypeRecommendationSignal.threshold-not-met
  - PrototypeRecommendationSignal.advisory-only

D8 default threshold = 3. Tunable via the constant below; never via a
runtime flag (the SKILL workflow is intentionally opinionated here).
"""

from __future__ import annotations

from typing import Any, Final, Iterable

PROTOTYPE_RECOMMENDED_TYPE: Final[str] = "workflow.prototype-recommended"
PROTOTYPE_RECOMMENDED_THRESHOLD: Final[int] = 3
_TRIGGERING_DIMENSIONS: Final[tuple[str, ...]] = ("clarity", "feasibility")


def _is_high_clarity_or_feasibility(finding: dict[str, Any]) -> bool:
    if finding.get("criticality") != "high":
        return False
    type_ = finding.get("type", "")
    # Finding type prefix: clarity.* or feasibility.* (the existing
    # iterate-on-plan finding taxonomy uses dotted dimensions).
    return any(
        type_.startswith(f"{dim}.") or type_ == dim
        for dim in _TRIGGERING_DIMENSIONS
    )


def maybe_emit_prototype_recommended(
    findings: Iterable[dict[str, Any]],
    *,
    change_id: str,
) -> dict[str, Any] | None:
    """Return a workflow.prototype-recommended finding when threshold met.

    The output finding has criticality=low so it sorts to the bottom of
    iteration reports — it's a hint, not a problem to fix. The
    description names the count and suggests the command so humans can
    act on it without consulting docs.

    Returns None when the threshold isn't met. Callers append the result
    to their finding list when not None; do not append None entries.
    """
    triggering = [f for f in findings if _is_high_clarity_or_feasibility(f)]
    if len(triggering) < PROTOTYPE_RECOMMENDED_THRESHOLD:
        return None

    triggering_types = sorted({f.get("type", "?") for f in triggering})
    return {
        "type": PROTOTYPE_RECOMMENDED_TYPE,
        "criticality": "low",
        "description": (
            f"{len(triggering)} high-criticality clarity+feasibility findings "
            f"in this batch ({', '.join(triggering_types)}). Consider running "
            f"/prototype-feature {change_id} to explore design alternatives "
            "before continuing refinement. This advisory does NOT block "
            "iteration — decide based on whether the uncertainty is in shape "
            "(prototype helps) or in detail (prototype won't)."
        ),
    }


__all__ = [
    "PROTOTYPE_RECOMMENDED_THRESHOLD",
    "PROTOTYPE_RECOMMENDED_TYPE",
    "maybe_emit_prototype_recommended",
]
