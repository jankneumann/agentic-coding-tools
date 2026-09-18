"""Symbol call-tree text export for ``build_atlas.py --tree``.

Walks ``call``-typed ``symbolEdges`` from ``build_view_model()`` and prints an
indented tree. Stdlib only. See design D3/D4/D8 of add-visual-code-explainer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Literal

RootKind = Literal["symbol", "module"]
Direction = Literal["in", "out", "both"]

MAX_HOPS = 4
DEFAULT_HOPS = 2


@dataclass(frozen=True, slots=True)
class ResolveOk:
    kind: RootKind
    id: str


@dataclass(frozen=True, slots=True)
class ResolveNotFound:
    pass


@dataclass(frozen=True, slots=True)
class ResolveAmbiguous:
    candidates: tuple[str, ...]


ResolveResult = ResolveOk | ResolveNotFound | ResolveAmbiguous


@dataclass(slots=True)
class TreeNode:
    id: str
    name: str
    file: str
    line: int
    kind: str
    cycle: bool = False
    more: int = 0
    children: list[TreeNode] = field(default_factory=list)


def resolve_target(view: dict[str, Any], target: str) -> ResolveResult:
    """Resolve ``target`` as exact id, unique name, then module file/basename."""
    symbols = view.get("symbols") or []
    by_id = {s["id"]: s for s in symbols if s.get("id")}

    if target in by_id:
        return ResolveOk(kind="symbol", id=target)

    name_hits = sorted(
        (s["id"] for s in symbols if s.get("name") == target),
        key=lambda i: i,
    )
    if len(name_hits) == 1:
        return ResolveOk(kind="symbol", id=name_hits[0])
    if len(name_hits) > 1:
        return ResolveAmbiguous(candidates=tuple(name_hits))

    modules = view.get("modules") or []
    basename = target.rsplit("/", 1)[-1]
    # Compare basename against each module's *basename*, not its whole path.
    # Comparing `m["file"] == basename` only ever matched modules stored at the
    # repository root, so `--tree webhook.py` missed `notifications/webhook.py`
    # and exited 2, against the documented "module file path or basename"
    # resolution contract.
    module_hits = [
        m for m in modules
        if m.get("file") == target
        or str(m.get("file") or "").rsplit("/", 1)[-1] == basename
        or m.get("key") == target
    ]
    # Prefer exact file path match over basename when both could apply.
    exact = [m for m in module_hits if m.get("file") == target or m.get("key") == target]
    chosen = exact[0] if len(exact) == 1 else (module_hits[0] if len(module_hits) == 1 else None)
    if chosen is None and len(module_hits) > 1:
        # Multiple modules share the basename across languages — treat as ambiguous
        # via their keys so the caller can ask.
        return ResolveAmbiguous(
            candidates=tuple(sorted(m["key"] for m in module_hits))
        )
    if chosen is not None:
        return ResolveOk(kind="module", id=chosen["key"])

    return ResolveNotFound()


def _symbol_index(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in (view.get("symbols") or []) if s.get("id")}


def _module_index(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["key"]: m for m in (view.get("modules") or []) if m.get("key")}


def _call_adjacency(
    view: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (out_adj, in_adj) over call edges only, neighbours sorted."""
    out_adj: dict[str, list[str]] = {}
    in_adj: dict[str, list[str]] = {}
    symbols = _symbol_index(view)
    for edge in view.get("symbolEdges") or []:
        if edge.get("ty") != "call":
            continue
        src, dst = edge.get("s"), edge.get("t")
        if src not in symbols or dst not in symbols:
            continue
        out_adj.setdefault(src, []).append(dst)
        in_adj.setdefault(dst, []).append(src)

    def _sort_unique(adj: dict[str, list[str]]) -> dict[str, list[str]]:
        sorted_adj: dict[str, list[str]] = {}
        for node, neigh in adj.items():
            uniq = sorted(set(neigh), key=lambda i: (symbols[i]["name"], i))
            sorted_adj[node] = uniq
        return sorted_adj

    return _sort_unique(out_adj), _sort_unique(in_adj)


