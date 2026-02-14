#!/usr/bin/env python3
"""Summary builder -- produce architecture.summary.json from Layer 2 artifacts.

Reads the canonical architecture graph, cross-layer flows, and high-impact
node data, then builds a compact summary with adaptive confidence threshold
for flow selection.

Usage:
    python scripts/insights/summary_builder.py --input-dir .architecture --output .architecture/architecture.summary.json
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import EdgeType  # noqa: E402
from arch_utils.graph_io import load_graph, save_json  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Graph = dict[str, Any]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def get_git_sha() -> str:
    """Obtain the current HEAD git SHA, returning 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Disconnected endpoint / frontend call detection
# ---------------------------------------------------------------------------


def find_disconnected_endpoints(
    graph: Graph,
) -> list[dict[str, str]]:
    """Find route entrypoints that are NOT the target of any api_call edge.

    These represent backend endpoints that no frontend component calls.
    """
    # Collect all node IDs that are targets of api_call edges
    api_call_targets: set[str] = set()
    for edge in graph.get("edges", []):
        if edge.get("type") == EdgeType.API_CALL:
            api_call_targets.add(edge["to"])

    disconnected: list[dict[str, str]] = []
    for ep in graph.get("entrypoints", []):
        if ep.get("kind") == "route" and ep["node_id"] not in api_call_targets:
            disconnected.append({
                "node_id": ep["node_id"],
                "path": ep.get("path", ""),
            })
    return disconnected


def find_disconnected_frontend_calls(
    graph: Graph,
) -> list[dict[str, str]]:
    """Find api_call edges whose target node doesn't exist in the graph.

    These represent frontend API calls that point to non-existent or
    unresolved backend handlers.
    """
    node_ids: set[str] = {n["id"] for n in graph.get("nodes", [])}

    disconnected: list[dict[str, str]] = []
    for edge in graph.get("edges", []):
        if edge.get("type") == EdgeType.API_CALL and edge["to"] not in node_ids:
            disconnected.append({
                "node_id": edge["from"],
                "url": edge.get("evidence", ""),
            })
    return disconnected


# ---------------------------------------------------------------------------
# Summary generation with adaptive confidence threshold
# ---------------------------------------------------------------------------


