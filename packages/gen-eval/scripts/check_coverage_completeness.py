#!/usr/bin/env python3
"""Every contracted coverage unit is exercised, or excluded with a reason (D11).

``make dogfood``'s acceptance gate for the **tool** archetype. Deliberately not
either of the two obvious alternatives:

- **Not** ``declared_interfaces_non_empty``. That goes green on a run that
  exercised nothing, which is the vacuous pass the whole coverage model exists
  to catch.
- **Not** ``coverage_pct >= 80``. Unreachable for this surface — 14 of
  gen-eval's 17 flags would have to be exercised and 5 are. A gate that can
  never pass is the mirror of one that can never fail, and gets disabled just
  as fast.

A percentage also answers the wrong question. "84% covered" does not say
whether the missing 16% is ``--verbose`` or ``--fail-threshold``. Completeness
forces that judgement into a file a reviewer reads.

The percentage is still printed. It is informative; it is not the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPORT = _PACKAGE_ROOT / "evaluation" / ".reports" / "gen-eval-report.json"
DEFAULT_EXCLUSIONS = _PACKAGE_ROOT / "evaluation" / "coverage-exclusions.yaml"


def _fail(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    return 1


def load_exclusions(path: Path) -> dict[str, str]:
    """Map each excluded unit to its stated reason.

    Returns the reason verbatim, including a blank one — deciding that a blank
    reason is a failure is the caller's job, and swallowing it here would turn
    an unexplained exclusion into an absent one.
    """
    import yaml

    if not path.is_file():
        raise FileNotFoundError(path)
    document = yaml.safe_load(path.read_text()) or {}
    entries = document.get("exclusions") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: `exclusions` must be a list, got {type(entries).__name__}")

    excluded: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("unit"):
            raise ValueError(f"{path}: every exclusion needs a `unit`, got {entry!r}")
        excluded[str(entry["unit"])] = str(entry.get("reason") or "")
    return excluded


def check(report: dict[str, Any], excluded: dict[str, str], source: str) -> int:
    """Return an exit code. Reports every failure, not only the first."""
    declared = int(report.get("declared_interface_count") or 0)
    if declared == 0:
        return _fail(
            f"{source} declares zero coverage units — refusing to treat an "
            f"empty declared surface as coverage. Coverage of nothing is "
            f"indistinguishable from full coverage."
        )

    coverage_pct = float(report.get("coverage_pct") or 0.0)
    if coverage_pct <= 0:
        return _fail(
            f"{source} reports 0% coverage across {declared} declared units. "
            f"Excluding the entire surface is not a covered suite; a zero here "
            f"usually means the declared and tested vocabularies never "
            f"connected at all."
        )

    unevaluated = [str(u) for u in (report.get("unevaluated_interfaces") or [])]
    exercised = set(report.get("per_interface") or {})

    failures: list[str] = []

    unexplained = [unit for unit in unevaluated if unit not in excluded]
    if unexplained:
        failures.append(
            "these coverage units are neither exercised by a scenario nor "
            "excluded with a reason:\n"
            + "\n".join(f"  - {unit}" for unit in sorted(unexplained))
            + "\nAdd a scenario, or record why not in the exclusions file."
        )

    blank = [unit for unit, reason in excluded.items() if not reason.strip()]
    if blank:
        failures.append(
            "these exclusions carry no reason:\n"
            + "\n".join(f"  - {unit}" for unit in sorted(blank))
            + "\nAn unexplained exclusion is how a coverage gap gets laundered "
            "into 'intentional'."
        )

    # A unit that is neither unevaluated nor exercised is not in the declared
    # surface at all, so an exclusion naming it explains nothing. Left in
    # place it accumulates, and the next flag to reuse the name inherits an
    # approval nobody granted it.
    known = set(unevaluated) | exercised
    stale = [unit for unit in excluded if unit not in known]
    if stale:
        failures.append(
            "these exclusions name units the contract does not declare:\n"
            + "\n".join(f"  - {unit}" for unit in sorted(stale))
            + "\nRemove them; they no longer explain anything."
        )

    if failures:
        return _fail("\n\n".join(failures))

    print(
        f"coverage complete: {len(exercised)} of {declared} units exercised "
        f"({coverage_pct:.1f}%), {len(excluded)} excluded with reasons"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    args = parser.parse_args(argv)

    if not args.report.is_file():
        return _fail(
            f"no report at {args.report} — a missing report is not a passing "
            f"one. Run `make dogfood` first."
        )
    try:
        excluded = load_exclusions(args.exclusions)
    except FileNotFoundError:
        return _fail(
            f"no exclusions file at {args.exclusions}. Every unit the suite "
            f"does not exercise needs a written reason; create it, empty if "
            f"the suite exercises everything."
        )
    except ValueError as exc:
        return _fail(str(exc))

    report = json.loads(args.report.read_text())
    return check(report, excluded, str(args.report))


if __name__ == "__main__":
    sys.exit(main())
