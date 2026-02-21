#!/usr/bin/env python3
"""Render canonical JSON and markdown reports for /security-review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from schema import validate_report


def _render_markdown(report: dict[str, Any], run_context: dict[str, str]) -> str:
    gate = report.get("gate", {})
    summary = report.get("summary", {})
    by_severity = summary.get("by_severity", {})
    profile = report.get("profile", {})

    lines = [
        "# Security Review Report",
        "",
        "## Run Context",
        "",
    ]

    if run_context.get("change_id"):
        lines.append(f"- Change ID: `{run_context['change_id']}`")
    if run_context.get("commit_sha"):
        # Keep this line format stable for validate-feature staleness checks.
        lines.append(f"- Commit SHA: {run_context['commit_sha']}")
    if run_context.get("timestamp"):
        lines.append(f"- Timestamp: {run_context['timestamp']}")

    lines.extend(
        [
            f"- Profile: `{profile.get('primary_profile', 'unknown')}`",
            f"- Confidence: `{profile.get('confidence', 'low')}`",
            "",
            "## Gate Summary",
            "",
        ]
    )

    lines.extend(
        [
            f"- Decision: **{gate.get('decision', 'INCONCLUSIVE')}**",
            f"- Fail threshold: `{gate.get('fail_on', 'high')}`",
            f"- Triggered findings: `{gate.get('triggered_count', 0)}`",
            "",
            "## Scanner Results",
            "",
            "| Scanner | Status | Notes |",
            "|---|---|---|",
        ]
    )

    for result in report.get("scanner_results", []):
        notes = "; ".join(result.get("messages", []))
        lines.append(
            f"| {result.get('scanner', 'unknown')} | {result.get('status', 'unknown')} | {notes} |"
        )

    lines.extend(
        [
            "",
            "## Severity Summary",
            "",
            f"- Total findings: `{summary.get('total_findings', 0)}`",
            f"- Critical: `{by_severity.get('critical', 0)}`",
            f"- High: `{by_severity.get('high', 0)}`",
            f"- Medium: `{by_severity.get('medium', 0)}`",
            f"- Low: `{by_severity.get('low', 0)}`",
            f"- Info: `{by_severity.get('info', 0)}`",
            "",
            "## Gate Reasons",
            "",
        ]
    )

    reasons = gate.get("reasons", [])
    if not reasons:
        lines.append("- No gate reasons provided")
    else:
        lines.extend([f"- {reason}" for reason in reasons])

    lines.extend(["", "## Top Findings", ""])
    findings = report.get("findings", [])[:20]
    if not findings:
        lines.append("- No findings")
    else:
        for finding in findings:
            lines.append(
                "- "
                f"`[{finding.get('severity', 'info').upper()}]` "
                f"{finding.get('scanner', 'unknown')} :: {finding.get('title', 'Untitled')} "
                f"({finding.get('location', 'n/a')})"
            )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", required=True, help="Aggregate JSON file")
    parser.add_argument("--gate", required=True, help="Gate JSON file")
    parser.add_argument(
        "--json-out",
        required=True,
        help="Output path for canonical JSON report",
    )
    parser.add_argument(
        "--md-out",
        required=True,
        help="Output path for markdown summary",
    )
    parser.add_argument("--change-id", default="", help="Optional OpenSpec change-id")
    parser.add_argument("--commit-sha", default="", help="Commit SHA associated with this run")
    parser.add_argument("--timestamp", default="", help="Run timestamp (ISO-8601)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    aggregate = json.loads(Path(args.aggregate).read_text(encoding="utf-8"))
    gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))

    run_context = {
        "change_id": args.change_id,
        "commit_sha": args.commit_sha,
        "timestamp": args.timestamp,
    }

    report = {
        **aggregate,
        "gate": gate,
        "run_context": run_context,
    }

    validate_report(report)

    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)

    json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_out.write_text(_render_markdown(report, run_context), encoding="utf-8")

    print(json.dumps({
        "json_report": str(json_out),
        "markdown_report": str(md_out),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