def generate_summary(
    graph: Graph,
    flows: list[dict[str, Any]],
    disconnected_endpoints: list[dict[str, str]],
    disconnected_frontend_calls: list[dict[str, str]],
    high_impact_nodes: list[dict[str, Any]],
    summary_limit: int,
    git_sha: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build architecture.summary.json with adaptive confidence threshold."""
    nodes = graph["nodes"]
    edges = graph["edges"]

    # Stats
    by_language: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    for node in nodes:
        by_language[node.get("language", "unknown")] += 1
        by_kind[node.get("kind", "unknown")] += 1

    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "by_language": dict(by_language),
        "by_kind": dict(by_kind),
        "entrypoint_count": len(graph["entrypoints"]),
    }

    # Adaptive confidence threshold for flows
    high_flows = [f for f in flows if f.get("confidence") == "high"]
    medium_flows = [f for f in flows if f.get("confidence") == "medium"]
    low_flows = [f for f in flows if f.get("confidence") == "low"]

    selected_flows: list[dict[str, Any]] = list(high_flows)
    remaining = summary_limit - len(selected_flows)

    if remaining > 0:
        selected_flows.extend(medium_flows[:remaining])
        remaining = summary_limit - len(selected_flows)

    if remaining > 0:
        selected_flows.extend(low_flows[:remaining])

    return {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "stats": stats,
        "cross_layer_flows": selected_flows,
        "disconnected_endpoints": disconnected_endpoints,
        "disconnected_frontend_calls": disconnected_frontend_calls,
        "high_impact_nodes": high_impact_nodes,
    }


# ---------------------------------------------------------------------------
# File loading helpers
# ---------------------------------------------------------------------------


def load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    """Load a JSON file expected to contain a list, returning [] if missing."""
    if not path.exists():
        logger.info(f"  [skip] {label}: {path.name} not found")
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            logger.info(f"  [ok]   {label}: {len(data)} items")
            return data
        # Some files wrap the list under a key (e.g. {"flows": [...]})
        # Try common keys
        for key in ("flows", "nodes", "items"):
            if isinstance(data.get(key), list):
                items = data[key]
                logger.info(f"  [ok]   {label}: {len(items)} items (from .{key})")
                return items
        logger.warning(f"  [warn] {label}: unexpected format, using empty list")
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"  [warn] {label}: {exc}")
        return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Build architecture.summary.json from graph and Layer 2 insights.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing architecture artifacts (default: .architecture)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/architecture.summary.json"),
        help="Output path for the summary (default: .architecture/architecture.summary.json)",
    )
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=50,
        help="Maximum number of cross-layer flows to include (default: 50)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    input_dir: Path = args.input_dir
    output_path: Path = args.output
    summary_limit: int = args.summary_limit

    # --- Load the canonical graph ---
    logger.info("Loading architecture graph...")
    graph = load_graph(input_dir / "architecture.graph.json")
    if not graph:
        logger.error("Could not load architecture.graph.json")
        return 1

    # Ensure required keys exist
    graph.setdefault("nodes", [])
    graph.setdefault("edges", [])
    graph.setdefault("entrypoints", [])

    # --- Extract snapshot info ---
    snapshots = graph.get("snapshots", [])
    if snapshots:
        latest_snapshot = snapshots[-1]
        git_sha = latest_snapshot.get("git_sha", get_git_sha())
    else:
        git_sha = get_git_sha()
    generated_at = datetime.now(timezone.utc).isoformat()

    # --- Load Layer 2 artifacts ---
    logger.info("Loading Layer 2 artifacts...")
    flows = load_json_list(input_dir / "cross_layer_flows.json", "cross_layer_flows")
    high_impact_nodes = load_json_list(input_dir / "high_impact_nodes.json", "high_impact_nodes")

    # --- Compute disconnected info from the graph ---
    logger.info("Computing disconnected endpoint info...")

    # Check for a pre-computed disconnected_info.json first
    disconnected_info_path = input_dir / "disconnected_info.json"
    if disconnected_info_path.exists():
        try:
            with open(disconnected_info_path) as f:
                disconnected_info = json.load(f)
            disconnected_endpoints = disconnected_info.get("disconnected_endpoints", [])
            disconnected_frontend_calls = disconnected_info.get("disconnected_frontend_calls", [])
            logger.info(
                f"  [ok]   disconnected_info: "
                f"{len(disconnected_endpoints)} endpoints, "
                f"{len(disconnected_frontend_calls)} frontend calls"
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"  [warn] disconnected_info.json: {exc}, computing from graph")
            disconnected_endpoints = find_disconnected_endpoints(graph)
            disconnected_frontend_calls = find_disconnected_frontend_calls(graph)
    else:
        disconnected_endpoints = find_disconnected_endpoints(graph)
        disconnected_frontend_calls = find_disconnected_frontend_calls(graph)
        logger.info(
            f"  [ok]   computed: "
            f"{len(disconnected_endpoints)} disconnected endpoints, "
            f"{len(disconnected_frontend_calls)} disconnected frontend calls"
        )

    # --- Generate summary ---
    logger.info("Generating summary...")
    summary = generate_summary(
        graph=graph,
        flows=flows,
        disconnected_endpoints=disconnected_endpoints,
        disconnected_frontend_calls=disconnected_frontend_calls,
        high_impact_nodes=high_impact_nodes,
        summary_limit=summary_limit,
        git_sha=git_sha,
        generated_at=generated_at,
    )

    # --- Write output ---
    out = save_json(output_path, summary)
    logger.info(f"Wrote {out}")

    # --- Print summary stats to stderr ---
    stats = summary["stats"]
    logger.info(
        f"Summary: "
        f"{stats['total_nodes']} nodes, "
        f"{stats['total_edges']} edges, "
        f"{stats['entrypoint_count']} entrypoints"
    )
    logger.info(
        f"  Flows included: {len(summary['cross_layer_flows'])} "
        f"(limit: {summary_limit})"
    )
    if disconnected_endpoints:
        logger.info(
            f"  Disconnected backend endpoints: {len(disconnected_endpoints)}"
        )
    if disconnected_frontend_calls:
        logger.info(
            f"  Disconnected frontend calls: {len(disconnected_frontend_calls)}"
        )
    if high_impact_nodes:
        logger.info(
            f"  High-impact nodes: {len(high_impact_nodes)}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
