"""Build the atlas view-model from committed architecture artifacts.

The atlas is a *rendering* layer. Every fact it shows comes from
``docs/architecture-analysis/architecture.graph.json`` (produced by
``refresh-architecture``); this module never parses source code itself.

Two responsibilities:

* **Aggregate** the symbol-level graph into a module-level overview. The raw
  graph holds ~1.5k symbol nodes, which is too many for a readable force
  layout, so the graph pane renders one node per source file and the tree pane
  keeps full symbol detail. Symbol-level cross-connections stay available
  through :func:`build_view_model`'s ``symbolEdges``.
* **Measure coverage honestly.** The analyzer is pointed at configured source
  roots, so the graph can describe a fraction of the repository while looking
  complete. :func:`measure_coverage` compares graph contents against the files
  actually on disk so the rendered page can say what it does *not* know.

Every collection is sorted by a stable key so a fixed input graph renders
byte-identical output, matching the determinism contract the other
architecture producers follow.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Directories that never contain first-party source. Mirrors the skip logic in
# ``analyze_python.py`` (dot-directories and __pycache__) plus the JS/vendor
# directories that analyzer does not need to consider.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {"__pycache__", "node_modules", "site-packages", "dist", "build", "target"}
)

# Suffix -> language label, matching the languages the graph compiler emits.
LANGUAGE_SUFFIXES: dict[str, str] = {
    ".py": "python",
    ".sql": "sql",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# Node kinds that are containers rather than leaves, used to nest SQL columns
# beneath their owning table in the tree pane.
_CONTAINER_KINDS: frozenset[str] = frozenset({"table"})

_UNFILED = "(unfiled)"
"""Group label for nodes the analyzer emitted without a source file.

