"""Deterministic behavior-cluster seeding for the handbook (design D4).

This module builds the *fixed skeleton* a handbook is synthesized onto. It is a
pure function of committed artifacts — the canonical graph plus the insight
files — and uses no LLM. That split is what keeps synthesis honest: the
structuring step may name, group, and narrate the clusters produced here, but
it can never invent a member node that static analysis did not find.

Algorithm:

1. Every entrypoint roots a candidate cluster.
2. Expand along behavior-carrying edges (``call``, ``api_call``, ``db_access``).
   ``import`` edges are excluded — importing a module is not participating in
   its behavior.
3. Merge clusters whose membership overlaps by more than ``MERGE_THRESHOLD``.
4. Annotate hubs from ``high_impact_nodes.json`` and attach exception patterns
   from ``treesitter_enrichment.json`` to the cluster owning their nodes.
5. Entrypoints whose expansion found no downstream go to ``uncovered[]`` — this
   is where today's 96 disconnected endpoints land, counted rather than hidden.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

from arch_utils.graph_io import load_graph, save_json
from arch_utils.traversal import build_adjacency, reachable_from
from source_roots import parse_source_roots, resolve_node_path

logger = logging.getLogger(__name__)

#: Edge types that carry behavior. ``import`` is deliberately absent.
BEHAVIOR_EDGE_TYPES: frozenset[str] = frozenset({"call", "api_call", "db_access"})

#: Clusters sharing more than this fraction of members are merged.
MERGE_THRESHOLD = 0.5

UNCOVERED_NO_TRACED_FLOW = "no_traced_flow"

#: Exception-carrying pattern groups in ``treesitter_enrichment.json``, mapped to
#: the language whose source root resolves their ``file`` field. The enrichment
#: artifact stores these as ``{group: {category: {count, items[]}}}`` with items
#: shaped ``{file, line, enclosing_node}``.
_EXCEPTION_PATTERN_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("python_patterns", "python", ("bare_except", "broad_except")),
    ("typescript_patterns", "typescript", ("empty_catch", "catch_clauses")),
)


def _extract_exception_patterns(
    enrichment: dict[str, Any] | None,
    source_roots: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize enrichment exception findings into a flat, attachable list.

    Accepts both the real ``treesitter_enrichment.json`` layout and a
    pre-flattened ``exception_patterns[]`` list, so callers can supply either.
    """
    if not enrichment:
        return []

    flat: list[dict[str, Any]] = []
    for entry in enrichment.get("exception_patterns") or []:
        if isinstance(entry, dict):
            flat.append(dict(entry))

    for group, language, categories in _EXCEPTION_PATTERN_GROUPS:
        bucket = enrichment.get(group)
        if not isinstance(bucket, dict):
            continue
        for category in categories:
            section = bucket.get(category)
            if not isinstance(section, dict):
                continue
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                rel = str(item.get("file") or "")
                resolved = (
                    resolve_node_path({"language": language, "file": rel}, source_roots)
                    if rel
                    else None
                )
                flat.append(
                    {
                        "node_id": item.get("enclosing_node"),
                        "file": resolved or rel,
                        "line": item.get("line"),
                        "exception_type": category,
                    }
                )
    return flat


def _node_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        n["id"]: n
        for n in graph.get("nodes") or []
        if isinstance(n, dict) and "id" in n
    }


def _in_scope(
    node: dict[str, Any] | None,
    scope: list[str] | None,
    roots: dict[str, str] | None = None,
) -> bool:
    """Match *scope* prefixes against the node's repo-relative path.

    Scope is expressed repo-relative (``agent-coordinator/src``) because that is
    what a caller can see; node ``file`` values are analyzer-relative, so they
    must be resolved before comparison.
    """
    if not scope:
        return True
    if node is None:
        return False
    path = resolve_node_path(node, roots)
    if path is None:
        return False
    return any(path.startswith(prefix) for prefix in scope)


def _cluster_id(root_ids: Iterable[str]) -> str:
    """Derive a stable, readable cluster id from its lowest-sorting root."""
    primary = sorted(root_ids)[0]
    tail = primary.split(":", 1)[-1]
    slug = tail.replace(".", "-").replace("_", "-").lower()
    return f"seed:{slug}"