def _enrich_symbols(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Attach ``file`` onto each symbol from its module for formatting."""
    modules = _module_index(view)
    out: dict[str, dict[str, Any]] = {}
    for sym in view.get("symbols") or []:
        sid = sym.get("id")
        if not sid:
            continue
        mod = modules.get(sym.get("module") or "")
        enriched = dict(sym)
        enriched["file"] = (mod or {}).get("file") or ""
        out[sid] = enriched
    return out


def _node_from_symbol(sym: dict[str, Any], *, cycle: bool = False, more: int = 0) -> TreeNode:
    return TreeNode(
        id=sym["id"],
        name=str(sym.get("name") or sym["id"]),
        file=str(sym.get("file") or ""),
        line=int(sym.get("line") or 0),
        kind=str(sym.get("kind") or "symbol"),
        cycle=cycle,
        more=more,
    )


def _node_from_module(mod: dict[str, Any]) -> TreeNode:
    file = str(mod.get("file") or "")
    name = file.rsplit("/", 1)[-1] if file else str(mod.get("key") or "module")
    return TreeNode(
        id=mod["key"],
        name=name,
        file=file,
        line=1,
        kind="module",
    )


def _walk_symbol(
    root_id: str,
    *,
    hops: int,
    direction: Literal["in", "out"],
    out_adj: dict[str, list[str]],
    in_adj: dict[str, list[str]],
    symbols: dict[str, dict[str, Any]],
) -> TreeNode:
    adj = out_adj if direction == "out" else in_adj

    def expand(node_id: str, depth: int, path: frozenset[str]) -> TreeNode:
        sym = symbols[node_id]
        if node_id in path:
            return _node_from_symbol(sym, cycle=True)
        neighbours = adj.get(node_id) or []
        if depth >= hops:
            return _node_from_symbol(sym, more=len(neighbours))
        children = [
            expand(nid, depth + 1, path | {node_id})
            for nid in neighbours
            if nid in symbols
        ]
        node = _node_from_symbol(sym)
        node.children = children
        return node

    return expand(root_id, 0, frozenset())


def _walk_module(
    module_key: str,
    *,
    hops: int,
    direction: Literal["in", "out"],
    out_adj: dict[str, list[str]],
    in_adj: dict[str, list[str]],
    symbols: dict[str, dict[str, Any]],
    modules: dict[str, dict[str, Any]],
) -> TreeNode:
    mod = modules[module_key]
    root = _node_from_module(mod)
    member_ids = sorted(
        (sid for sid, sym in symbols.items() if sym.get("module") == module_key),
        key=lambda i: (symbols[i]["name"], i),
    )
    if hops < 1:
        root.more = len(member_ids)
        return root

    adj = out_adj if direction == "out" else in_adj

    def expand_symbol(node_id: str, depth: int, path: frozenset[str]) -> TreeNode:
        sym = symbols[node_id]
        if node_id in path:
            return _node_from_symbol(sym, cycle=True)
        neighbours = adj.get(node_id) or []
        if depth >= hops:
            return _node_from_symbol(sym, more=len(neighbours))
        children = [
            expand_symbol(nid, depth + 1, path | {node_id})
            for nid in neighbours
            if nid in symbols
        ]
        node = _node_from_symbol(sym)
        node.children = children
        return node

    # Hop 1 = module's own symbols; subsequent hops follow call edges.
    root.children = [expand_symbol(sid, 1, frozenset()) for sid in member_ids]
    return root


def walk(
    view: dict[str, Any],
    root: ResolveOk,
    *,
    hops: int = DEFAULT_HOPS,
    direction: Direction = "out",
) -> TreeNode | tuple[TreeNode, TreeNode]:
    """BFS-shaped recursive walk. ``both`` returns ``(callees_tree, callers_tree)``."""
    symbols = _enrich_symbols(view)
    modules = _module_index(view)
    out_adj, in_adj = _call_adjacency(view)
    hops = max(0, hops)

    def one(dir_: Literal["in", "out"]) -> TreeNode:
        if root.kind == "module":
            return _walk_module(
                root.id,
                hops=hops,
                direction=dir_,
                out_adj=out_adj,
                in_adj=in_adj,
                symbols=symbols,
                modules=modules,
            )
        return _walk_symbol(
            root.id,
            hops=hops,
            direction=dir_,
            out_adj=out_adj,
            in_adj=in_adj,
            symbols=symbols,
        )

    if direction == "both":
        return one("out"), one("in")
    return one(direction)  # type: ignore[arg-type]


def format_tree_node(node: TreeNode, *, indent: int = 0) -> list[str]:
    pad = "  " * indent
    suffix = ""
    if node.cycle:
        suffix = "  (cycle)"
    elif node.more:
        suffix = f"  (+{node.more} more)"
    line = f"{pad}{node.name}  ({node.file}:{node.line})  [{node.kind}]{suffix}"
    lines = [line]
    if not node.cycle:
        for child in node.children:
            lines.extend(format_tree_node(child, indent=indent + 1))
    return lines


def format_tree(
    tree: TreeNode | tuple[TreeNode, TreeNode],
    *,
    direction: Direction = "out",
) -> str:
    if direction == "both":
        callees, callers = tree  # type: ignore[misc]
        lines = ["callees:"]
        lines.extend(format_tree_node(callees, indent=0))
        lines.append("callers:")
        lines.extend(format_tree_node(callers, indent=0))
        return "\n".join(lines) + "\n"
    assert isinstance(tree, TreeNode)
    return "\n".join(format_tree_node(tree)) + "\n"


def footer(view: dict[str, Any]) -> str:
    """Coverage footer matching the page banner percentages.

    Always ``graph @ <sha7> · <list> covered`` so the D5 disclosure mapping
    (copy after ``· `` / before trailing `` covered``) stays well-defined even
    when the coverage list is empty.
    """
    sha = str((view.get("meta") or {}).get("gitSha") or "")
    sha7 = sha[:7]
    cov = view.get("coverage") or []
    parts = [
        f"{c['language']} {c['percent']}%"
        for c in sorted(cov, key=lambda x: x["language"])
    ]
    return f"graph @ {sha7} · {' / '.join(parts)} covered"


def clamp_hops(hops: int) -> tuple[int, bool]:
    """Return (effective_hops, was_clamped).

    Values above ``MAX_HOPS`` clamp to the max (design D3). Negative values
    floor at 0 so a bad CLI int cannot invert the depth check.
    """
    if hops > MAX_HOPS:
        return MAX_HOPS, True
    if hops < 0:
        return 0, True
    return hops, False


def render_tree(
    view: dict[str, Any],
    target: str,
    *,
    hops: int = DEFAULT_HOPS,
    direction: Direction = "out",
    include_footer: bool = True,
    err_file=None,
) -> tuple[int, str]:
    """High-level entry used by ``build_atlas.main``.

    Returns ``(exit_code, stdout_text)``. Messages for 2/3 go to ``err_file``.
    """
    err = err_file if err_file is not None else sys.stderr
    hops, clamped = clamp_hops(hops)
    if clamped:
        print(f"note: --hops clamped to {hops}", file=err)

    resolved = resolve_target(view, target)
    if isinstance(resolved, ResolveNotFound):
        print("not found", file=err)
        return 2, ""
    if isinstance(resolved, ResolveAmbiguous):
        for cand in resolved.candidates:
            print(cand, file=err)
        return 3, ""

    tree = walk(view, resolved, hops=hops, direction=direction)
    text = format_tree(tree, direction=direction)
    if include_footer:
        text += footer(view) + "\n"
    return 0, text
