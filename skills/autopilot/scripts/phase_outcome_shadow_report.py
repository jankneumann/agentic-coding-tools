"""Reporting CLI for phase-outcome shadow adjudication (design D5 of
`adjudicate-phase-outcomes-in-shadow-mode`).

Mirrors `gatekeeper_shadow_report.py`'s shape: reads one or more recorded
``loop-state.json`` files, extracts every ``"PHASE_OUTCOME_SHADOW"``
``phase_history`` entry, and prints the disagreement rate. Fully
deterministic -- no model calls -- so it satisfies the autopilot
host-assisted invariant.

    python3 phase_outcome_shadow_report.py openspec/changes/*/loop-state.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_SHADOW_PHASE = "PHASE_OUTCOME_SHADOW"


def _shadow_entries(loop_state_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(loop_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    history = data.get("phase_history")
    if not isinstance(history, list):
        return []
    return [
        entry
        for entry in history
        if isinstance(entry, dict) and entry.get("phase") == _SHADOW_PHASE
    ]


def collect_shadow_entries(paths: list[Path]) -> list[dict[str, Any]]:
    """All phase-outcome shadow entries across every given loop-state.json path."""
    entries: list[dict[str, Any]] = []
    for path in paths:
        entries.extend(_shadow_entries(path))
    return entries


def disagreement_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The disagreement rate and a per-outcome-pair breakdown over *entries*."""
    total = len(entries)
    disagreements = [
        entry
        for entry in entries
        if entry.get("judged_outcome") != entry.get("acting_outcome")
    ]
    pair_counts = Counter(
        (entry.get("acting_outcome"), entry.get("judged_outcome"))
        for entry in disagreements
    )
    return {
        "total_transitions": total,
        "disagreement_count": len(disagreements),
        "disagreement_rate": (len(disagreements) / total) if total else 0.0,
        "disagreement_pairs": {
            f"{claimed} -> {judged}": count
            for (claimed, judged), count in pair_counts.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report the phase-outcome shadow disagreement rate from "
            "recorded loop-state.json files."
        )
    )
    parser.add_argument(
        "loop_state_paths",
        nargs="+",
        help="One or more loop-state.json paths (shell-glob expanded by the caller).",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.loop_state_paths]
    entries = collect_shadow_entries(paths)
    report = disagreement_report(entries)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
