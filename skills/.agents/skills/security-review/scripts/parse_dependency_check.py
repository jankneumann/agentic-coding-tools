#!/usr/bin/env python3
"""Parse OWASP Dependency-Check JSON output into canonical findings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from models import Finding, ScannerResult, normalize_severity


def parse_report(payload: dict[str, Any]) -> ScannerResult:
    findings: list[Finding] = []
    dependencies = payload.get("dependencies", [])

    for dep in dependencies:
        location = dep.get("fileName") or dep.get("filePath") or ""
        vulns = dep.get("vulnerabilities") or []
        for idx, vuln in enumerate(vulns):
            vuln_id = str(vuln.get("name") or vuln.get("source") or f"dep-{idx}")
            severity = normalize_severity(vuln.get("severity"))
            title = vuln.get("name") or "Dependency vulnerability"
            description = vuln.get("description") or ""
            findings.append(
                Finding(
                    scanner="dependency-check",
                    finding_id=vuln_id,
                    title=title,
                    severity=severity,
                    description=description,
                    location=location,
                    metadata={
                        "package": dep.get("packages") or dep.get("packagePath"),
                        "cvssv2": vuln.get("cvssv2"),
                        "cvssv3": vuln.get("cvssv3"),
                        "references": vuln.get("references", []),
                    },
                )
            )

    return ScannerResult(
        scanner="dependency-check",
        status="ok",
        findings=findings,
        messages=[f"Parsed {len(findings)} findings"],
        metadata={"dependency_count": len(dependencies)},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to dependency-check JSON report")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        result = ScannerResult(
            scanner="dependency-check",
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
            scanner="dependency-check",
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
