#!/usr/bin/env python3
"""Comment linker insight module — maps comments/TODOs to architecture graph nodes.

Layer 2 module that reads treesitter_enrichment.json and architecture.graph.json
to produce comment_insights.json with TODO/FIXME counts per module, documentation
coverage metrics, and marker hotspot identification.

Usage:
    python scripts/insights/comment_linker.py \
        --input-dir docs/architecture-analysis \
        --output docs/architecture-analysis/comment_insights.json
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


def compute_comment_insights(
    enrichment: dict[str, Any],
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute comment insights from enrichment data."""
    comments = enrichment.get("comments", {}).get("items", [])

    # Group by file
    by_file: dict[str, list[dict[str, Any]]] = {}
    for comment in comments:
        by_file.setdefault(comment["file"], []).append(comment)

    # Marker counts per file
    marker_counts: dict[str, Counter[str]] = {}
    total_markers: Counter[str] = Counter()
    for file_path, file_comments in by_file.items():
        file_markers: Counter[str] = Counter()
        for c in file_comments:
            for m in c.get("markers", []):
                file_markers[m] += 1
                total_markers[m] += 1
        if file_markers:
            marker_counts[file_path] = file_markers

    # Marker hotspots (files with most markers)
    hotspots = sorted(
        [
            {
                "file": f,
                "total_markers": sum(counts.values()),
                "markers": dict(counts),
            }
            for f, counts in marker_counts.items()
        ],
        key=lambda x: x["total_markers"],
        reverse=True,
    )

    # Per-node comment associations
    node_comments: dict[str, int] = Counter()
    node_markers: dict[str, list[str]] = {}
    for comment in comments:
        node_id = comment.get("enclosing_node")
        if node_id:
            node_comments[node_id] += 1
            for m in comment.get("markers", []):
                node_markers.setdefault(node_id, []).append(m)

    # Documentation coverage (nodes with at least one comment)
    total_nodes = len(graph.get("nodes", [])) if graph else 0
    documented_nodes = len(node_comments)

    # Per-file summary
    file_summaries = []
    for file_path in sorted(by_file.keys()):
        fc = by_file[file_path]
        file_summaries.append({
            "file": file_path,
            "total_comments": len(fc),
            "with_markers": sum(1 for c in fc if c.get("markers")),
            "languages": list({c["language"] for c in fc}),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_comments": len(comments),
            "total_with_markers": sum(1 for c in comments if c.get("markers")),
            "marker_totals": dict(total_markers),
            "total_graph_nodes": total_nodes,
            "documented_nodes": documented_nodes,
            "documentation_coverage": (
                round(documented_nodes / total_nodes, 3) if total_nodes else 0
            ),
        },
        "marker_hotspots": hotspots[:20],
        "node_marker_map": {
            nid: {"comment_count": node_comments[nid], "markers": markers}
            for nid, markers in node_markers.items()
        },
        "file_summaries": file_summaries,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comment linker — maps comments/TODOs to architecture nodes.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("docs/architecture-analysis"),
        help="Directory containing enrichment and graph files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/comment_insights.json"),
        help="Output path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    enrichment_path = args.input_dir / "treesitter_enrichment.json"
    graph_path = args.input_dir / "architecture.graph.json"

    if not enrichment_path.exists():
        logger.info("No treesitter_enrichment.json found — skipping comment linker.")
        return 0

    with open(enrichment_path) as f:
        enrichment = json.load(f)

    graph = None
    if graph_path.exists():
        with open(graph_path) as f:
            graph = json.load(f)

    insights = compute_comment_insights(enrichment, graph)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(insights, f, indent=2)
        f.write("\n")

    logger.info(
        "Comment insights: %d comments, %d with markers, %.1f%% node coverage",
        insights["summary"]["total_comments"],
        insights["summary"]["total_with_markers"],
        insights["summary"]["documentation_coverage"] * 100,
    )
    logger.info("Wrote %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
