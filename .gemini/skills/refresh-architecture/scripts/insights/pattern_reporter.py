#!/usr/bin/env python3
"""Pattern reporter insight module — aggregates pattern query findings.

Layer 2 module that reads treesitter_enrichment.json and produces
pattern_insights.json with per-module pattern counts, type hint coverage,
security findings by severity, and exception handling summary.

Usage:
    python scripts/insights/pattern_reporter.py \
        --input-dir docs/architecture-analysis \
        --output docs/architecture-analysis/pattern_insights.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def compute_pattern_insights(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Compute pattern insights from enrichment data."""
    py_patterns = enrichment.get("python_patterns", {})
    ts_patterns = enrichment.get("typescript_patterns", {})
    security = enrichment.get("security_patterns", {})

    # --- Python patterns ---
    py_summary = {}
    for category, data in py_patterns.items():
        items = data.get("items", [])
        py_summary[category] = {
            "count": data.get("count", len(items)),
            "files": _count_by_file(items),
        }

    # Type hint coverage
    type_hints = py_patterns.get("type_hints", {}).get("items", [])
    functions_with_return_type = len({
        (h["file"], h.get("function", ""))
        for h in type_hints
        if h.get("kind") == "return_type"
    })
    typed_params = len([h for h in type_hints if h.get("kind") == "param_type"])

    # Exception handling summary
    bare_except_count = py_patterns.get("bare_except", {}).get("count", 0)
    broad_except_count = py_patterns.get("broad_except", {}).get("count", 0)

    # --- TypeScript patterns ---
    ts_summary = {}
    for category, data in ts_patterns.items():
        items = data.get("items", [])
        ts_summary[category] = {
            "count": data.get("count", len(items)),
            "files": _count_by_file(items),
        }

    # --- Security findings ---
    security_items = security.get("items", [])
    security_by_category: dict[str, list[dict[str, Any]]] = {}
    for finding in security_items:
        cat = finding.get("category", "unknown")
        security_by_category.setdefault(cat, []).append(finding)

    security_summary = {
        "total": security.get("total", len(security_items)),
        "by_severity": security.get("by_severity", {}),
        "by_category": {
            cat: {
                "count": len(items),
                "severity": items[0].get("severity", "unknown") if items else "unknown",
                "files": _count_by_file(items),
            }
            for cat, items in security_by_category.items()
        },
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_patterns": py_summary,
        "typescript_patterns": ts_summary,
        "type_hint_coverage": {
            "functions_with_return_type": functions_with_return_type,
            "typed_parameters": typed_params,
        },
        "exception_handling": {
            "bare_except": bare_except_count,
            "broad_except": broad_except_count,
            "total_except_issues": bare_except_count + broad_except_count,
        },
        "security": security_summary,
    }


def _count_by_file(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count items per file."""
    counter: Counter[str] = Counter()
    for item in items:
        counter[item.get("file", "unknown")] += 1
    return dict(counter.most_common(20))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pattern reporter — aggregates pattern query findings.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("docs/architecture-analysis"),
        help="Directory containing treesitter_enrichment.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/pattern_insights.json"),
        help="Output path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    enrichment_path = args.input_dir / "treesitter_enrichment.json"
    if not enrichment_path.exists():
        logger.info("No treesitter_enrichment.json found — skipping pattern reporter.")
        return 0

    with open(enrichment_path) as f:
        enrichment = json.load(f)

    insights = compute_pattern_insights(enrichment)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(insights, f, indent=2)
        f.write("\n")

    logger.info(
        "Pattern insights: %d Python patterns, %d TypeScript patterns, %d security findings",
        sum(v["count"] for v in insights["python_patterns"].values()),
        sum(v["count"] for v in insights["typescript_patterns"].values()),
        insights["security"]["total"],
    )
    logger.info("Wrote %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
