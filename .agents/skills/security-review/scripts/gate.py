#!/usr/bin/env python3
"""Risk gate evaluation for /security-review normalized findings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from models import GateResult, normalize_severity, severity_rank


DEGRADED_STATUSES = {"unavailable", "error"}


def evaluate_gate(
    scanner_results: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    fail_on: str,
    allow_degraded_pass: bool,
) -> GateResult:
    """Compute PASS/FAIL/INCONCLUSIVE from findings and scanner execution state."""
    fail_on_norm = normalize_severity(fail_on)
    threshold = severity_rank(fail_on_norm)

    degraded = [
        result.get("scanner", "unknown")
        for result in scanner_results
        if result.get("status") in DEGRADED_STATUSES
    ]
    triggered = [
        finding
        for finding in findings
        if severity_rank(str(finding.get("severity", "info"))) >= threshold
    ]

    reasons: list[str] = []
    if degraded and not allow_degraded_pass:
        reasons.append(
            "Scanner execution incomplete: " + ", ".join(sorted(set(degraded)))
        )
        if triggered:
            reasons.append(
                "Threshold findings present but decision held INCONCLUSIVE due to incomplete coverage"
            )
        return GateResult(
            decision="INCONCLUSIVE",
            fail_on=fail_on_norm,
            triggered_count=len(triggered),
            reasons=reasons,
        )

    if triggered:
        reasons.append(
            f"{len(triggered)} finding(s) met or exceeded fail_on={fail_on_norm}"
        )
        return GateResult(
            decision="FAIL",
            fail_on=fail_on_norm,
            triggered_count=len(triggered),
            reasons=reasons,
        )

    if degraded and allow_degraded_pass:
        reasons.append(
            "Degraded execution allowed by policy; no threshold findings detected"
        )

    return GateResult(
        decision="PASS",
        fail_on=fail_on_norm,
        triggered_count=0,
        reasons=reasons,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", required=True, help="Aggregate JSON input")
    parser.add_argument(
        "--fail-on",
        choices=["info", "low", "medium", "high", "critical"],
        help="Override fail-on threshold",
    )
    parser.add_argument(
        "--allow-degraded-pass",
        action="store_true",
        help="Allow PASS when scanners are degraded and no threshold findings exist",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.aggregate).read_text(encoding="utf-8"))
    scanner_results = payload.get("scanner_results", [])
    findings = payload.get("findings", [])
    fail_on = args.fail_on or payload.get("fail_on", "high")

    result = evaluate_gate(
        scanner_results=scanner_results,
        findings=findings,
        fail_on=fail_on,
        allow_degraded_pass=args.allow_degraded_pass,
    )

    print(json.dumps(result.to_dict(), indent=2 if args.pretty else None))

    if result.decision == "PASS":
        return 0
    if result.decision == "FAIL":
        return 10
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
