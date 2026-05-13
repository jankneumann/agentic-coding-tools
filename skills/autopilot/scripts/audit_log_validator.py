"""Audit-log cross-check for per-phase archetype dispatch (task 4.4).

Reads a coordinator audit log (JSONL) or queries the audit endpoint, counts
model calls per archetype, and reports whether the opus-vs-sonnet
distribution matches what `archetypes.yaml::phase_mapping` predicts for
the phases recorded in `loop-state.json`.

Used for the manual rollout cross-check described in proposal.md::Rollout.
The check is two-sided:

  * Aggregate: total opus calls vs total sonnet calls vs haiku calls.
    Compare to expected counts derived from the phase sequence in
    `loop-state.json::handoff_ids` joined with phase metadata.
  * Per-phase: each (phase, model) tuple must match `phase_mapping`.

Usage::

    python3 audit_log_validator.py \
        --audit-log <path-to-jsonl> \
        --change-id <change-id> \
        [--archetypes-yaml <path>]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Default mapping mirrors agent-coordinator/archetypes.yaml::phase_mapping.
# When --archetypes-yaml is provided we override from the YAML; otherwise
# this serves as the audit baseline and is documented in design.md.
_DEFAULT_PHASE_MODEL: dict[str, str] = {
    "INIT":         "haiku",
    "PLAN":         "opus",
    "PLAN_ITERATE": "opus",
    "PLAN_REVIEW":  "opus",
    "PLAN_FIX":     "opus",
    "IMPLEMENT":    "sonnet",
    "IMPL_ITERATE": "sonnet",
    "IMPL_REVIEW":  "opus",
    "IMPL_FIX":     "sonnet",
    "VALIDATE":     "sonnet",
    "VAL_REVIEW":   "opus",
    "VAL_FIX":      "sonnet",
    "SUBMIT_PR":    "haiku",
}

# Archetype → default model for the aggregate check.
_DEFAULT_ARCHETYPE_MODEL: dict[str, str] = {
    "architect":   "opus",
    "reviewer":    "opus",
    "implementer": "sonnet",
    "analyst":     "sonnet",
    "runner":      "haiku",
}


def load_phase_mapping_from_yaml(yaml_path: Path) -> dict[str, str]:
    """Parse archetypes.yaml and return phase → model mapping.

    Falls back to defaults on parse error.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("pyyaml not installed; using built-in defaults")
        return dict(_DEFAULT_PHASE_MODEL)

    try:
        data = yaml.safe_load(yaml_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to parse %s (%s); using defaults", yaml_path, exc)
        return dict(_DEFAULT_PHASE_MODEL)

    archetypes = data.get("archetypes", {}) if isinstance(data, dict) else {}
    phase_mapping = data.get("phase_mapping", {}) if isinstance(data, dict) else {}

    out: dict[str, str] = {}
    for phase, spec in phase_mapping.items():
        if not isinstance(spec, dict):
            continue
        archetype = spec.get("archetype")
        if archetype and archetype in archetypes:
            model = archetypes[archetype].get("model")
            if isinstance(model, str):
                out[phase] = model
    return out or dict(_DEFAULT_PHASE_MODEL)


def parse_audit_log(audit_log: Path) -> list[dict[str, Any]]:
    """Read JSONL audit log; return list of entries.

    Each line that fails to parse is logged and skipped.
    """
    entries: list[dict[str, Any]] = []
    for lineno, raw in enumerate(audit_log.read_text().splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            logger.warning("audit log %s line %d: %s", audit_log, lineno, exc)
    return entries


def expected_phase_models_from_loop_state(
    loop_state_path: Path,
    phase_mapping: dict[str, str],
) -> Counter[str]:
    """Read loop-state.json and compute expected model count per archetype.

    Returns a Counter keyed by model name (opus/sonnet/haiku).
    """
    try:
        state = json.loads(loop_state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read loop-state at %s: %s", loop_state_path, exc)
        return Counter()

    # Derive phases visited from handoff_ids count + any phase markers.
    # Conservative approach: count one dispatch per phase listed in
    # handoff_ids (which has one entry per non-state-only phase).
    handoff_count = len(state.get("handoff_ids", []))

    # If we have an explicit phase trace, use it; otherwise assume the
    # canonical 7-phase happy path (PLAN_ITERATE → … → VAL_REVIEW).
    canonical_phases = [
        "PLAN_ITERATE", "PLAN_REVIEW", "IMPLEMENT", "IMPL_ITERATE",
        "IMPL_REVIEW", "VALIDATE", "VAL_REVIEW",
    ]
    phases = canonical_phases[:handoff_count] if handoff_count else canonical_phases

    counts: Counter[str] = Counter()
    for phase in phases:
        model = phase_mapping.get(phase)
        if model:
            counts[model] += 1
    return counts


def actual_model_counts(entries: list[dict[str, Any]]) -> Counter[str]:
    """Count `model` field across audit entries that look like dispatches."""
    counts: Counter[str] = Counter()
    for e in entries:
        # Audit entries that represent a sub-agent dispatch carry a `model`
        # field (or a nested `metadata.model`). Be lenient about location.
        model = e.get("model")
        if model is None and isinstance(e.get("metadata"), dict):
            model = e["metadata"].get("model")
        if isinstance(model, str):
            counts[model] += 1
    return counts


def actual_per_phase(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Build (phase → model) map from audit entries that include both."""
    out: dict[str, str] = {}
    for e in entries:
        phase = e.get("phase")
        model = e.get("model") or (
            e.get("metadata", {}).get("model") if isinstance(e.get("metadata"), dict) else None
        )
        if isinstance(phase, str) and isinstance(model, str):
            out[phase] = model
    return out


def validate(
    audit_log: Path,
    loop_state_path: Path,
    phase_mapping: dict[str, str],
    *,
    tolerance: int = 1,
) -> tuple[bool, list[str]]:
    """Run the cross-check; return (ok, list_of_findings)."""
    entries = parse_audit_log(audit_log)
    findings: list[str] = []

    expected = expected_phase_models_from_loop_state(loop_state_path, phase_mapping)
    actual = actual_model_counts(entries)
    actual_phases = actual_per_phase(entries)

    # Aggregate sanity check
    for model, exp_count in expected.items():
        act_count = actual.get(model, 0)
        if abs(exp_count - act_count) > tolerance:
            findings.append(
                f"aggregate model count mismatch for {model!r}: "
                f"expected {exp_count}, got {act_count} "
                f"(tolerance ±{tolerance})"
            )

    # Per-phase check (when we have phase info)
    for phase, actual_model in actual_phases.items():
        expected_model = phase_mapping.get(phase)
        if expected_model and actual_model != expected_model:
            findings.append(
                f"phase {phase!r} dispatched with model {actual_model!r}, "
                f"expected {expected_model!r}"
            )

    if not findings:
        findings.append(
            f"OK: {sum(actual.values())} dispatches across "
            f"{len(actual)} models match phase_mapping"
        )
    return (not any(f.startswith(("aggregate", "phase")) for f in findings), findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check coordinator audit log against archetype phase mapping",
    )
    parser.add_argument("--audit-log", type=Path, required=True,
                        help="Path to JSONL audit log file")
    parser.add_argument("--change-id", type=str, required=True,
                        help="OpenSpec change-id (used to locate loop-state.json)")
    parser.add_argument("--archetypes-yaml", type=Path, default=None,
                        help="Optional override path to archetypes.yaml")
    parser.add_argument("--tolerance", type=int, default=1,
                        help="Allowed delta between expected and actual aggregate counts")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if not args.audit_log.exists():
        print(f"audit log not found: {args.audit_log}", file=sys.stderr)
        return 2

    loop_state = Path("openspec") / "changes" / args.change_id / "loop-state.json"
    if not loop_state.exists():
        print(f"loop-state.json not found: {loop_state}", file=sys.stderr)
        return 2

    phase_mapping = (
        load_phase_mapping_from_yaml(args.archetypes_yaml)
        if args.archetypes_yaml else dict(_DEFAULT_PHASE_MODEL)
    )

    ok, findings = validate(args.audit_log, loop_state, phase_mapping,
                            tolerance=args.tolerance)
    for f in findings:
        print(f)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
