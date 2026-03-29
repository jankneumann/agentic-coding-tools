#!/usr/bin/env python3
"""Parse OWASP ZAP JSON report into canonical findings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from models import Finding, ScannerResult, normalize_severity

RISK_CODE_MAP = {
    "0": "info",
    "1": "low",
    "2": "medium",
    "3": "high",
    "4": "critical",
}


def _severity_from_alert(alert: dict[str, Any]) -> str:
    risk_code = str(alert.get("riskcode", "")).strip()
    if risk_code in RISK_CODE_MAP:
        return RISK_CODE_MAP[risk_code]

    risk_desc = str(alert.get("riskdesc", "")).split(" ")[0].strip("()")
    return normalize_severity(risk_desc)


def parse_report(payload: dict[str, Any]) -> ScannerResult:
    findings: list[Finding] = []
    site_entries = payload.get("site", [])

    for site in site_entries:
        alerts = site.get("alerts", [])
        for idx, alert in enumerate(alerts):
            plugin_id = str(alert.get("pluginid") or f"zap-{idx}")
            instances = alert.get("instances", [])
            first_instance = instances[0] if instances else {}
            location = (
                first_instance.get("uri")
                or first_instance.get("endpoint")
                or site.get("name")
                or ""
            )

            findings.append(
                Finding(
                    scanner="zap",
                    finding_id=plugin_id,
                    title=str(alert.get("name") or "ZAP alert"),
                    severity=normalize_severity(_severity_from_alert(alert)),
                    description=str(alert.get("desc") or ""),
                    location=location,
                    metadata={
                        "confidence": alert.get("confidence"),
                        "solution": alert.get("solution"),
                        "reference": alert.get("reference"),
                        "instances": instances,
                    },
                )
            )

    return ScannerResult(
        scanner="zap",
        status="ok",
        findings=findings,
        messages=[f"Parsed {len(findings)} findings"],
        metadata={"site_count": len(site_entries)},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to ZAP JSON report")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        result = ScannerResult(
            scanner="zap",
            status="error",
            findings=[],
            messages=[f"Report not found: {input_path}"],
        )
        print(json.dumps(result.to_dict(), indent=2 if args.pretty else None))
        return 1

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result = ScannerResult(
            scanner="zap",
            status="error",
            findings=[],
            messages=[f"Invalid JSON: {exc}"],
        )
        print(json.dumps(result.to_dict(), indent=2 if args.pretty else None))
        return 1

    result = parse_report(payload)
    print(json.dumps(result.to_dict(), indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
