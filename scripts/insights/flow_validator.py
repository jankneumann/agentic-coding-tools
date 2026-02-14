#!/usr/bin/env python3
"""Flow validator insight module — thin wrapper around validate_flows.py.

Checks reachability, test coverage alignment, disconnected flows, orphaned code,
and pattern consistency by consuming architecture.graph.json.

This module delegates to the existing validate_flows logic but conforms to the
Layer 2 insight module interface (--input-dir / --output).

Usage:
    python scripts/insights/flow_validator.py --input-dir .architecture --output .architecture/architecture.diagnostics.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_flows import validate_flows  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Flow validator: reachability, test coverage, orphans, and pattern consistency.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing architecture.graph.json (default: .architecture)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/architecture.diagnostics.json"),
        help="Output path for diagnostics JSON (default: .architecture/architecture.diagnostics.json)",
    )
    parser.add_argument(
        "--files",
        type=str,
        default=None,
        help="Comma-separated list of files to scope validation to",
    )
    parser.add_argument(
        "--diff",
        type=str,
        default=None,
        help='Git diff spec to resolve changed files (e.g., "main...HEAD")',
    )
    parser.add_argument(
        "--glob",
        type=str,
        default=None,
        help='Glob pattern to match changed files (e.g., "src/**/*.py")',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    graph_path = args.input_dir / "architecture.graph.json"

    if not graph_path.exists():
        logger.error(f"graph file not found: {graph_path}")
        return 1

    # Import the scope resolver from validate_flows
    from validate_flows import _resolve_changed_files  # noqa: E402

    changed_files = _resolve_changed_files(args.files, args.diff, args.glob)

    report = validate_flows(graph_path, args.output, changed_files)

    summary = report["summary"]
    scope_label = f" (scope: {len(report['changed_files'])} files)" if report["scope"] == "changed" else ""
    logger.info(f"Flow validation complete{scope_label}.")
    logger.info(f"  Entrypoints checked: {summary['entrypoints_checked']}")
    logger.info(f"  Flows with test coverage: {summary['flows_with_coverage']}")
    logger.info(f"  Flows without test coverage: {summary['flows_without_coverage']}")
    logger.info(f"  Findings: {summary['total_findings']} total "
               f"({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info)")
    logger.info(f"  Output: {args.output}")

    if summary["errors"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
