#!/usr/bin/env python3
"""Cross-language linker — match frontend API calls to backend route endpoints.

Reads an existing architecture.graph.json and optionally ts_analysis.json,
performs 3-pass frontend-to-backend URL matching (exact, parameterized,
heuristic), appends cross-language api_call edges, and writes the updated
graph back.

Usage:
    python scripts/insights/cross_layer_linker.py \
        --input-dir .architecture \
        --output .architecture/architecture.graph.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup for sibling package imports
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arch_utils.constants import EdgeType  # noqa: E402
from arch_utils.node_id import make_node_id  # noqa: E402
from graph_builder import deduplicate_edges, validate_edges  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Node = dict[str, Any]
Edge = dict[str, Any]
Entrypoint = dict[str, Any]
Graph = dict[str, Any]


# ---------------------------------------------------------------------------
# Path normalisation helpers
# ---------------------------------------------------------------------------


def _normalize_path_for_matching(path: str) -> str:
    """Normalize a URL path by stripping trailing slashes and lowering."""
    path = path.strip().rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return path.lower()


def _to_regex_pattern(route_path: str) -> str:
    """Convert a route path with parameter placeholders to a regex.

    Handles both Python-style ``{param}`` and TS-style ``:param`` placeholders.
    """
    # Normalize to a common form first: replace :param with {param}
    normalized = re.sub(r":(\w+)", r"{\1}", route_path)
    # Escape everything except the placeholders
    parts = re.split(r"(\{[^}]+\})", normalized)
    regex_parts: list[str] = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            regex_parts.append(r"[^/]+")
        else:
            regex_parts.append(re.escape(part))
    return "^" + "".join(regex_parts) + "$"


def _is_parameterized(path: str) -> bool:
    """Check if a path contains parameter placeholders ({param} or :param)."""
    return bool(re.search(r"\{[^}]+\}|:\w+", path))


# ---------------------------------------------------------------------------
# Core linking logic
# ---------------------------------------------------------------------------


def link_frontend_to_backend(
    ts_data: dict[str, Any] | None,
    py_entrypoints: list[Entrypoint],
    all_nodes: list[Node],
) -> tuple[list[Edge], list[dict[str, str]], list[dict[str, str]]]:
    """Match TS API call URLs to Python route decorator paths.

    Returns:
        - list of cross-language api_call edges
        - list of disconnected backend endpoints (no frontend caller)
        - list of disconnected frontend calls (no backend match)
    """
    cross_edges: list[Edge] = []
    disconnected_endpoints: list[dict[str, str]] = []
    disconnected_frontend_calls: list[dict[str, str]] = []

    if ts_data is None:
        # No TS analysis: all backend routes are disconnected from frontend
        for ep in py_entrypoints:
            if ep["kind"] == "route":
                disconnected_endpoints.append({
                    "node_id": ep["node_id"],
                    "path": ep.get("path", ""),
                })
        return cross_edges, disconnected_endpoints, disconnected_frontend_calls

    # Build a lookup of backend routes: path -> list of entrypoint info
    route_lookup: dict[str, list[Entrypoint]] = defaultdict(list)
    for ep in py_entrypoints:
        if ep["kind"] == "route" and ep.get("path"):
            normalized = _normalize_path_for_matching(ep["path"])
            route_lookup[normalized].append(ep)

    # Collect all API call sites from TS analysis
    api_calls: list[dict[str, Any]] = ts_data.get("api_call_sites", [])

    # Track which routes and frontend calls have been matched
    matched_routes: set[str] = set()
    matched_frontend_calls: set[int] = set()

    # Pass 1: Exact URL matches (high confidence)
    for idx, call in enumerate(api_calls):
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)
        if normalized_url in route_lookup:
            for ep in route_lookup[normalized_url]:
                caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                cross_edges.append({
                    "from": caller_id,
                    "to": ep["node_id"],
                    "type": EdgeType.API_CALL,
                    "confidence": "high",
                    "evidence": f"string_match:{url}",
                })
                matched_routes.add(ep["node_id"])
                matched_frontend_calls.add(idx)

    # Pass 2: Parameterized path matches (medium confidence)
    for idx, call in enumerate(api_calls):
        if idx in matched_frontend_calls:
            continue
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)

        for route_path, eps in route_lookup.items():
            if not _is_parameterized(route_path) and not _is_parameterized(normalized_url):
                continue  # Already handled by exact match or no params to match
            pattern = _to_regex_pattern(route_path)
            if re.match(pattern, normalized_url):
                for ep in eps:
                    caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                    cross_edges.append({
                        "from": caller_id,
                        "to": ep["node_id"],
                        "type": EdgeType.API_CALL,
                        "confidence": "medium",
                        "evidence": f"param_match:{url}~{ep.get('path', '')}",
                    })
                    matched_routes.add(ep["node_id"])
                    matched_frontend_calls.add(idx)
            else:
                # Also try matching the other way: frontend URL might have :param style
                url_pattern = _to_regex_pattern(normalized_url)
                if re.match(url_pattern, route_path):
                    for ep in eps:
                        caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                        cross_edges.append({
                            "from": caller_id,
                            "to": ep["node_id"],
                            "type": EdgeType.API_CALL,
                            "confidence": "medium",
                            "evidence": f"param_match:{url}~{ep.get('path', '')}",
                        })
                        matched_routes.add(ep["node_id"])
                        matched_frontend_calls.add(idx)

    # Pass 3: Heuristic partial matches (low confidence)
    # Match if the URL path shares a significant common prefix with a route
    for idx, call in enumerate(api_calls):
        if idx in matched_frontend_calls:
            continue
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)
        url_segments = [s for s in normalized_url.split("/") if s]

        if len(url_segments) < 2:
            continue

        best_match_ep: Entrypoint | None = None
        best_match_score = 0
        best_route_path = ""

        for route_path, eps in route_lookup.items():
            route_segments = [s for s in route_path.split("/") if s]
            # Count matching leading segments (ignoring parameter segments)
            match_count = 0
            for us, rs in zip(url_segments, route_segments):
                rs_is_param = rs.startswith("{") or rs.startswith(":")
                us_is_param = us.startswith("{") or us.startswith(":")
                if rs_is_param or us_is_param or us == rs:
                    match_count += 1
                else:
                    break

            # Require at least 2 matching segments for a heuristic match
            if match_count >= 2 and match_count > best_match_score:
                best_match_score = match_count
                best_match_ep = eps[0] if eps else None
                best_route_path = route_path

        if best_match_ep is not None:
            caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
            cross_edges.append({
                "from": caller_id,
                "to": best_match_ep["node_id"],
                "type": EdgeType.API_CALL,
                "confidence": "low",
                "evidence": f"heuristic_match:{url}~{best_route_path}",
            })
            matched_routes.add(best_match_ep["node_id"])
            matched_frontend_calls.add(idx)

    # Disconnected backend endpoints (routes not called by any frontend)
    for ep in py_entrypoints:
        if ep["kind"] == "route" and ep["node_id"] not in matched_routes:
            disconnected_endpoints.append({
                "node_id": ep["node_id"],
                "path": ep.get("path", ""),
            })

    # Disconnected frontend calls (no matching backend route)
    for idx, call in enumerate(api_calls):
        if idx not in matched_frontend_calls:
            caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
            disconnected_frontend_calls.append({
                "node_id": caller_id,
                "url": call.get("url", ""),
            })

    return cross_edges, disconnected_endpoints, disconnected_frontend_calls


# ---------------------------------------------------------------------------
# Graph loading / saving helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if missing or invalid."""
    if not path.exists():
        logger.info(f"  [skip] {path.name} not found")
        return None
    try:
        with open(path) as f:
            data: dict[str, Any] = json.load(f)
        logger.info(f"  [ok]   {path.name} loaded")
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"  [warn] {path.name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_cross_layer_linking(input_dir: Path, output_path: Path) -> int:
    """Execute the cross-layer linking pipeline. Returns 0 on success."""
    logger.info("Cross-layer linker: loading inputs...")

    # Load the canonical graph (must exist)
    graph_path = input_dir / "architecture.graph.json"
    graph = load_json(graph_path)
    if graph is None:
        logger.error(
            f"architecture.graph.json not found in {input_dir}. "
            "Run graph_builder first."
        )
        return 1

    # Load optional ts_analysis.json for API call sites
    ts_data = load_json(input_dir / "ts_analysis.json")

    # Extract Python route entrypoints from the graph
    py_entrypoints: list[Entrypoint] = [
        ep for ep in graph.get("entrypoints", []) if ep.get("kind") == "route"
    ]
    all_nodes: list[Node] = graph.get("nodes", [])

    logger.info(
        f"  Found {len(py_entrypoints)} route entrypoints, "
        f"{len(all_nodes)} nodes in graph"
    )

    # Run the 3-pass linking
    cross_edges, disconnected_endpoints, disconnected_frontend_calls = (
        link_frontend_to_backend(ts_data, py_entrypoints, all_nodes)
    )

    logger.info(
        f"  Linking results: {len(cross_edges)} cross-layer edges, "
        f"{len(disconnected_endpoints)} disconnected endpoints, "
        f"{len(disconnected_frontend_calls)} disconnected frontend calls"
    )

    # Append cross-layer edges to the graph and deduplicate/validate
    existing_edges: list[Edge] = graph.get("edges", [])
    combined_edges = existing_edges + cross_edges

    combined_edges = deduplicate_edges(combined_edges)
    node_id_set = {n["id"] for n in all_nodes}
    combined_edges = validate_edges(combined_edges, node_id_set)

    graph["edges"] = combined_edges

    # Store disconnected info in the graph for downstream consumers
    graph["disconnected_endpoints"] = disconnected_endpoints
    graph["disconnected_frontend_calls"] = disconnected_frontend_calls

    # Write the updated graph
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
        f.write("\n")

    logger.info(f"Wrote updated graph to {output_path}")
    logger.info(
        f"Cross-layer linking complete: "
        f"{len(combined_edges)} total edges "
        f"(+{len(cross_edges)} cross-language)"
    )

    if disconnected_endpoints:
        logger.info(
            f"  Disconnected backend endpoints: {len(disconnected_endpoints)}"
        )
        for dep in disconnected_endpoints:
            logger.info(f"    - {dep['node_id']} ({dep.get('path', '')})")

    if disconnected_frontend_calls:
        logger.info(
            f"  Disconnected frontend calls: {len(disconnected_frontend_calls)}"
        )
        for dfc in disconnected_frontend_calls:
            logger.info(f"    - {dfc['node_id']} -> {dfc.get('url', '')}")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Cross-language linker: match frontend API calls to backend "
            "route endpoints and append api_call edges to the architecture graph."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help=(
            "Directory containing architecture.graph.json and optionally "
            "ts_analysis.json (default: .architecture)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path for the updated graph "
            "(default: <input-dir>/architecture.graph.json)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    output = args.output if args.output is not None else args.input_dir / "architecture.graph.json"
    return run_cross_layer_linking(input_dir=args.input_dir, output_path=output)


if __name__ == "__main__":
    sys.exit(main())