The SQL analyzer reports indexes and triggers without a file attribution (64
such nodes in the current graph). Dropping them would silently shrink the
atlas, so they are grouped explicitly instead.
"""


class AtlasInputError(Exception):
    """Raised when an input artifact is missing or structurally unusable."""


@dataclass(frozen=True, slots=True)
class Coverage:
    """How much of the repository the graph actually describes.

    Matching is by *file name*, not path: the analyzer records bare basenames
    (``coordination_api.py``), so a path-exact comparison is impossible. This
    biases coverage *upward* — one covered basename may match several on-disk
    files — so the reported percentage is an optimistic bound and the UI says so.

    ``percent`` is driven by ``files_matched`` (graph names that resolve to a file
    actually present) rather than by ``files_in_graph``. Using the raw graph count
    would let a stale graph report over 100% coverage and hide the gap entirely.
    ``files_missing`` counts the opposite direction — names the graph describes
    that no longer exist on disk — which is a direct staleness signal.
    """

    language: str
    files_in_graph: int
    files_matched: int
    files_missing: int
    files_on_disk: int
    uncovered_top_dirs: tuple[tuple[str, int], ...]

    @property
    def percent(self) -> float:
        if self.files_on_disk == 0:
            return 0.0
        return round(100.0 * self.files_matched / self.files_on_disk, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "filesInGraph": self.files_in_graph,
            "filesMatched": self.files_matched,
            "filesMissing": self.files_missing,
            "filesOnDisk": self.files_on_disk,
            "percent": self.percent,
            "uncoveredTopDirs": [
                {"dir": name, "files": count} for name, count in self.uncovered_top_dirs
            ],
        }


@dataclass(slots=True)
class Module:
    """One source file: the unit rendered as a node in the graph pane."""

    key: str
    file: str
    language: str
    symbols: list[dict[str, Any]] = field(default_factory=list)

    @property
    def kind_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(s["kind"] for s in self.symbols).items()))

    @property
    def tags(self) -> list[str]:
        return sorted({t for s in self.symbols for t in s.get("tags", ())})


def load_graph(path: Path) -> dict[str, Any]:
    """Load and structurally validate the architecture graph."""
    if not path.is_file():
        raise AtlasInputError(
            f"architecture graph not found at {path}. "
            "Run `make architecture` (or `make architecture-refresh`) first."
        )
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AtlasInputError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(graph, dict):
        raise AtlasInputError(f"{path} must contain a JSON object, got {type(graph).__name__}")
    for required in ("nodes", "edges"):
        if not isinstance(graph.get(required), list):
            raise AtlasInputError(f"{path} is missing a '{required}' list")
    return graph


def module_key(language: str, file: str) -> str:
    """Stable module identifier, namespaced to avoid collision with node ids."""
    return f"mod::{language}::{file or _UNFILED}"


def group_modules(nodes: list[dict[str, Any]]) -> list[Module]:
    """Group symbol nodes into modules, keyed by (language, file)."""
    modules: dict[str, Module] = {}
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        language = node.get("language") or "unknown"
        file = node.get("file") or _UNFILED
        key = module_key(language, file)
        module = modules.get(key)
        if module is None:
            module = Module(key=key, file=file, language=language)
            modules[key] = module

        span = node.get("span") or {}
        module.symbols.append(
            {
                "id": node_id,
                "name": node.get("name") or node_id,
                "kind": node.get("kind") or "unknown",
                "line": span.get("start") or 0,
                "tags": tuple(sorted(node.get("tags") or ())),
                "signature": node.get("signatures") or {},
            }
        )

    for module in modules.values():
        # Sort by declaration order, then name, so re-runs are byte-stable.
        module.symbols.sort(key=lambda s: (s["line"], s["name"], s["id"]))
    return sorted(modules.values(), key=lambda m: (m.language, m.file))


def nest_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nest child symbols beneath their container (SQL columns under tables).

    Containment is inferred from the dotted node-id prefix, which is how the
    SQL analyzer names columns (``pg:public.public.file_locks.file_path`` is a
    column of ``pg:public.public.file_locks``). Symbols with no container are
    returned at the top level, so nothing is dropped when the heuristic misses.
    """
    containers = {s["id"]: s for s in symbols if s["kind"] in _CONTAINER_KINDS}
    if not containers:
        return [dict(s, children=[]) for s in symbols]

    out: dict[str, dict[str, Any]] = {
        s["id"]: dict(s, children=[]) for s in symbols if s["id"] in containers
    }
    top: list[dict[str, Any]] = []
    for symbol in symbols:
        if symbol["id"] in containers:
            continue
        parent_id = _longest_container_prefix(symbol["id"], containers)
        if parent_id is None:
            top.append(dict(symbol, children=[]))
        else:
            out[parent_id]["children"].append(dict(symbol, children=[]))

    top.extend(out[cid] for cid in containers)
    top.sort(key=lambda s: (s["line"], s["name"], s["id"]))
    return top


def _longest_container_prefix(node_id: str, containers: dict[str, Any]) -> str | None:
    """Return the most specific container id that prefixes ``node_id``."""
    best: str | None = None
    for candidate in containers:
        if node_id.startswith(candidate + ".") and (best is None or len(candidate) > len(best)):
            best = candidate
    return best


def aggregate_edges(
    edges: list[dict[str, Any]],
    node_to_module: dict[str, str],
) -> list[dict[str, Any]]:
    """Roll symbol-level edges up to module level, summing weights.

    Self-edges (a module calling itself) are dropped: they carry no navigation
    value in the overview and would render as unreadable loops. Intra-module
    calls remain visible at symbol level via ``symbolEdges``.
    """
    weights: Counter[tuple[str, str, str]] = Counter()
    for edge in edges:
        src = node_to_module.get(edge.get("from", ""))
        dst = node_to_module.get(edge.get("to", ""))
        if src is None or dst is None or src == dst:
            continue
        weights[(src, dst, edge.get("type") or "unknown")] += 1

    return [
        {"source": src, "target": dst, "type": etype, "weight": weight}
        for (src, dst, etype), weight in sorted(weights.items())
    ]


