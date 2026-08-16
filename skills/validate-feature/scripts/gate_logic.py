"""Gate logic for validation pipeline — soft and hard gates.

Parses validation-report.md for phase sections and determines
whether the pipeline should continue or halt.

Design decision D7: Gates check validation-report.md for
phase sections with **Status**: pass/fail/skipped/DEGRADED.

Status vocabulary (contracts/architecture-gates-config.md):

| Status     | Meaning                                | soft_gate   | hard_gate                   |
|------------|----------------------------------------|-------------|-----------------------------|
| `pass`     | Checked, passed                        | continue    | continue                    |
| `fail`     | Checked, failed                        | warn        | block                       |
| `skipped`  | Intentionally not run                  | continue    | block if required           |
| `DEGRADED` | **Could not be checked**                | warn loudly | block unless --accept-degraded |

Design decision D4: the Architecture phase is config-ratcheted through
`architecture.config.yaml`. With `gates.architecture.mode: advisory` (the
shipped default, and the fallback whenever the file is absent or unreadable)
the Architecture phase is NOT a required phase and architecture findings never
change a run's outcome. Flipping the mode to `blocking` adds "Architecture" to
the required phases and makes a new dependency cycle fail the gate.

Functions:
    check_phase_status(report_path, section) -> 'pass' | 'fail' | 'skipped' | 'degraded' | 'missing'
    check_smoke_status(report_path) -> same
    load_gate_config(config_path) -> dict          # optional file, safe defaults
    architecture_mode(config_path) -> 'advisory' | 'blocking'
    resolve_required_phases(config_path) -> dict[str, str]
    severity_for_category(category, config_path) -> str
    architecture_status(findings, config_path) -> 'pass' | 'fail'
    soft_gate(report_path) -> (action, reason)   # action always 'continue'
    hard_gate(report_path, accept_degraded=()) -> (action, reason)
    pre_merge_gate(report_path, force=False, accept_degraded=(), config_path=None)
        -> (action, reason, details)
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

# Phases that must pass before merge is allowed.
# Maps section heading -> human-readable name.
REQUIRED_PHASES: dict[str, str] = {
    "Smoke Tests": "Smoke tests",
    "Security": "Security scan",
    "E2E Tests": "E2E tests",
}

# The Architecture phase joins the required set only in blocking mode (D4).
ARCHITECTURE_PHASE_HEADING = "Architecture"
ARCHITECTURE_PHASE_LABEL = "Architecture gate"

# "Could not be checked" — distinct from both pass and fail (D6).
DEGRADED = "degraded"


# ---------------------------------------------------------------------------
# Architecture gate configuration (optional file, safe defaults — Rule 4)
# ---------------------------------------------------------------------------

CONFIG_FILENAME = "architecture.config.yaml"

DEFAULT_ARCHITECTURE_GATE: dict[str, Any] = {
    "mode": "advisory",
    "block_on": {"new_dependency_cycles": True},
    "clean_runs_before_flip": 3,
}

DEFAULT_SEVERITY_THRESHOLDS: dict[str, str] = {
    "new_cycle": "critical",
    "cross_layer_violation": "major",
    "file_size": "minor",
}

VALID_MODES = ("advisory", "blocking")

_KNOWN_ARCHITECTURE_KEYS = frozenset(DEFAULT_ARCHITECTURE_GATE) | {"severity_thresholds"}

# block_on toggle -> finding category it governs. `block_on` decides what
# blocks; `severity_thresholds` decides how a category is labelled. Keeping the
# two separate means the Phase-2 flip is a mode change, not a severity audit.
_BLOCK_ON_CATEGORIES: dict[str, str] = {"new_dependency_cycles": "new_cycle"}

_DEFAULT_CATEGORY_SEVERITY = "minor"


def _default_gate_config() -> dict[str, Any]:
    return {
        "architecture": {
            "mode": DEFAULT_ARCHITECTURE_GATE["mode"],
            "block_on": dict(DEFAULT_ARCHITECTURE_GATE["block_on"]),
            "clean_runs_before_flip": DEFAULT_ARCHITECTURE_GATE["clean_runs_before_flip"],
        },
        "severity_thresholds": dict(DEFAULT_SEVERITY_THRESHOLDS),
    }


def _find_config(config_path: str | Path | None) -> Path | None:
    """Locate architecture.config.yaml, or None when there is nothing to read.

    An explicitly passed path that does not exist yields None (built-in
    defaults) rather than an error — the file is optional per the
    `report-configuration` spec.
    """
    if config_path is not None:
        candidate = Path(config_path)
        return candidate if candidate.is_file() else None

    seen: set[Path] = set()
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        for parent in (base, *base.parents):
            if parent in seen:
                continue
            seen.add(parent)
            candidate = parent / CONFIG_FILENAME
            if candidate.is_file():
                return candidate
    return None


def load_gate_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load gate configuration, falling back to built-in advisory defaults.

    The file is optional. A missing, empty, unparseable, or malformed file
    yields the defaults; unknown keys warn rather than error (forward
    compatibility, matching the architecture report generator's behavior).
    """
    config = _default_gate_config()

    path = _find_config(config_path)
    if path is None:
        return config

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        warnings.warn(
            f"PyYAML not available — using built-in gate defaults instead of {path}",
            stacklevel=2,
        )
        return config

    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        warnings.warn(
            f"Could not read {path} ({exc}) — using built-in gate defaults",
            stacklevel=2,
        )
        return config

    if not isinstance(raw, dict):
        return config

    gates = raw.get("gates")
    architecture = gates.get("architecture") if isinstance(gates, dict) else None
    if isinstance(architecture, dict):
        for key in architecture:
            if key not in _KNOWN_ARCHITECTURE_KEYS:
                warnings.warn(
                    f"Unknown gates.architecture key '{key}' — will be ignored",
                    stacklevel=2,
                )

        mode = architecture.get("mode", config["architecture"]["mode"])
        if mode in VALID_MODES:
            config["architecture"]["mode"] = mode
        else:
            warnings.warn(
                f"Unknown gates.architecture.mode '{mode}' — falling back to "
                f"'{DEFAULT_ARCHITECTURE_GATE['mode']}'",
                stacklevel=2,
            )

        block_on = architecture.get("block_on")
        if isinstance(block_on, dict):
            config["architecture"]["block_on"].update(
                {str(k): bool(v) for k, v in block_on.items()}
            )

        flip = architecture.get("clean_runs_before_flip")
        if isinstance(flip, int):
            config["architecture"]["clean_runs_before_flip"] = flip

    # Thresholds live in the gate's own namespace. `health.severity_thresholds`
    # is read as a fallback for configs written before the gate had one, but it
    # belongs to the architecture report, which grades on {error, warning, info}
    # rather than the gate's {critical, major, minor}. Two consumers sharing one
    # key with different vocabularies is how a threshold ends up silently
    # filtering nothing, so new config should use the gate namespace.
    thresholds: Any = None
    if isinstance(architecture, dict):
        thresholds = architecture.get("severity_thresholds")
    if not isinstance(thresholds, dict):
        health = raw.get("health")
        thresholds = (
            health.get("severity_thresholds") if isinstance(health, dict) else None
        )
    if isinstance(thresholds, dict):
        config["severity_thresholds"].update(
            {str(k): str(v) for k, v in thresholds.items()}
        )

    return config