def _merge_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge clusters whose membership overlap exceeds ``MERGE_THRESHOLD``.

    Runs to a fixed point so a chain of overlapping clusters collapses fully,
    and is order-independent because inputs are sorted by root.
    """
    working = [
        {"roots": set(c["roots"]), "member_nodes": set(c["member_nodes"])}
        for c in clusters
    ]
    changed = True
    while changed:
        changed = False
        out: list[dict[str, Any]] = []
        for candidate in working:
            for existing in out:
                overlap = existing["member_nodes"] & candidate["member_nodes"]
                smaller = min(len(existing["member_nodes"]), len(candidate["member_nodes"]))
                if smaller and len(overlap) / smaller > MERGE_THRESHOLD:
                    existing["member_nodes"] |= candidate["member_nodes"]
                    existing["roots"] |= candidate["roots"]
                    changed = True
                    break
            else:
                out.append(candidate)
        working = out
    return [
        {"roots": sorted(c["roots"]), "member_nodes": sorted(c["member_nodes"])}
        for c in working
    ]


def seed_behaviors(
    graph: dict[str, Any],
    *,
    high_impact: dict[str, Any] | None = None,
    enrichment: dict[str, Any] | None = None,
    scope: list[str] | None = None,
    source_roots: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the deterministic behavior seed skeleton for *graph*.

    ``scope`` optionally restricts clustering to nodes whose repo-relative file
    starts with one of the given path prefixes, so a first synthesis can target
    one subsystem instead of the whole repository.
    """
    nodes = _node_index(graph)
    adjacency = build_adjacency(
        graph.get("edges") or [], edge_types=BEHAVIOR_EDGE_TYPES
    )

    candidates: list[dict[str, Any]] = []
    uncovered: list[dict[str, Any]] = []

    entrypoints = sorted(
        (e for e in graph.get("entrypoints") or [] if isinstance(e, dict)),
        key=lambda e: str(e.get("node_id") or ""),
    )

    for entry in entrypoints:
        root = entry.get("node_id")
        if not root or not _in_scope(nodes.get(root), scope, source_roots):
            continue

        members = {
            n
            for n in reachable_from(root, adjacency)
            if _in_scope(nodes.get(n), scope, source_roots)
        }
        members.add(root)

        if len(members) < 2:
            uncovered.append(
                {
                    "node_id": root,
                    "kind": entry.get("kind"),
                    "path": entry.get("path"),
                    "reason": UNCOVERED_NO_TRACED_FLOW,
                }
            )
            continue

        candidates.append({"roots": [root], "member_nodes": sorted(members)})

    merged = _merge_clusters(candidates)

    hub_ids = {
        h.get("node_id")
        for h in ((high_impact or {}).get("high_impact_nodes") or [])
        if isinstance(h, dict)
    }
    patterns = _extract_exception_patterns(enrichment, source_roots)

    clusters: list[dict[str, Any]] = []
    for cluster in merged:
        member_set = set(cluster["member_nodes"])
        member_files = {
            path
            for path in (
                resolve_node_path(nodes[n], source_roots)
                for n in cluster["member_nodes"]
                if n in nodes
            )
            if path
        }
        attached = [
            p
            for p in patterns
            if p.get("node_id") in member_set
            or (p.get("node_id") is None and str(p.get("file")) in member_files)
        ]
        clusters.append(
            {
                "id": _cluster_id(cluster["roots"]),
                "root": sorted(cluster["roots"])[0],
                "roots": cluster["roots"],
                "member_nodes": cluster["member_nodes"],
                "member_files": sorted(member_files),
                "hubs": sorted(member_set & hub_ids),
                "exception_patterns": sorted(
                    attached,
                    key=lambda p: (str(p.get("file")), int(p.get("line") or 0)),
                ),
            }
        )

    clusters.sort(key=lambda c: c["id"])
    uncovered.sort(key=lambda u: str(u["node_id"]))

    return {
        "clusters": clusters,
        "uncovered": uncovered,
        "summary": {
            "clusters": len(clusters),
            "uncovered_entrypoints": len(uncovered),
            "clustered_nodes": len({n for c in clusters for n in c["member_nodes"]}),
            "scope": scope or [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic behavior seed clusters from the architecture graph"
    )
    parser.add_argument("--graph", required=True)
    parser.add_argument("--high-impact", help="Path to high_impact_nodes.json")
    parser.add_argument("--enrichment", help="Path to treesitter_enrichment.json")
    parser.add_argument(
        "--scope",
        action="append",
        default=None,
        help="Restrict to nodes whose repo-relative file starts with this prefix",
    )
    parser.add_argument(
        "--source-root",
        action="append",
        default=None,
        metavar="LANG=PATH",
        help="Override an analyzer source root (repeatable), e.g. python=src",
    )
    parser.add_argument("--output", required=True, help="Path to write behavior_seeds.json")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    graph = load_graph(Path(args.graph))
    if not graph:
        logger.error("graph not found or empty: %s", args.graph)
        return 1

    seeds = seed_behaviors(
        graph,
        high_impact=load_graph(Path(args.high_impact), quiet=True) if args.high_impact else None,
        enrichment=load_graph(Path(args.enrichment), quiet=True) if args.enrichment else None,
        scope=args.scope,
        source_roots=parse_source_roots(args.source_root),
    )
    save_json(Path(args.output), seeds)
    logger.info(
        "Seeded %d cluster(s), %d uncovered entrypoint(s) -> %s",
        seeds["summary"]["clusters"],
        seeds["summary"]["uncovered_entrypoints"],
        args.output,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