def measure_coverage(
    repo_root: Path,
    nodes: list[dict[str, Any]],
) -> list[Coverage]:
    """Compare graph contents against source files actually present on disk."""
    on_disk: dict[str, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in EXCLUDED_DIR_NAMES
        )
        for filename in filenames:
            language = LANGUAGE_SUFFIXES.get(Path(filename).suffix)
            if language is None:
                continue
            on_disk.setdefault(language, []).append(Path(dirpath, filename))

    graph_files: dict[str, set[str]] = {}
    for node in nodes:
        file = node.get("file")
        if file:
            graph_files.setdefault(node.get("language") or "unknown", set()).add(file)

    coverages: list[Coverage] = []
    for language in sorted(set(on_disk) | set(graph_files)):
        disk_paths = on_disk.get(language, [])
        disk_names = {p.name for p in disk_paths}
        graph_names = graph_files.get(language, set())

        uncovered: Counter[str] = Counter()
        for path in disk_paths:
            if path.name in graph_names:
                continue
            rel = path.relative_to(repo_root)
            uncovered[rel.parts[0] if len(rel.parts) > 1 else "."] += 1

        coverages.append(
            Coverage(
                language=language,
                files_in_graph=len(graph_names),
                files_matched=len(graph_names & disk_names),
                files_missing=len(graph_names - disk_names),
                files_on_disk=len(disk_paths),
                uncovered_top_dirs=tuple(sorted(uncovered.items(), key=lambda kv: (-kv[1], kv[0]))),
            )
        )
    return coverages


def build_view_model(
    graph: dict[str, Any],
    repo_root: Path,
    *,
    measure: bool = True,
) -> dict[str, Any]:
    """Assemble the complete JSON payload embedded into the rendered page."""
    nodes: list[dict[str, Any]] = graph["nodes"]
    edges: list[dict[str, Any]] = graph["edges"]

    modules = group_modules(nodes)
    node_to_module = {
        symbol["id"]: module.key for module in modules for symbol in module.symbols
    }

    snapshot = (graph.get("snapshots") or [{}])[0]
    entrypoints = {e for e in graph.get("entrypoints") or [] if isinstance(e, str)}

    module_payload = [
        {
            "key": module.key,
            "file": module.file,
            "language": module.language,
            "symbolCount": len(module.symbols),
            "kinds": module.kind_counts,
            "tags": module.tags,
            "tree": nest_symbols(module.symbols),
        }
        for module in modules
    ]

    symbol_payload = [
        {
            "id": symbol["id"],
            "name": symbol["name"],
            "kind": symbol["kind"],
            "module": module.key,
            "line": symbol["line"],
            "tags": list(symbol["tags"]),
            "entry": symbol["id"] in entrypoints,
        }
        for module in modules
        for symbol in module.symbols
    ]

    symbol_edges = sorted(
        (
            {
                "s": edge["from"],
                "t": edge["to"],
                "ty": edge.get("type") or "unknown",
                "c": edge.get("confidence") or "unknown",
            }
            for edge in edges
            if edge.get("from") in node_to_module and edge.get("to") in node_to_module
        ),
        key=lambda e: (e["s"], e["t"], e["ty"]),
    )

    dropped = len(edges) - len(symbol_edges)

    return {
        "meta": {
            "generatedFrom": snapshot.get("generated_at"),
            "gitSha": snapshot.get("git_sha"),
            "toolVersions": snapshot.get("tool_versions") or {},
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "moduleCount": len(modules),
            "danglingEdges": dropped,
        },
        "coverage": [c.to_dict() for c in (measure_coverage(repo_root, nodes) if measure else [])],
        "modules": module_payload,
        "moduleEdges": aggregate_edges(edges, node_to_module),
        "symbols": symbol_payload,
        "symbolEdges": symbol_edges,
    }
