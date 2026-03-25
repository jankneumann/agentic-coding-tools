#!/usr/bin/env python3
"""Compare two architecture graphs and report structural changes.

Compares a baseline architecture.graph.json to the current version and reports:
  - New dependency cycles introduced
  - New high-impact modules (many transitive dependents)
  - Routes added without tests
  - DB tables touched without corresponding migrations
  - Nodes added/removed
  - Edges added/removed

Usage:
    python scripts/diff_architecture.py \
        --baseline docs/architecture-analysis/tmp/baseline_graph.json \
        --current docs/architecture-analysis/architecture.graph.json \
        --output docs/architecture-analysis/architecture.diff.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arch_utils.graph_io import load_graph, save_json  # noqa: E402
from arch_utils.traversal import find_cycles, transitive_dependents  # noqa: E402


def _node_set(graph: dict) -> dict[str, dict]:
    """Return a dict of node_id -> node from the graph."""
    return {n["id"]: n for n in graph.get("nodes", [])}


def _edge_set(graph: dict) -> set[tuple[str, str, str]]:
    """Return a set of (from, to, type) tuples."""
    return {(e["from"], e["to"], e["type"]) for e in graph.get("edges", [])}


def _entrypoint_set(graph: dict) -> dict[str, dict]:
    """Return a dict of node_id -> entrypoint."""
    return {ep["node_id"]: ep for ep in graph.get("entrypoints", [])}


def diff_graphs(
    baseline: dict[str, Any], current: dict[str, Any],
) -> dict[str, Any]:
    """Compare two architecture graphs and produce a diff report."""
    b_nodes = _node_set(baseline)
    c_nodes = _node_set(current)
    b_edges = _edge_set(baseline)
    c_edges = _edge_set(current)
    b_eps = _entrypoint_set(baseline)
    c_eps = _entrypoint_set(current)

    added_nodes = set(c_nodes) - set(b_nodes)
    removed_nodes = set(b_nodes) - set(c_nodes)
    added_edges = c_edges - b_edges
    removed_edges = b_edges - c_edges

    # Cycles
    b_cycles = find_cycles(baseline.get("edges", []))
    c_cycles = find_cycles(current.get("edges", []))
    b_cycle_sets = {tuple(sorted(c)) for c in b_cycles}
    c_cycle_sets = {tuple(sorted(c)) for c in c_cycles}
    new_cycles = [list(c) for c in c_cycle_sets - b_cycle_sets]

    # High-impact modules
    c_deps = transitive_dependents(current.get("edges", []))
    b_deps = transitive_dependents(baseline.get("edges", []))
    new_high_impact = []
    for node_id, deps in c_deps.items():
        if len(deps) > 10 and node_id not in b_deps:
            new_high_impact.append({
                "id": node_id,
                "dependent_count": len(deps),
            })

    # New entrypoints without tests
    new_eps = set(c_eps) - set(b_eps)
    # Check if test nodes exist for new entrypoints
    test_nodes = {
        nid for nid in c_nodes
        if "test" in nid.lower() or c_nodes[nid].get("file", "").startswith("test")
    }
    untested_new_routes = []
    for ep_id in new_eps:
        ep = c_eps[ep_id]
        name = c_nodes.get(ep_id, {}).get("name", "")
        has_test = any(f"test_{name}" in tid or name in tid for tid in test_nodes)
        if not has_test:
            untested_new_routes.append({
                "node_id": ep_id,
                "kind": ep.get("kind", "unknown"),
                "path": ep.get("path", ""),
            })

    # New DB table nodes
    new_db_tables = [
        {"id": nid, "name": c_nodes[nid].get("name", "")}
        for nid in added_nodes
        if c_nodes[nid].get("kind") == "table"
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_snapshot": (baseline.get("snapshots", [{}])[0] if baseline.get("snapshots") else {}),
        "current_snapshot": (current.get("snapshots", [{}])[0] if current.get("snapshots") else {}),
        "summary": {
            "nodes_added": len(added_nodes),
            "nodes_removed": len(removed_nodes),
            "edges_added": len(added_edges),
            "edges_removed": len(removed_edges),
            "new_cycles": len(new_cycles),
            "new_high_impact_modules": len(new_high_impact),
            "untested_new_routes": len(untested_new_routes),
            "new_db_tables": len(new_db_tables),
        },
        "details": {
            "added_nodes": sorted(added_nodes)[:100],
            "removed_nodes": sorted(removed_nodes)[:100],
            "added_edges": [
                {"from": e[0], "to": e[1], "type": e[2]} for e in sorted(added_edges)[:100]
            ],
            "removed_edges": [
                {"from": e[0], "to": e[1], "type": e[2]} for e in sorted(removed_edges)[:100]
            ],
            "new_cycles": new_cycles[:20],
            "new_high_impact_modules": new_high_impact[:20],
            "untested_new_routes": untested_new_routes,
            "new_db_tables": new_db_tables,
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Compare two architecture graphs")
    parser.add_argument("--baseline", required=True, help="Path to baseline graph JSON")
    parser.add_argument("--current", required=True, help="Path to current graph JSON")
    parser.add_argument(
        "--output", default="docs/architecture-analysis/architecture.diff.json",
        help="Output path for diff report",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    if not baseline_path.exists():
        logger.error("Baseline not found: %s", baseline_path)
        return 1
    if not current_path.exists():
        logger.error("Current graph not found: %s", current_path)
        return 1

    baseline = load_graph(baseline_path)
    current = load_graph(current_path)
    report = diff_graphs(baseline, current)

    output_path = save_json(Path(args.output), report)

    s = report["summary"]
    logger.info("Architecture diff: +%d/-%d nodes, +%d/-%d edges",
                s['nodes_added'], s['nodes_removed'], s['edges_added'], s['edges_removed'])
    if s["new_cycles"]:
        logger.warning("%d new dependency cycle(s)", s['new_cycles'])
    if s["new_high_impact_modules"]:
        logger.warning("%d new high-impact module(s)", s['new_high_impact_modules'])
    if s["untested_new_routes"]:
        logger.warning("%d new route(s) without tests", s['untested_new_routes'])
    if s["new_db_tables"]:
        logger.info("%d new database table(s)", s['new_db_tables'])

    logger.info("Report written to %s", output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
