"""Graph traversal utilities used across the architecture pipeline.

Provides adjacency building, reachability, cycle detection, and transitive
dependent computation — all parameterised by edge-type filters so callers
can restrict to structural, side-effect, or all edges.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable

from arch_utils.constants import DEPENDENCY_EDGE_TYPES, EdgeType


# ---------------------------------------------------------------------------
# Adjacency
# ---------------------------------------------------------------------------


def build_adjacency(
    edges: Iterable[dict[str, Any]],
    *,
    edge_types: frozenset[str] | None = None,
    reverse: bool = False,
) -> dict[str, list[str]]:
    """Build a forward (or reverse) adjacency list from *edges*.

    Parameters
    ----------
    edges:
        Iterable of edge dicts with at least ``from``, ``to``, and ``type``.
    edge_types:
        If given, only include edges whose ``type`` is in this set.
        Defaults to all edges.
    reverse:
        If ``True``, reverse edge direction (build "who depends on me").

    Returns
    -------
    dict mapping node_id -> list of neighbour node_ids.
    """
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge_types is not None and edge.get("type") not in edge_types:
            continue
        src, dst = edge["from"], edge["to"]
        if reverse:
            adj[dst].append(src)
        else:
            adj[src].append(dst)
    return dict(adj)


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


def reachable_from(
    start: str,
    adjacency: dict[str, list[str] | set[str]],
    *,
    include_start: bool = True,
) -> set[str]:
    """Return all nodes reachable from *start* via BFS.

    Works with adjacency lists whose values are lists *or* sets.
    """
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, ()):
            if neighbor not in visited:
                queue.append(neighbor)
    if not include_start:
        visited.discard(start)
    return visited


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def find_cycles(
    edges: Iterable[dict[str, Any]],
    *,
    edge_types: frozenset[str] | None = None,
) -> list[list[str]]:
    """Find all elementary cycles via DFS on the directed graph.

    Parameters
    ----------
    edges:
        Edge dicts with ``from``, ``to``, ``type``.
    edge_types:
        Restrict to these edge types (default: dependency edges).
    """
    if edge_types is None:
        edge_types = frozenset({EdgeType.CALL, EdgeType.IMPORT})

    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.get("type") in edge_types:
            adj[edge["from"]].append(edge["to"])

    visited: set[str] = set()
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    def _dfs(node: str, path: list[str]) -> None:
        if node in on_stack:
            idx = path.index(node)
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        on_stack.add(node)
        path.append(node)
        for neighbor in adj.get(node, []):
            _dfs(neighbor, path)
        path.pop()
        on_stack.discard(node)

    for node_id in adj:
        if node_id not in visited:
            _dfs(node_id, [])

    return cycles


# ---------------------------------------------------------------------------
# Transitive dependents
# ---------------------------------------------------------------------------


def transitive_dependents(
    edges: Iterable[dict[str, Any]],
    *,
    edge_types: frozenset[str] | None = None,
) -> dict[str, set[str]]:
    """For each node, compute the set of nodes that *transitively depend on it*.

    Uses reverse adjacency + BFS per node.  Suitable for impact analysis.

    Parameters
    ----------
    edge_types:
        Restrict to these edge types (default: ``DEPENDENCY_EDGE_TYPES``).
    """
    if edge_types is None:
        edge_types = DEPENDENCY_EDGE_TYPES

    # Build reverse adjacency: target -> {sources}
    rev: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.get("type") in edge_types:
            rev[edge["to"]].add(edge["from"])

    result: dict[str, set[str]] = {}
    for node_id in rev:
        visited: set[str] = set()
        stack = list(rev.get(node_id, set()))
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            stack.extend(rev.get(n, set()) - visited)
        result[node_id] = visited

    return result
