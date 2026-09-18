"""GATEKEEPER shadow judgment (OpenSpec
`run-the-gatekeeper-as-a-scored-decision-in-shadow-mode`, roadmap item
`ri-06` of `roadmap-jev-system-one-integration-assessment`).

Runs a calibrated `Score`/`Choice`-based judgment alongside the existing
premium-tier GATEKEEPER judge, without acting on it: the acting verdict
(`_phase_gatekeeper`'s return value) is computed exactly as it is today,
and this module only appends an observational record. See design.md's D1
for why the call lives inside `_phase_gatekeeper` and D3 for the config-
sourced threshold shape.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autopilot import LoopState

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Per system_one_decisions.testing's own documented stubbing rule: import the
# module, never a pre-bound name, so `stub_decide`/monkeypatch reaches the
# attribute this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

DEFAULT_CONFIG_PATH = _THIS_DIR / "gatekeeper-shadow.json"

DEFAULT_RISK_ESCALATE_LEVEL = 2.5
DEFAULT_RISK_REVIEW_LEVEL = 1.5
DEFAULT_VERIFIABILITY_ESCALATE_LEVEL = 0.5
DEFAULT_VERIFIABILITY_REVIEW_LEVEL = 1.5

_SHADOW_PHASE = "GATEKEEPER_SHADOW"

_VERIFIABILITY_CRITERIA = [
    "Unverifiable: no testable acceptance criteria.",
    "Weakly verifiable: some criteria, but mostly a free-text description.",
    "Verifiable: WHEN/THEN scenarios and a task breakdown exist.",
    "Strongly verifiable: WHEN/THEN scenarios, a task breakdown, and a "
    "work-packages plan all exist and agree.",
]

_RISK_CRITERIA = [
    "Low: narrow write scope, no migration or security signal.",
    "Moderate: broader write scope or one risk signal present.",
    "High: a db migration or security signal, or several external "
    "dependencies.",
    "Critical: multiple risk signals together, or an unbounded write scope.",
]

_VERDICT_CRITERIA = {
    "proceed": "Verifiable and low risk enough to automate.",
    "proceed_with_review": "Automate, but schedule the extra "
                            "validation-review checkpoint.",
    "escalate": "Unverifiable outcomes or unacceptable risk -- stop for a "
                "human.",
}


@dataclass(frozen=True)
class ShadowThresholds:
    risk_escalate: float = DEFAULT_RISK_ESCALATE_LEVEL
    risk_review: float = DEFAULT_RISK_REVIEW_LEVEL
    verifiability_escalate: float = DEFAULT_VERIFIABILITY_ESCALATE_LEVEL
    verifiability_review: float = DEFAULT_VERIFIABILITY_REVIEW_LEVEL


def load_shadow_thresholds(config_path: Path | None = None) -> ShadowThresholds:
    """Read the optional sidecar JSON, falling back to the module defaults.

    Single default layer only (design D3's Non-goal) -- no project-override
    layer, mirroring the constraint `review_rules.py::_coverage_quorum_threshold`
    already established for `parallel-infrastructure` (no natural repo_root
    to resolve an override against; here there is not even a precedent that
    asked for one).
    """
    path = config_path or DEFAULT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ShadowThresholds()
    if not isinstance(raw, dict):
        return ShadowThresholds()

    def _field(name: str, default: float) -> float:
        # A malformed sidecar (wrong shape, non-numeric value) must degrade
        # to the default for that field, never raise -- shadow configuration
        # errors can never become a GATEKEEPER phase exception (design's own
        # safety property: shadow judgment cannot affect acting behavior).
        try:
            return float(raw.get(name, default))
        except (TypeError, ValueError):
            return default

    return ShadowThresholds(
        risk_escalate=_field("risk_escalate", DEFAULT_RISK_ESCALATE_LEVEL),
        risk_review=_field("risk_review", DEFAULT_RISK_REVIEW_LEVEL),
        verifiability_escalate=_field(
            "verifiability_escalate", DEFAULT_VERIFIABILITY_ESCALATE_LEVEL
        ),
        verifiability_review=_field(
            "verifiability_review", DEFAULT_VERIFIABILITY_REVIEW_LEVEL
        ),
    )


def compute_candidate_verdict(
    risk_score: float,
    verifiability_score: float,
    thresholds: ShadowThresholds,
) -> str:
    """Pure threshold logic over the two Score answers (design D3).

    Never invoked from the acting-verdict path -- only from the shadow
    judgment -- so its defaults may be freely tuned during the shadow period
    without changing any behavior.
    """
    if (
        risk_score >= thresholds.risk_escalate
        or verifiability_score <= thresholds.verifiability_escalate
    ):
        return "escalate"
    if (
        risk_score >= thresholds.risk_review
        or verifiability_score <= thresholds.verifiability_review
    ):
        return "proceed_with_review"
    return "proceed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _shadow_entry_dict(
    *,
    phase: str,
    acting_outcome: str | None,
    judged_outcome: str,
    judgment: dict[str, Any],
) -> dict[str, Any]:
    """The shared shadow envelope shape (design D4).

    `ri-07`'s own shadow record (a different phase transition point) may
    build its own entry with this same envelope and its own `phase`/
    `judgment` payload. `phase` here is a synthetic marker (e.g.
    `"GATEKEEPER_SHADOW"`), never the real phase name, so every existing
    `phase_history` consumer -- which filters by an exact `phase` match --
    stays inert to it.
    """
    return {
        "phase": phase,
        "at": _now_iso(),
        "kind": "shadow",
        "acting_outcome": acting_outcome,
        "judged_outcome": judged_outcome,
        "judgment": judgment,
    }


def record_shadow_judgment(
    state: "LoopState",
    *,
    phase: str,
    acting_outcome: str | None,
    judged_outcome: str,
    judgment: dict[str, Any],
) -> None:
    """Append one shadow entry to `state.phase_history` (design D4).

    A thin `LoopState`-mutating wrapper over `_shadow_entry_dict`, for
    callers that hold a `LoopState` (the Python-level `_phase_gatekeeper`
    path, and any `ri-07` reuse of the same envelope).
    """
    state.phase_history.append(
        _shadow_entry_dict(
            phase=phase,
            acting_outcome=acting_outcome,
            judged_outcome=judged_outcome,
            judgment=judgment,
        )
    )


def _work_packages_summary(change_dir: Path) -> dict[str, Any] | None:
    """A compact profile of work-packages.yaml, not a raw dump (design D5)."""
    wp_path = change_dir / "work-packages.yaml"
    if not wp_path.is_file():
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        raw = yaml.safe_load(wp_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    packages = raw.get("packages") if isinstance(raw, dict) else None
    if not isinstance(packages, list):
        return None
    package_ids = [p.get("id") for p in packages if isinstance(p, dict) and p.get("id")]
    has_dependencies = any(
        isinstance(p, dict) and p.get("depends_on") for p in packages
    )
    return {
        "package_count": len(packages),
        "package_ids": package_ids,
        "has_dependencies": has_dependencies,
    }


def _read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _score_snapshot(answer: Any) -> dict[str, Any]:
    return {
        "score": _answer_field(answer, "score"),
        "confidence": _answer_field(answer, "confidence"),
        "probabilities": _answer_field(answer, "probabilities", {}),
    }


def _choice_snapshot(answer: Any) -> dict[str, Any]:
    return {
        "choice": _answer_field(answer, "choice"),
        "confidence": _answer_field(answer, "confidence"),
        "probabilities": _answer_field(answer, "probabilities", {}),
    }


def build_shadow_entry(
    gate_signals: dict[str, Any],
    change_dir: Path | None,
    *,
    acting_verdict: str | None,
) -> dict[str, Any] | None:
    """The GATEKEEPER shadow step (design D1), as a pure function.

    Returns the shadow `phase_history` entry, or `None` when `change_dir` is
    `None`, the helper module is unavailable, `decide()` returns `None` (any
    of its four unavailability branches), or the returned answer set is
    missing an expected field. Never raises; never influences
    `acting_verdict`.

    Deliberately independent of `LoopState` so both the Python-level
    `_phase_gatekeeper` path (via `shadow_gatekeeper_judgment` below) and the
    real host-driven `phase_agent.apply_phase_outcome` path -- which works
    with a plain state dict, not a `LoopState` -- can call it identically.
    Codex review, PR #591: the host-driven GATEKEEPER dispatch protocol
    (`skills/autopilot/SKILL.md` Step 1.5: `build-dispatch` / `apply-outcome`)
    never calls `_phase_gatekeeper` at all, so the shadow judgment must not
    live only there.
    """
    if change_dir is None or system_one_decisions is None:
        return None

    state_payload: dict[str, Any] = {"gate_signals": dict(gate_signals)}
    proposal_text = _read_text_if_exists(change_dir / "proposal.md")
    if proposal_text is not None:
        state_payload["proposal"] = proposal_text
    tasks_text = _read_text_if_exists(change_dir / "tasks.md")
    if tasks_text is not None:
        state_payload["tasks"] = tasks_text
    wp_summary = _work_packages_summary(change_dir)
    if wp_summary is not None:
        state_payload["work_packages_summary"] = wp_summary

    questions = {
        "verifiability": {
            "type": "score",
            "instructions": (
                "How verifiable are this change's outcomes from its "
                "artifacts -- can they be objectively checked?"
            ),
            "criteria": _VERIFIABILITY_CRITERIA,
        },
        "risk": {
            "type": "score",
            "instructions": (
                "How risky is this change if a slice of it goes wrong -- "
                "blast radius and reversibility?"
            ),
            "criteria": _RISK_CRITERIA,
        },
        "verdict": {
            "type": "choice",
            "instructions": "Given the above, which outcome would you choose?",
            "criteria": _VERDICT_CRITERIA,
        },
    }

    answers = system_one_decisions.decide(
        state_payload, questions, site="autopilot.gatekeeper_shadow"
    )
    if not answers:
        return None

    try:
        verifiability_answer = answers["verifiability"]
        risk_answer = answers["risk"]
        verdict_answer = answers["verdict"]
        risk_score = float(_answer_field(risk_answer, "score"))
        verifiability_score = float(_answer_field(verifiability_answer, "score"))
    except (KeyError, TypeError, ValueError):
        return None

    thresholds = load_shadow_thresholds()
    candidate_verdict = compute_candidate_verdict(
        risk_score, verifiability_score, thresholds
    )

    return _shadow_entry_dict(
        phase=_SHADOW_PHASE,
        acting_outcome=acting_verdict,
        judged_outcome=candidate_verdict,
        judgment={
            "verifiability": _score_snapshot(verifiability_answer),
            "risk": _score_snapshot(risk_answer),
            "choice_cross_check": _choice_snapshot(verdict_answer),
        },
    )


def shadow_gatekeeper_judgment(
    state: "LoopState",
    change_dir: Path | None,
    *,
    acting_verdict: str | None,
) -> None:
    """`LoopState`-mutating wrapper over `build_shadow_entry` (design D1).

    Used by the Python-level `_phase_gatekeeper` path. Appends nothing when
    `build_shadow_entry` returns `None`.
    """
    entry = build_shadow_entry(
        dict(state.gate_signals), change_dir, acting_verdict=acting_verdict
    )
    if entry is not None:
        state.phase_history.append(entry)
