#!/usr/bin/env python3
"""Impact ranker -- identify high-impact nodes via reverse transitive closure.

Reads architecture.graph.json and finds the nodes with the most dependents
(i.e. the nodes that, if changed, would transitively affect the greatest
number of other nodes).

Usage:
    python scripts/insights/impact_ranker.py \
        --input-dir .architecture \
        --output .architecture/high_impact_nodes.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import DEPENDENCY_EDGE_TYPES  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Node = dict[str, Any]
Edge = dict[str, Any]


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------


def compute_high_impact_nodes(
    all_nodes: list[Node],
    all_edges: list[Edge],
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Return nodes whose reverse transitive dependent count meets *threshold*.

    For each node the algorithm builds a reverse-adjacency graph (edges that
    represent structural dependency are flipped) and then performs a BFS to
    count the full transitive set of dependents.  Only nodes with at least
    *threshold* dependents are included in the result.

    The returned list is sorted by ``dependent_count`` descending.
    """
    reverse_adj: dict[str, set[str]] = defaultdict(set)
    for edge in all_edges:
        if edge["type"] in DEPENDENCY_EDGE_TYPES:
            reverse_adj[edge["to"]].add(edge["from"])

    high_impact: list[dict[str, Any]] = []
    for node in all_nodes:
        nid = node["id"]
        if nid not in reverse_adj:
            continue
        visited: set[str] = set()
        queue: deque[str] = deque(reverse_adj[nid])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for dep in reverse_adj.get(current, set()):
                if dep not in visited:
                    queue.append(dep)
        if len(visited) >= threshold:
            high_impact.append({
                "id": nid,
                "dependent_count": len(visited),
            })

    high_impact.sort(key=lambda x: x["dependent_count"], reverse=True)
    return high_impact


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Rank architecture nodes by impact (reverse transitive dependent count)."
        ),
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
        default=Path(".architecture/high_impact_nodes.json"),
        help="Output path for high_impact_nodes.json (default: .architecture/high_impact_nodes.json)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Minimum number of dependents to be considered high-impact (default: 5)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    graph_path = args.input_dir / "architecture.graph.json"
    if not graph_path.exists():
        logger.error(f"{graph_path} not found.")
        return 1

    with open(graph_path) as f:
        graph = json.load(f)

    all_nodes: list[Node] = graph.get("nodes", [])
    all_edges: list[Edge] = graph.get("edges", [])

    high_impact = compute_high_impact_nodes(all_nodes, all_edges, threshold=args.threshold)

    output_data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": args.threshold,
        "total_nodes": len(all_nodes),
        "total_edges": len(all_edges),
        "high_impact_count": len(high_impact),
        "high_impact_nodes": high_impact,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)
        f.write("\n")

    # Summary to stderr
    logger.info(
        f"Impact analysis complete: {len(high_impact)} high-impact nodes "
        f"(threshold={args.threshold}) out of {len(all_nodes)} total nodes."
    )
    if high_impact:
        top = high_impact[:5]
        logger.info("Top nodes by dependent count:")
        for entry in top:
            logger.info(f"  {entry['id']}: {entry['dependent_count']} dependents")
    logger.info(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
