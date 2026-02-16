#!/usr/bin/env python3
"""Flow tracer — infer cross-layer flows from the canonical architecture graph.

Chains Frontend→Backend→Service→Database paths via BFS to discover indirect
flows that span language boundaries (e.g. a React component that ultimately
touches a Postgres table through an API call, service function, and query).

Usage:
    python scripts/insights/flow_tracer.py --input-dir docs/architecture-analysis --output docs/architecture-analysis/cross_layer_flows.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import EdgeType  # noqa: E402
from arch_utils.traversal import build_adjacency  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Node = dict[str, Any]
Edge = dict[str, Any]
Entrypoint = dict[str, Any]


# ---------------------------------------------------------------------------
# Cross-layer flow inference
# ---------------------------------------------------------------------------


def infer_cross_layer_flows(
    all_nodes: list[Node],
    all_edges: list[Edge],
    entrypoints: list[Entrypoint],
) -> list[dict[str, Any]]:
    """Infer Frontend→Database indirect flows by chaining endpoint→service→query→table paths.

    For each cross-language API call edge, performs a BFS from the backend
    handler to discover all reachable database tables and intermediate service
    functions along the way.

    Parameters
    ----------
    all_nodes:
        All nodes from the canonical architecture graph.
    all_edges:
        All edges from the canonical architecture graph.
    entrypoints:
        Entrypoints from the canonical architecture graph.

    Returns
    -------
    List of flow dicts, each describing a frontend-to-database path.
    """
    flows: list[dict[str, Any]] = []
    node_map: dict[str, Node] = {n["id"]: n for n in all_nodes}
    adj = build_adjacency(all_edges)

    # Find cross-language API call edges
    cross_api_edges = [e for e in all_edges if e["type"] == EdgeType.API_CALL]

    for api_edge in cross_api_edges:
        frontend_id = api_edge["from"]
        backend_handler_id = api_edge["to"]
        frontend_node = node_map.get(frontend_id)
        backend_node = node_map.get(backend_handler_id)
        if frontend_node is None or backend_node is None:
            continue

        # BFS from backend handler to find all reachable db tables
        visited: set[str] = set()
        queue: deque[str] = deque([backend_handler_id])
        service_functions: list[str] = []
        db_tables: list[str] = []

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            current_node = node_map.get(current)
            if current_node is None:
                continue
            if current_node.get("kind") == "table":
                db_tables.append(current)
                continue
            if (current != backend_handler_id
                and current_node.get("language") == "python"
                and current_node.get("kind") in ("function", "class")):
                service_functions.append(current)
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        api_url = ""
        evidence = api_edge.get("evidence", "")
        match = re.search(r"(?:string_match|param_match|heuristic_match):([^~]+)", evidence)
        if match:
            api_url = match.group(1)

        flow: dict[str, Any] = {
            "frontend_component": frontend_id,
            "api_url": api_url,
            "backend_handler": backend_handler_id,
            "service_functions": service_functions,
            "db_tables": db_tables,
            "confidence": api_edge.get("confidence", "medium"),
        }
        flows.append(flow)
    return flows


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Infer cross-layer flows (Frontend→Database) from the architecture graph.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("docs/architecture-analysis"),
        help="Directory containing architecture.graph.json (default: docs/architecture-analysis)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/cross_layer_flows.json"),
        help="Output path for cross-layer flows JSON (default: docs/architecture-analysis/cross_layer_flows.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    graph_path = args.input_dir / "architecture.graph.json"
    if not graph_path.exists():
        logger.error(
            f"{graph_path} not found. Run the graph builder first."
        )
        return 1

    logger.info(f"Loading graph from {graph_path}...")
    with open(graph_path) as f:
        graph = json.load(f)

    all_nodes: list[Node] = graph.get("nodes", [])
    all_edges: list[Edge] = graph.get("edges", [])
    entrypoints: list[Entrypoint] = graph.get("entrypoints", [])

    logger.info(
        f"  {len(all_nodes)} nodes, {len(all_edges)} edges, "
        f"{len(entrypoints)} entrypoints"
    )

    flows = infer_cross_layer_flows(all_nodes, all_edges, entrypoints)

    output_data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flows": flows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    # Summary to stderr
    tables_touched = {t for flow in flows for t in flow["db_tables"]}
    logger.info(
        f"Flow tracing complete: {len(flows)} cross-layer flows found, "
        f"touching {len(tables_touched)} unique tables"
    )
    logger.info(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
