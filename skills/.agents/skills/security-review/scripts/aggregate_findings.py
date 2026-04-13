#!/usr/bin/env python3
"""Aggregate normalized scanner outputs into canonical security-review payload."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import normalize_severity, severity_rank


def aggregate(
    scanner_payloads: list[dict[str, Any]],
    fail_on: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate scanner payloads into summary counts and deduplicated findings."""
    findings: list[dict[str, Any]] = []
    scanner_results: list[dict[str, Any]] = []
    dedupe: set[tuple[str, str, str, str]] = set()

    for payload in scanner_payloads:
        scanner_results.append(payload)
        for finding in payload.get("findings", []):
            normalized = {**finding, "severity": normalize_severity(finding.get("severity"))}
            key = (
                str(normalized.get("scanner", "")),
                str(normalized.get("finding_id", "")),
                str(normalized.get("title", "")),
                str(normalized.get("location", "")),
            )
            if key in dedupe:
                continue
            dedupe.add(key)
            findings.append(normalized)

    findings.sort(
        key=lambda item: (
            -severity_rank(str(item.get("severity", "info"))),
            str(item.get("scanner", "")),
            str(item.get("title", "")),
        )
    )

    counts = Counter(str(finding.get("severity", "info")) for finding in findings)
    by_severity = {
        "info": counts.get("info", 0),
        "low": counts.get("low", 0),
        "medium": counts.get("medium", 0),
        "high": counts.get("high", 0),
        "critical": counts.get("critical", 0),
    }

    if profile is None:
        profile = {
            "primary_profile": "unknown",
            "profiles": ["unknown"],
            "confidence": "low",
            "signals": [],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "fail_on": normalize_severity(fail_on),
        "scanner_results": scanner_results,
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_severity": by_severity,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Scanner result JSON file (repeatable)",
    )
    parser.add_argument("--profile-json", help="Profile JSON file")
    parser.add_argument(
        "--fail-on",
        choices=["info", "low", "medium", "high", "critical"],
        default="high",
        help="Severity threshold for fail gate",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payloads = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in args.input
    ]
    profile = None
    if args.profile_json:
        profile = json.loads(Path(args.profile_json).read_text(encoding="utf-8"))

    output = aggregate(payloads, fail_on=args.fail_on, profile=profile)
    print(json.dumps(output, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
