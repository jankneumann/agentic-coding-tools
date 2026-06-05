"""Run structural architecture linters and output review-findings JSON.

This script is invoked by the validate-feature --phase=architecture pipeline.
It discovers changed files (via git diff or a passed list), runs all structural
linters, and outputs findings in review-findings JSON format.

Exit codes:
    0 — No critical or high findings
    1 — Critical or high findings detected

Usage:
    python run_architecture_linters.py [--files FILE1,FILE2,...] [--max-lines N] [--target ID] [--base-ref REF]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Add scripts dir to path for linters import
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from linters import run_all_linters


def _discover_changed_files(base_ref: str = "main") -> list[str]:
    """Discover changed files via git diff against a base ref.

    Args:
        base_ref: Git ref to diff against (default: main).

    Returns:
        List of changed file paths relative to the repo root.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
        return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _has_blocking_findings(findings: list[dict]) -> bool:
    """Check if any findings are critical or high severity."""
    blocking = {"critical", "high"}
    return any(f.get("criticality") in blocking for f in findings)


def main() -> None:
    """CLI entry point for running architecture linters."""
    parser = argparse.ArgumentParser(
        description="Run structural architecture linters on changed files.",
    )
    parser.add_argument(
        "--files",
        help="Comma-separated list of files to check (default: discover via git diff)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=500,
        help="Maximum file line count (default: 500)",
    )
    parser.add_argument(
        "--target",
        default="wp-architecture-linters",
        help="Target identifier for the review-findings output",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Git ref to diff against for file discovery (default: main)",
    )
    args = parser.parse_args()

    # Discover or parse file list
    if args.files:
        changed_files = [f.strip() for f in args.files.split(",") if f.strip()]
    else:
        changed_files = _discover_changed_files(args.base_ref)

    if not changed_files:
        # No files to check — output clean result
        result = {
            "review_type": "implementation",
            "target": args.target,
            "reviewer_vendor": "structural-linter",
            "findings": [],
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # Run all linters
    config = {
        "max_lines": args.max_lines,
        "target": args.target,
    }
    result = run_all_linters(changed_files, config=config)

    # Output JSON
    print(json.dumps(result, indent=2))

    # Summary to stderr
    finding_count = len(result["findings"])
    if finding_count == 0:
        print("Architecture linters: PASS — no findings", file=sys.stderr)
    else:
        criticalities = {}
        for f in result["findings"]:
            c = f.get("criticality", "unknown")
            criticalities[c] = criticalities.get(c, 0) + 1
        summary_parts = [f"{v} {k}" for k, v in sorted(criticalities.items())]
        print(
            f"Architecture linters: {finding_count} finding(s) "
            f"({', '.join(summary_parts)})",
            file=sys.stderr,
        )

    # Exit 1 if blocking findings exist
    if _has_blocking_findings(result["findings"]):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
