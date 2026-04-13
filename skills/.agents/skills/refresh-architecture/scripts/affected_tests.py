#!/usr/bin/env python3
"""affected_tests() — query which test files are affected by a file change.

Reverse BFS from changed files through the architecture graph to test nodes:

    changed_file (path) ──mapped──▶ source_node ◀──TEST_COVERS── test_node

Returns ``list[str] | None``:
  - ``list[str]`` — test file paths to run
  - ``[]`` — no tests cover the changed files
  - ``None`` — fall back to running the full suite (graph stale, missing,
    traversal bound exceeded). Callers MUST treat None as "run everything".

See contracts/internal/test-linker-output.yaml for the contract and
design.md D5/D10 for the rationale behind the traversal bound.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Graphs older than this are treated as stale; callers get None.
MAX_GRAPH_AGE_HOURS: int = 24

#: Hard cap on BFS visit count. Traversals that would exceed this bound
#: return None (fall back to full suite) rather than block indefinitely.
MAX_TRAVERSAL_NODES: int = 10_000


# ---------------------------------------------------------------------------
# Staleness / loading
# ---------------------------------------------------------------------------


def is_graph_stale(graph_path: Path, max_age_hours: int = MAX_GRAPH_AGE_HOURS) -> bool:
    """Return True if *graph_path* does not exist or is older than *max_age_hours*."""
    if not graph_path.exists():
        return True
    mtime = graph_path.stat().st_mtime
    age_seconds = time.time() - mtime
    return age_seconds > max_age_hours * 3600


def load_graph_with_mtime(graph_path: Path) -> tuple[dict[str, Any], float] | None:
    """Load the graph and return (graph, mtime), or None if missing/stale."""
    if is_graph_stale(graph_path):
        return None
    try:
        with open(graph_path) as f:
            graph = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("affected_tests: cannot load graph: %s", exc)
        return None
    return graph, graph_path.stat().st_mtime


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------


def _normalize_path(raw: str) -> str:
    """Strip leading ./ and collapse redundant separators for comparison."""
    p = raw.strip()
    if p.startswith("./"):
        p = p[2:]
    return p


def _build_file_to_nodes_index(
    nodes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Map file path → list of node ids declared in that file.

    Uses the suffix-match trick: for a changed file ``src/feature_flags.py``,
    we also index ``feature_flags.py`` and ``agent-coordinator/src/feature_flags.py``
    so that partial path matches still find the node.
    """
    index: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        f = n.get("file")
        if not f:
            continue
        norm = _normalize_path(f)
        index[norm].append(n["id"])
    return dict(index)


# ---------------------------------------------------------------------------
# Reverse edge index
# ---------------------------------------------------------------------------


def _build_reverse_test_covers_index(
    edges: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Map source_node_id → list of test_node_ids that cover it."""
    reverse: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("type") == "TEST_COVERS":
            reverse[e["to"]].append(e["from"])
    return dict(reverse)


def _build_reverse_structural_index(
    edges: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Map target_node_id → list of caller/importer ids (for transitive walk).

    Phase 1 is import-level only — transitive closure is deferred. We still
    follow ``import`` edges in reverse so that changing a module propagates
    to modules that import it (one hop), as a shallow heuristic.
    """
    reverse: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("type") in {"import", "call"}:
            reverse[e["to"]].append(e["from"])
    return dict(reverse)


# ---------------------------------------------------------------------------
# Main query
# ---------------------------------------------------------------------------


def _resolve_changed_to_node_ids(
    changed_files: list[str],
    file_index: dict[str, list[str]],
) -> set[str]:
    """Map file paths to graph node ids, tolerating prefix differences."""
    out: set[str] = set()
    changed_norm = [_normalize_path(p) for p in changed_files]
    for changed in changed_norm:
        # 1. Exact match
        if changed in file_index:
            out.update(file_index[changed])
            continue
        # 2. Suffix match (changed file path ends with indexed path, or vice versa)
        for indexed_path, node_ids in file_index.items():
            if changed.endswith(indexed_path) or indexed_path.endswith(changed):
                out.update(node_ids)
    return out


def affected_tests(
    changed_files: list[str],
    graph_path: Path | str = Path("docs/architecture-analysis/architecture.graph.json"),
) -> list[str] | None:
    """Return the list of test file paths affected by *changed_files*.

    Returns:
        ``list[str]`` of relative test file paths (may be empty),
        or ``None`` if the result cannot be trusted (graph stale, missing,
        or traversal bound exceeded). Callers MUST run the full suite on None.
    """
    graph_path = Path(graph_path)
    loaded = load_graph_with_mtime(graph_path)
    if loaded is None:
        logger.warning(
            "affected_tests: graph missing or stale (>%dh) — falling back to full suite",
            MAX_GRAPH_AGE_HOURS,
        )
        return None

    graph, _mtime = loaded
    if not changed_files:
        return []

    nodes: list[dict[str, Any]] = graph.get("nodes", [])
    edges: list[dict[str, Any]] = graph.get("edges", [])
    node_by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in nodes}

    file_index = _build_file_to_nodes_index(nodes)
    reverse_test_covers = _build_reverse_test_covers_index(edges)
    reverse_structural = _build_reverse_structural_index(edges)

    start_nodes = _resolve_changed_to_node_ids(changed_files, file_index)
    if not start_nodes:
        logger.warning(
            "affected_tests: no graph nodes found for changed files %s "
            "(uncovered modules — suggest 'run full suite')",
            changed_files,
        )
        return []

    # BFS with visited set (cycle safe) and traversal bound.
    visited: set[str] = set()
    frontier: deque[str] = deque(start_nodes)
    test_ids: set[str] = set()

    while frontier:
        if len(visited) >= MAX_TRAVERSAL_NODES:
            logger.warning(
                "affected_tests: traversal exceeded %d nodes — falling back to full suite",
                MAX_TRAVERSAL_NODES,
            )
            return None
        nid = frontier.popleft()
        if nid in visited:
            continue
        visited.add(nid)

        # Collect tests covering this node
        for test_id in reverse_test_covers.get(nid, ()):
            test_ids.add(test_id)

        # Walk structural edges (import/call) in reverse — shallow transitive
        for upstream in reverse_structural.get(nid, ()):
            if upstream not in visited:
                frontier.append(upstream)

    # Uncovered input warning
    covered_any = any(
        any(sid in reverse_test_covers for sid in file_index.get(_normalize_path(f), []))
        for f in changed_files
    )
    if not covered_any and not test_ids:
        logger.warning(
            "affected_tests: uncovered modules in changed files %s",
            changed_files,
        )

    # Dedupe test file paths
    test_files: set[str] = set()
    for tid in test_ids:
        node = node_by_id.get(tid)
        if node and node.get("file"):
            test_files.add(_normalize_path(node["file"]))
    return sorted(test_files)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Given a list of changed files, query the architecture graph for "
            "the subset of tests that cover them. Prints one test file path "
            "per line, or 'ALL' if the graph is stale (callers run full suite)."
        ),
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("docs/architecture-analysis/architecture.graph.json"),
        help="Path to architecture.graph.json",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Changed file paths (space-separated)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    result = affected_tests(args.files, graph_path=args.graph)
    if result is None:
        print("ALL")
        return 0
    for path in result:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
