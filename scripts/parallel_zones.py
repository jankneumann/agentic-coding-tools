#!/usr/bin/env python3
"""Parallel modification zone analyzer.

Identifies independent subgraphs in the canonical architecture graph to
determine which modules can be safely modified in parallel.

Uses only stdlib dependencies -- graph algorithms are implemented via
union-find (connected components) and BFS (transitive dependents).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def load_graph(path: Path) -> dict:
    """Load and return the architecture graph JSON."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Union-Find for weakly connected components
# ---------------------------------------------------------------------------

class UnionFind:
    """Disjoint-set / union-find with path compression and union by rank."""

    def __init__(self, elements: list[str]) -> None:
        self._parent: dict[str, str] = {e: e for e in elements}
        self._rank: dict[str, int] = {e: 0 for e in elements}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Union by rank
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def components(self) -> dict[str, list[str]]:
        """Return mapping of root -> list of members."""
        groups: dict[str, list[str]] = defaultdict(list)
        for element in self._parent:
            groups[self.find(element)].append(element)
        return dict(groups)


# ---------------------------------------------------------------------------
# Dependency-edge filtering
# ---------------------------------------------------------------------------

# Edge types that represent import / dependency relationships.
_DEPENDENCY_EDGE_TYPES = frozenset({
    "import",
    "call",
    "api_call",
    "db_access",
    "hook_usage",
    "component_child",
    "fk_reference",
})


def _is_dependency_edge(edge: dict) -> bool:
    """Return True if this edge should be considered a dependency link."""
    return edge.get("type") in _DEPENDENCY_EDGE_TYPES


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

def compute_connected_components(
    node_ids: list[str],
    edges: list[dict],
) -> list[list[str]]:
    """Compute weakly connected components via union-find.

    Only dependency edges (import, call, etc.) are considered.  The graph is
    treated as undirected for the purpose of finding connected components.
    """
    uf = UnionFind(node_ids)
    for edge in edges:
        if _is_dependency_edge(edge):
            src, dst = edge["from"], edge["to"]
            if src in uf._parent and dst in uf._parent:
                uf.union(src, dst)

    groups = uf.components()
    # Sort components deterministically: by size descending, then by first id
    return sorted(groups.values(), key=lambda g: (-len(g), sorted(g)[0]))


def find_leaf_modules(
    node_ids: set[str],
    edges: list[dict],
) -> set[str]:
    """Return node IDs that have no dependents (nothing imports/calls them).

    A leaf module is one where no dependency edge points *to* it -- meaning
    no other module depends on it, so modifying it cannot break others.
    """
    has_dependent: set[str] = set()
    for edge in edges:
        if _is_dependency_edge(edge):
            # edge["to"] is depended upon by edge["from"]
            target = edge["to"]
            if target in node_ids:
                has_dependent.add(target)
    return node_ids - has_dependent


def compute_dependents_graph(
    edges: list[dict],
) -> dict[str, set[str]]:
    """Build a reverse adjacency list: module -> set of direct dependents.

    If A imports B, then A is a *dependent* of B.  So edge (from=A, to=B)
    means A depends on B, and B's dependents include A.
    """
    rev: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if _is_dependency_edge(edge):
            # A depends on B  =>  B's dependents include A
            rev[edge["to"]].add(edge["from"])
    return dict(rev)


def compute_impact_radius(
    module_id: str,
    dependents_graph: dict[str, set[str]],
) -> list[str]:
    """BFS over the dependents graph to find all transitive dependents.

    Returns sorted list of module IDs that would be impacted if *module_id*
    is modified (i.e., everything that transitively depends on it).
    """
    visited: set[str] = set()
    queue: deque[str] = deque([module_id])
    while queue:
        current = queue.popleft()
        for dep in dependents_graph.get(current, ()):
            if dep not in visited:
                visited.add(dep)
                queue.append(dep)
    return sorted(visited)


def find_high_impact_modules(
    node_ids: set[str],
    dependents_graph: dict[str, set[str]],
    threshold: int,
) -> list[dict]:
    """Return modules whose transitive dependent count exceeds *threshold*."""
    results: list[dict] = []
    for node_id in sorted(node_ids):
        dependents = compute_impact_radius(node_id, dependents_graph)
        if len(dependents) > threshold:
            results.append({
                "id": node_id,
                "dependent_count": len(dependents),
                "dependents": dependents,
            })
    # Sort by dependent count descending for readability
    results.sort(key=lambda r: -r["dependent_count"])
    return results


# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------

_PREFIX_TO_LANGUAGE: dict[str, str] = {
    "py": "python",
    "ts": "typescript",
    "pg": "sql",
}


def _language_from_id(node_id: str) -> str:
    prefix = node_id.split(":")[0] if ":" in node_id else ""
    return _PREFIX_TO_LANGUAGE.get(prefix, "unknown")


def _language_mix(module_ids: list[str]) -> list[str]:
    """Return sorted, deduplicated list of languages in a group."""
    return sorted({_language_from_id(m) for m in module_ids})


# ---------------------------------------------------------------------------
# Output construction
# ---------------------------------------------------------------------------

def build_output(
    graph: dict,
    components: list[list[str]],
    leaf_ids: set[str],
    high_impact: list[dict],
    node_map: dict[str, dict],
) -> dict:
    """Assemble the parallel_zones.json structure."""
    independent_groups = []
    for idx, group in enumerate(components):
        independent_groups.append({
            "id": idx,
            "modules": sorted(group),
            "language_mix": _language_mix(group),
            "size": len(group),
        })

    leaf_modules = sorted(
        [
            {
                "id": nid,
                "language": node_map[nid]["language"],
                "file": node_map[nid]["file"],
            }
            for nid in leaf_ids
            if nid in node_map
        ],
        key=lambda x: x["id"],
    )

    total_modules = len(node_map)
    largest = max((len(g) for g in components), default=0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "independent_groups": independent_groups,
        "leaf_modules": leaf_modules,
        "high_impact_modules": high_impact,
        "summary": {
            "total_modules": total_modules,
            "total_groups": len(components),
            "largest_group_size": largest,
            "leaf_count": len(leaf_modules),
            "high_impact_count": len(high_impact),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parallel modification zone analyzer for architecture graphs.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path(".architecture/architecture.graph.json"),
        help="Path to the canonical architecture graph JSON (default: .architecture/architecture.graph.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/parallel_zones.json"),
        help="Output path for parallel_zones.json (default: .architecture/parallel_zones.json)",
    )
    parser.add_argument(
        "--impact-threshold",
        type=int,
        default=10,
        help="Threshold for high-impact modules (default: 10)",
    )
    parser.add_argument(
        "--impact-for",
        type=str,
        default=None,
        help="Print impact radius for a specific module",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # --- Load graph ---
    if not args.graph.exists():
        print(f"Error: graph file not found: {args.graph}", file=sys.stderr)
        return 1

    graph = load_graph(args.graph)

    nodes: list[dict] = graph.get("nodes", [])
    edges: list[dict] = graph.get("edges", [])

    node_map: dict[str, dict] = {n["id"]: n for n in nodes}
    node_ids = list(node_map.keys())
    node_id_set = set(node_ids)

    if not node_ids:
        print("Warning: graph contains no nodes.", file=sys.stderr)

    # --- Analysis ---
    components = compute_connected_components(node_ids, edges)
    leaf_ids = find_leaf_modules(node_id_set, edges)
    dependents_graph = compute_dependents_graph(edges)
    high_impact = find_high_impact_modules(
        node_id_set, dependents_graph, args.impact_threshold,
    )

    # --- Impact for a specific module ---
    if args.impact_for is not None:
        module_id = args.impact_for
        if module_id not in node_id_set:
            print(
                f"Error: module '{module_id}' not found in graph.",
                file=sys.stderr,
            )
            return 1
        radius = compute_impact_radius(module_id, dependents_graph)
        print(f"Impact radius for '{module_id}': {len(radius)} transitive dependent(s)")
        if radius:
            for dep in radius:
                print(f"  - {dep}")
        else:
            print("  (no dependents)")

    # --- Build & write output ---
    output = build_output(graph, components, leaf_ids, high_impact, node_map)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    # --- Summary to stdout ---
    s = output["summary"]
    print(f"Wrote {args.output}")
    print(f"  Total modules:      {s['total_modules']}")
    print(f"  Independent groups: {s['total_groups']}")
    print(f"  Largest group:      {s['largest_group_size']}")
    print(f"  Leaf modules:       {s['leaf_count']}")
    print(f"  High-impact (>{args.impact_threshold}): {s['high_impact_count']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