def _resolved(
    config: dict[str, Any] | None,
    config_path: str | Path | None,
) -> dict[str, Any]:
    return config if config is not None else load_gate_config(config_path)


def architecture_mode(
    config_path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> str:
    """Return the configured architecture gate mode ('advisory' | 'blocking')."""
    return str(_resolved(config, config_path)["architecture"]["mode"])


def resolve_required_phases(
    config_path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return the required phases for this run.

    Identical to REQUIRED_PHASES in advisory mode (the shipped default), so
    this change cannot alter the outcome of an existing validation run.
    """
    phases = dict(REQUIRED_PHASES)
    if architecture_mode(config_path, config=_resolved(config, config_path)) == "blocking":
        phases[ARCHITECTURE_PHASE_HEADING] = ARCHITECTURE_PHASE_LABEL
    return phases


def severity_for_category(
    category: str,
    config_path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> str:
    """Map an architecture finding category onto its configured severity.

    A new dependency cycle maps to `critical` by default (D4).
    """
    thresholds = _resolved(config, config_path)["severity_thresholds"]
    return str(thresholds.get(category, _DEFAULT_CATEGORY_SEVERITY))


def _finding_category(finding: dict[str, Any]) -> str:
    """Best-effort category for an architecture finding."""
    category = finding.get("category")
    if isinstance(category, str) and category:
        return category
    text = " ".join(
        str(finding.get(key, "")) for key in ("description", "title", "type")
    ).lower()
    if "dependency cycle" in text or "new cycle" in text:
        return "new_cycle"
    return "unknown"


def architecture_status(
    findings: Iterable[dict[str, Any]],
    config_path: str | Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> str:
    """Return 'pass' or 'fail' for the Architecture phase given its findings.

    Advisory mode always returns 'pass' — findings are still rendered in
    validation-report.md, they just do not change the run's outcome. Blocking
    mode fails on any finding whose category is enabled in `block_on`
    (today: a new dependency cycle).
    """
    resolved = _resolved(config, config_path)
    architecture = resolved["architecture"]

    if architecture.get("mode") != "blocking":
        return "pass"

    block_on = architecture.get("block_on") or {}
    blocking_categories = {
        category
        for toggle, category in _BLOCK_ON_CATEGORIES.items()
        if block_on.get(toggle)
    }

    for finding in findings:
        if _finding_category(finding) in blocking_categories:
            return "fail"
    return "pass"


# ---------------------------------------------------------------------------
# Report parsing
# ---------------------------------------------------------------------------

# Legacy vocabulary, matched exactly as before so no existing report changes
# meaning. DEGRADED is matched separately (and case-insensitively, since the
# contract writes it uppercase in the phase table).
_LEGACY_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*(pass|fail|skipped)")
_DEGRADED_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*degraded", re.IGNORECASE)


def check_phase_status(report_path: str, section_heading: str) -> str:
    """Parse validation-report.md for a phase's status.

    Args:
        report_path: Path to validation-report.md
        section_heading: The ## heading to look for (e.g. "Smoke Tests")

    Returns:
        'pass', 'fail', 'skipped', 'degraded', or 'missing'
    """
    p = Path(report_path)
    if not p.exists():
        return "missing"

    content = p.read_text()

    if f"## {section_heading}" not in content:
        return "missing"

    # Extract section content between ## heading and next ## heading (or EOF)
    pattern = rf"## {re.escape(section_heading)}\s*\n(.*?)(?=\n## |\Z)"
    section_match = re.search(pattern, content, re.DOTALL)

    if not section_match:
        return "missing"

    section_content = section_match.group(1)

    # Look for **Status**: line
    status_match = _LEGACY_STATUS_RE.search(section_content)
    if status_match:
        return status_match.group(1)

    if _DEGRADED_STATUS_RE.search(section_content):
        return DEGRADED

    return "missing"


def check_smoke_status(report_path: str) -> str:
    """Parse validation-report.md for smoke test status.

    Convenience wrapper around check_phase_status for backward compatibility.

    Args:
        report_path: Path to validation-report.md

    Returns:
        'pass', 'fail', 'skipped', 'degraded', or 'missing'
    """
    return check_phase_status(report_path, "Smoke Tests")


# ---------------------------------------------------------------------------
# Degraded-override helpers
# ---------------------------------------------------------------------------

def _normalise_overrides(accept_degraded: Sequence[str] | None) -> set[str]:
    return {str(name).strip().lower() for name in (accept_degraded or ()) if str(name).strip()}


def _override_matches(heading: str, label: str, overrides: set[str]) -> bool:
    """An override may name either the report heading or the readable label."""
    return heading.lower() in overrides or label.lower() in overrides


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def soft_gate(report_path: str) -> tuple[str, str]:
    """Soft gate for /implement-feature — always continues.

    Args:
        report_path: Path to validation-report.md

    Returns:
        Tuple of (action, reason).
        action is always 'continue'.
    """
    status = check_smoke_status(report_path)

    if status == "pass":
        return ("continue", "Smoke tests passed.")
    elif status == "fail":
        return ("continue", "WARNING: Smoke tests failed. Continuing (soft gate).")
    elif status == DEGRADED:
        return (
            "continue",
            "WARNING: Smoke tests are DEGRADED — they were NOT CHECKED "
            "(checker unavailable). This is not a pass. Continuing (soft gate).",
        )
    elif status == "skipped":
        return ("continue", "WARNING: Smoke tests skipped. Continuing (soft gate).")
    else:  # missing
        return ("continue", "Smoke tests not yet run. Will trigger deploy+smoke.")


def hard_gate(
    report_path: str,
    *,
    accept_degraded: Sequence[str] | None = None,
) -> tuple[str, str]:
    """Hard gate for /cleanup-feature — blocks on non-pass status.

    Args:
        report_path: Path to validation-report.md
        accept_degraded: Phase names whose DEGRADED status the operator
            explicitly accepts. The override is echoed into the returned reason.

    Returns:
        Tuple of (action, reason).
        action is 'continue' only if status is 'pass' (or an accepted
        DEGRADED), otherwise 'halt'.
    """
    status = check_smoke_status(report_path)
    overrides = _normalise_overrides(accept_degraded)

    if status == "pass":
        return ("continue", "Smoke tests passed. Proceeding to merge.")
    elif status == "fail":
        return ("halt", "Smoke tests failed. Re-run required before merge.")
    elif status == DEGRADED:
        if _override_matches("Smoke Tests", "Smoke tests", overrides):
            return (
                "continue",
                "DEGRADED OVERRIDE accepted for Smoke tests (Smoke Tests) — "
                "the phase was NOT CHECKED; proceeding by explicit operator override.",
            )
        return (
            "halt",
            "Smoke tests were NOT CHECKED (status DEGRADED) — this is not the "
            "same as a pass. Re-run the phase, or pass "
            "--accept-degraded 'Smoke Tests' to override explicitly.",
        )
    elif status == "skipped":
        return ("halt", "Smoke tests were skipped. Re-run required before merge.")
    else:  # missing
        return ("halt", "Smoke tests missing. Run deploy+smoke before merge.")


def pre_merge_gate(
    report_path: str,
    *,
    force: bool = False,
    accept_degraded: Sequence[str] | None = None,
    config_path: str | Path | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Full pre-merge gate — checks all required phases.

    Returns exit-code-compatible result: 'continue' means merge is allowed,
    'halt' means merge is blocked.

    Args:
        report_path: Path to validation-report.md
        force: If True, override the gate (explicit user bypass).
        accept_degraded: Phase names whose DEGRADED status the operator
            explicitly accepts. Each accepted override is named in the summary.
        config_path: Optional path to architecture.config.yaml. Governs whether
            the Architecture phase is required (D4); defaults to advisory.

    Returns:
        Tuple of (action, reason, phase_statuses).
        phase_statuses maps phase name -> status string.
    """
    phases = resolve_required_phases(config_path)
    overrides = _normalise_overrides(accept_degraded)

    phase_statuses: dict[str, str] = {}
    failures: list[str] = []
    accepted: list[str] = []

    for heading, label in phases.items():
        status = check_phase_status(report_path, heading)
        phase_statuses[heading] = status

        if status == "pass":
            continue

        if status == DEGRADED:
            if _override_matches(heading, label, overrides):
                accepted.append(f"{label} ({heading})")
            else:
                failures.append(f"{label}: DEGRADED — NOT CHECKED")
            continue

        failures.append(f"{label}: {status}")

    override_note = ""
    if accepted:
        override_note = " DEGRADED OVERRIDE accepted for: " + "; ".join(accepted) + "."

    if not failures:
        return (
            "continue",
            "All required phases passed. Proceeding to merge." + override_note,
            phase_statuses,
        )

    failure_summary = "; ".join(failures)

    if force:
        return (
            "continue",
            f"FORCED OVERRIDE — merging despite failures: {failure_summary}"
            + override_note,
            phase_statuses,
        )

    hint = "Re-run failed phases or use --force to override."
    if any("NOT CHECKED" in f for f in failures):
        hint = (
            "Re-run failed phases, pass --accept-degraded <phase> for phases that "
            "could not be checked, or use --force to override."
        )

    return (
        "halt",
        f"Pre-merge gate failed. {failure_summary}. {hint}" + override_note,
        phase_statuses,
    )


def main() -> None:
    """CLI entry point for pre-merge gate check.

    Usage:
        python gate_logic.py <report_path> [--force] [--accept-degraded PHASE]...

    Exit codes:
        0 — merge allowed
        1 — merge blocked
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Pre-merge gate: check all required validation phases.",
    )
    parser.add_argument("report_path", help="Path to validation-report.md")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override gate (explicit user bypass)",
    )
    parser.add_argument(
        "--accept-degraded",
        action="append",
        default=[],
        metavar="PHASE",
        help=(
            "Accept a DEGRADED (could-not-be-checked) required phase. "
            "Repeatable; the override is recorded in the gate summary."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to architecture.config.yaml (default: discovered upward)",
    )
    args = parser.parse_args()

    action, reason, statuses = pre_merge_gate(
        args.report_path,
        force=args.force,
        accept_degraded=args.accept_degraded,
        config_path=args.config,
    )

    result = {
        "action": action,
        "reason": reason,
        "phase_statuses": statuses,
        "force": args.force,
        "accept_degraded": args.accept_degraded,
        "architecture_gate_mode": architecture_mode(args.config),
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if action == "continue" else 1)


if __name__ == "__main__":
    main()
