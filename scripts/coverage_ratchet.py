#!/usr/bin/env python3
"""Coverage no-decrease ratchet (design D5 of introduce-fitness-function-gates).

Compares measured line coverage against the percentages stored in
``coverage-baseline.json`` at the repo root and fails when a suite drops by
more than the baseline's ``tolerance_pp``. A ratchet, not an absolute bar: an
arbitrary threshold penalises legacy code, while a ratchet measures drift.

Usage
-----

    # measured percentages passed explicitly
    python scripts/coverage_ratchet.py \
        --measured agent-coordinator=71.2 --measured skills=64.0

    # or read the line rate out of a Cobertura coverage.xml
    python scripts/coverage_ratchet.py \
        --coverage-xml agent-coordinator=agent-coordinator/coverage.xml \
        --coverage-xml skills=skills/coverage.xml

    # move the bar up after an improvement
    python scripts/coverage_ratchet.py --measured agent-coordinator=74.5 ... --update

Exit codes
----------

    0  every suite is at or above (baseline - tolerance)
    1  at least one suite regressed beyond tolerance
    2  usage error, or a baseline that violates the contract schema
       (openspec/changes/introduce-fitness-function-gates/contracts/
        coverage-baseline.schema.json)

Validation is hand-rolled rather than jsonschema-driven so the script stays
stdlib-only and runnable from any venv; ``scripts/tests/test_coverage_ratchet.py``
cross-checks every rejection against the real contract schema, so the two
cannot drift apart silently.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = REPO_ROOT / "coverage-baseline.json"
SCRIPT_REF = "python scripts/coverage_ratchet.py"


class BaselineError(Exception):
    """The baseline file is absent, unparseable, or violates the contract."""


# ---------------------------------------------------------------------------
# Baseline I/O + contract validation
# ---------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineError(message)


def validate_baseline(payload: Any) -> dict[str, Any]:
    """Validate against contracts/coverage-baseline.schema.json (draft 2020-12)."""
    _require(isinstance(payload, dict), "coverage-baseline.json must be a JSON object")
    assert isinstance(payload, dict)  # narrowing for type checkers

    allowed_top = {"schema_version", "tolerance_pp", "updated_at", "updated_by", "suites"}
    extra = set(payload) - allowed_top
    _require(not extra, f"coverage-baseline.json has unknown key(s): {sorted(extra)}")

    for key in ("schema_version", "tolerance_pp", "suites"):
        _require(key in payload, f"coverage-baseline.json is missing required key '{key}'")

    _require(
        payload["schema_version"] == 1 and isinstance(payload["schema_version"], int),
        "coverage-baseline.json schema_version must be 1",
    )

    tolerance = payload["tolerance_pp"]
    _require(
        isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool),
        "coverage-baseline.json tolerance_pp must be a number",
    )
    _require(0 <= float(tolerance) <= 5, "coverage-baseline.json tolerance_pp must be 0..5")

    if "updated_by" in payload:
        updated_by = payload["updated_by"]
        _require(
            isinstance(updated_by, str) and 1 <= len(updated_by) <= 128,
            "coverage-baseline.json updated_by must be a 1..128 character string",
        )
    if "updated_at" in payload:
        _require(
            isinstance(payload["updated_at"], str),
            "coverage-baseline.json updated_at must be a date-time string",
        )

    suites = payload["suites"]
    _require(isinstance(suites, dict), "coverage-baseline.json suites must be an object")
    _require(bool(suites), "coverage-baseline.json suites must name at least one suite")

    for name, entry in suites.items():
        where = f"coverage-baseline.json suite '{name}'"
        _require(isinstance(entry, dict), f"{where} must be an object")
        entry_extra = set(entry) - {"line_coverage_pct", "command"}
        _require(not entry_extra, f"{where} has unknown key(s): {sorted(entry_extra)}")
        for key in ("line_coverage_pct", "command"):
            _require(key in entry, f"{where} is missing required key '{key}'")
        pct = entry["line_coverage_pct"]
        _require(
            isinstance(pct, (int, float)) and not isinstance(pct, bool),
            f"{where} line_coverage_pct must be a number",
        )
        _require(0 <= float(pct) <= 100, f"{where} line_coverage_pct must be 0..100")
        command = entry["command"]
        _require(
            isinstance(command, str) and command != "",
            f"{where} command must be a non-empty string",
        )

    return payload


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BaselineError(f"coverage-baseline.json not found at {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise BaselineError(f"coverage-baseline.json at {path} is not valid JSON: {exc}") from exc
    return validate_baseline(payload)


def write_baseline(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


# ---------------------------------------------------------------------------
# Measurement inputs
# ---------------------------------------------------------------------------


def parse_pair(raw: str, flag: str) -> tuple[str, str]:
    if "=" not in raw:
        raise BaselineError(f"{flag} expects NAME=VALUE, got {raw!r}")
    name, _, value = raw.partition("=")
    if not name or not value:
        raise BaselineError(f"{flag} expects NAME=VALUE, got {raw!r}")
    return name, value


def line_rate_from_xml(path: Path) -> float:
    """Read the overall line rate out of a Cobertura coverage.xml, as a percentage."""
    if not path.exists():
        raise BaselineError(f"coverage xml not found at {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise BaselineError(f"coverage xml at {path} is not parseable: {exc}") from exc
    rate = root.get("line-rate")
    if rate is None:
        raise BaselineError(f"coverage xml at {path} has no line-rate attribute")
    return float(rate) * 100.0


def collect_measured(args: argparse.Namespace) -> dict[str, float]:
    measured: dict[str, float] = {}
    for raw in args.measured or []:
        name, value = parse_pair(raw, "--measured")
        try:
            measured[name] = float(value)
        except ValueError as exc:
            raise BaselineError(f"--measured {raw!r} is not a number") from exc
    for raw in args.coverage_xml or []:
        name, value = parse_pair(raw, "--coverage-xml")
        measured[name] = line_rate_from_xml(Path(value))
    if not measured:
        raise BaselineError("no measurements given; pass --measured and/or --coverage-xml")
    return measured


# ---------------------------------------------------------------------------
# The ratchet
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coverage_ratchet.py",
        description="Fail when line coverage drops below the stored baseline.",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="path to coverage-baseline.json (default: repo root)",
    )
    parser.add_argument(
        "--measured",
        action="append",
        metavar="NAME=PCT",
        help="measured line coverage percentage for a suite (repeatable)",
    )
    parser.add_argument(
        "--coverage-xml",
        action="append",
        metavar="NAME=PATH",
        help="read a suite's line coverage from a Cobertura coverage.xml (repeatable)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline with any improved percentages (ratchet moves up only)",
    )
    parser.add_argument(
        "--updated-by",
        default=None,
        help="value recorded in the baseline's updated_by field when --update is used",
    )
    args = parser.parse_args(argv)

    baseline_path = Path(args.baseline)
    try:
        baseline = load_baseline(baseline_path)
        measured = collect_measured(args)
    except BaselineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    suites: dict[str, Any] = baseline["suites"]
    tolerance = float(baseline["tolerance_pp"])

    unknown = sorted(set(measured) - set(suites))
    if unknown:
        print(
            f"error: measured suite(s) not present in {baseline_path.name}: {unknown}",
            file=sys.stderr,
        )
        return 2
    missing = sorted(set(suites) - set(measured))
    if missing:
        print(
            f"error: no measurement given for baselined suite(s): {missing}",
            file=sys.stderr,
        )
        return 2

    print(f"coverage ratchet — baseline {baseline_path}, tolerance {tolerance:.2f}pp")

    regressions: list[str] = []
    improvements: list[str] = []
    for name in sorted(suites):
        before = float(suites[name]["line_coverage_pct"])
        now = measured[name]
        delta = now - before
        if delta < -tolerance:
            status = "REGRESSED"
            regressions.append(name)
        elif delta > 0:
            status = "IMPROVED"
            improvements.append(name)
        else:
            status = "ok"
        print(
            f"  {name}: baseline {before:.2f}% measured {now:.2f}% "
            f"({delta:+.2f}pp) {status}"
        )

    if args.update:
        for name in improvements:
            suites[name]["line_coverage_pct"] = round(measured[name], 2)
        baseline["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if args.updated_by:
            baseline["updated_by"] = args.updated_by
        write_baseline(baseline_path, baseline)
        if improvements:
            print(f"updated {baseline_path.name} for: {', '.join(sorted(improvements))}")
        else:
            print(f"no improvement to record; {baseline_path.name} percentages unchanged")

    if regressions:
        for name in regressions:
            before = float(suites[name]["line_coverage_pct"])
            print(
                f"::error::coverage regression in suite '{name}': "
                f"baseline {before:.2f}%, measured {measured[name]:.2f}% "
                f"({measured[name] - before:+.2f}pp, tolerance {tolerance:.2f}pp). "
                f"Command: {suites[name]['command']}",
                file=sys.stderr,
            )
        return 1

    if improvements and not args.update:
        pairs = " ".join(f"--measured {n}={measured[n]:.2f}" for n in sorted(measured))
        print(
            "coverage improved — move the ratchet up and commit the result:\n"
            f"  {SCRIPT_REF} {pairs} --update"
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
