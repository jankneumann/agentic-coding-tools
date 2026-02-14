#!/usr/bin/env python3
"""Generate Mermaid diagrams from the canonical architecture graph at multiple zoom levels.

Reads architecture.graph.json and produces:
  - containers.mmd          — Container view (frontend / backend / DB / external)
  - backend_components.mmd  — Backend component view (Python packages with dependency edges)
  - frontend_components.mmd — Frontend component view (TS directories with import edges)
  - db_erd.mmd              — Database ERD (tables with FK relationships)
  - feature_slice.mmd/json  — Feature slice subgraph (when --feature-files given)

Usage:
    python scripts/generate_views.py [OPTIONS]

Options:
    --graph PATH          Path to architecture.graph.json
                          (default: .architecture/architecture.graph.json)
    --output-dir PATH     Output directory for generated views
                          (default: .architecture/views)
    --feature-files LIST  Comma-separated file paths or glob patterns for
                          feature slice extraction
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

Graph = dict[str, Any]


def load_graph(path: Path) -> Graph:
    """Load and return the canonical architecture graph JSON."""
    if not path.exists():
        print(f"Error: graph file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LANGUAGE_CONTAINER: dict[str, str] = {
    "python": "Backend",
    "typescript": "Frontend",
    "sql": "Database",
}

# Mermaid-safe identifier: replace non-alphanumeric chars with underscores.
def _mermaid_id(raw: str) -> str:
    """Convert an arbitrary string into a safe Mermaid node identifier."""
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)


def _quote(label: str) -> str:
    """Wrap a label in double-quotes for Mermaid, escaping inner quotes."""
    return '"' + label.replace('"', "#quot;") + '"'


def _node_index(graph: Graph) -> dict[str, dict]:
    """Build a dict mapping node id -> node object."""
    return {n["id"]: n for n in graph.get("nodes", [])}


def _top_level_package(file_path: str) -> str:
    """Extract the top-level package from a Python file path.

    Examples:
        backend/services/user.py  -> backend.services
        backend/api/routes.py     -> backend.api
        utils.py                  -> utils
    """
    parts = Path(file_path).with_suffix("").parts
    if len(parts) <= 1:
        return parts[0] if parts else "root"
    # Use the first two path components as the package identifier
    return ".".join(parts[:2])


def _top_level_directory(file_path: str) -> str:
    """Extract the top-level directory from a TypeScript file path.

    Examples:
        src/components/UserProfile.tsx -> src/components
        src/hooks/useAuth.ts           -> src/hooks
        index.ts                       -> root
    """
    parts = Path(file_path).parts
    if len(parts) <= 1:
        return "root"
    return "/".join(parts[:2])


# ---------------------------------------------------------------------------
# Container View
# ---------------------------------------------------------------------------

def generate_container_view(graph: Graph) -> str:
    """Generate Mermaid flowchart showing high-level containers with connections.

    Groups nodes by language into containers (python -> Backend,
    typescript -> Frontend, sql -> Database).  Edges that cross container
    boundaries are shown as arrows between the containers.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_idx = _node_index(graph)

    # Determine which container each node belongs to.
    node_container: dict[str, str] = {}
    containers_seen: set[str] = set()
    for node in nodes:
        container = LANGUAGE_CONTAINER.get(node["language"], "External")
        node_container[node["id"]] = container
        containers_seen.add(container)

    # Collect cross-container edges (deduplicated as container pairs).
    cross_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for edge in edges:
        src_container = node_container.get(edge["from"])
        dst_container = node_container.get(edge["to"])
        if src_container and dst_container and src_container != dst_container:
            cross_edges[(src_container, dst_container)].add(edge["type"])

    # Build Mermaid output.
    lines: list[str] = ["flowchart TB"]

    # Container descriptions with node counts.
    container_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        container_counts[node_container[node["id"]]] += 1

    for container in sorted(containers_seen):
        count = container_counts[container]
        cid = _mermaid_id(container)
        lines.append(f"    {cid}[{_quote(f'{container} ({count} nodes)')}]")

    # Cross-container edges.
    for (src, dst), edge_types in sorted(cross_edges.items()):
        label = ", ".join(sorted(edge_types))
        src_id = _mermaid_id(src)
        dst_id = _mermaid_id(dst)
        lines.append(f"    {src_id} -->|{_quote(label)}| {dst_id}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Backend Component View
# ---------------------------------------------------------------------------

def generate_backend_component_view(graph: Graph) -> str:
    """Generate Mermaid flowchart for Python packages with dependency edges.

    Groups Python modules by their top-level package and shows import edges
    between packages.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_idx = _node_index(graph)

    # Filter to Python nodes.
    py_nodes = [n for n in nodes if n["language"] == "python"]
    if not py_nodes:
        return "flowchart TB\n    empty[\"No Python nodes found\"]\n"

    # Map node id -> package.
    node_package: dict[str, str] = {}
    package_nodes: dict[str, list[str]] = defaultdict(list)
    for node in py_nodes:
        pkg = _top_level_package(node["file"])
        node_package[node["id"]] = pkg
        package_nodes[pkg].append(node["name"])

    # Collect inter-package edges (import and call types).
    pkg_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    relevant_types = {"import", "call", "db_access"}
    for edge in edges:
        src_pkg = node_package.get(edge["from"])
        dst_pkg = node_package.get(edge["to"])
        if (
            src_pkg
            and dst_pkg
            and src_pkg != dst_pkg
            and edge["type"] in relevant_types
        ):
            pkg_edges[(src_pkg, dst_pkg)].add(edge["type"])

    # Build Mermaid.
    lines: list[str] = ["flowchart TB"]

    for pkg in sorted(package_nodes):
        pid = _mermaid_id(pkg)
        count = len(package_nodes[pkg])
        lines.append(f"    {pid}[{_quote(f'{pkg} ({count} symbols)')}]")

    for (src, dst), edge_types in sorted(pkg_edges.items()):
        label = ", ".join(sorted(edge_types))
        lines.append(
            f"    {_mermaid_id(src)} -->|{_quote(label)}| {_mermaid_id(dst)}"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Frontend Component View
# ---------------------------------------------------------------------------

def generate_frontend_component_view(graph: Graph) -> str:
    """Generate Mermaid flowchart for TypeScript modules grouped by directory.

    Groups TS modules by their top-level directory and shows import edges
    between directories.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Filter to TypeScript nodes.
    ts_nodes = [n for n in nodes if n["language"] == "typescript"]
    if not ts_nodes:
        return "flowchart TB\n    empty[\"No TypeScript nodes found\"]\n"

    # Map node id -> directory.
    node_dir: dict[str, str] = {}
    dir_nodes: dict[str, list[str]] = defaultdict(list)
    for node in ts_nodes:
        d = _top_level_directory(node["file"])
        node_dir[node["id"]] = d
        dir_nodes[d].append(node["name"])

    # Collect inter-directory edges.
    dir_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    relevant_types = {"import", "component_child", "hook_usage", "call"}
    for edge in edges:
        src_dir = node_dir.get(edge["from"])
        dst_dir = node_dir.get(edge["to"])
        if (
            src_dir
            and dst_dir
            and src_dir != dst_dir
            and edge["type"] in relevant_types
        ):
            dir_edges[(src_dir, dst_dir)].add(edge["type"])

    # Build Mermaid.
    lines: list[str] = ["flowchart TB"]

    for d in sorted(dir_nodes):
        did = _mermaid_id(d)
        count = len(dir_nodes[d])
        lines.append(f"    {did}[{_quote(f'{d} ({count} symbols)')}]")

    for (src, dst), edge_types in sorted(dir_edges.items()):
        label = ", ".join(sorted(edge_types))
        lines.append(
            f"    {_mermaid_id(src)} -->|{_quote(label)}| {_mermaid_id(dst)}"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# DB ERD
# ---------------------------------------------------------------------------

def _column_type_str(sig: dict) -> str:
    """Extract a display type string from column signatures."""
    col_type = sig.get("data_type", sig.get("type", ""))
    nullable = sig.get("nullable", True)
    pk = sig.get("primary_key", False)
    suffix = ""
    if pk:
        suffix += " PK"
    if not nullable:
        suffix += " NOT NULL"
    return f"{col_type}{suffix}".strip()


def generate_db_erd(graph: Graph) -> str:
    """Generate Mermaid erDiagram for database tables with FK relationships.

    Shows tables with their columns and FK relationships as lines with
    cardinality markers.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_idx = _node_index(graph)

    # Collect table nodes and column nodes.
    table_nodes = [n for n in nodes if n["language"] == "sql" and n["kind"] == "table"]
    column_nodes = [n for n in nodes if n["language"] == "sql" and n["kind"] == "column"]

    if not table_nodes:
        return "erDiagram\n    EMPTY {\n        string note \"No tables found\"\n    }\n"

    # Map table name -> columns.
    # Columns can be associated via their id prefix or via parent edges.
    table_columns: dict[str, list[dict]] = defaultdict(list)
    for col in column_nodes:
        # Column IDs follow pattern pg:schema.table.column
        parts = col["id"].split(":")
        if len(parts) == 2:
            qual_name = parts[1]  # e.g., public.users.email
            name_parts = qual_name.split(".")
            if len(name_parts) >= 2:
                table_key = ".".join(name_parts[:-1])  # e.g., public.users
                table_columns[table_key].append(col)

    # Also try matching columns to tables by file path.
    table_id_to_name: dict[str, str] = {}
    for t in table_nodes:
        table_id_to_name[t["id"]] = t["name"]
        # Ensure table qualified name is indexed.
        prefix, qual = t["id"].split(":", 1) if ":" in t["id"] else ("", t["id"])
        table_id_to_name[t["id"]] = qual

    # Collect FK relationships.
    fk_edges: list[dict] = [
        e for e in edges if e["type"] == "fk_reference"
    ]

    # Derive table relationships from FK edges.
    # FK edge goes from the referencing column/table to the referenced column/table.
    relationships: list[tuple[str, str, str]] = []  # (from_table, to_table, label)
    for fk in fk_edges:
        from_node = node_idx.get(fk["from"])
        to_node = node_idx.get(fk["to"])
        if not from_node or not to_node:
            continue

        # Determine table names from node ids.
        from_table = _table_name_from_id(fk["from"])
        to_table = _table_name_from_id(fk["to"])
        if from_table and to_table:
            label = fk.get("evidence", "FK")
            relationships.append((from_table, to_table, label))

    # Build erDiagram.
    lines: list[str] = ["erDiagram"]

    for table in sorted(table_nodes, key=lambda t: t["name"]):
        prefix, qual = table["id"].split(":", 1) if ":" in table["id"] else ("", table["id"])
        safe_name = _mermaid_id(table["name"])
        cols = table_columns.get(qual, [])

        lines.append(f"    {safe_name} {{")
        if cols:
            for col in sorted(cols, key=lambda c: c["name"]):
                sig = col.get("signatures", {})
                col_type = sig.get("data_type", sig.get("type", "string"))
                # Mermaid erDiagram column format: type name "comment"
                col_safe = _mermaid_id(col["name"])
                pk_marker = ""
                if sig.get("primary_key"):
                    pk_marker = " PK"
                elif _is_fk_column(col["id"], fk_edges):
                    pk_marker = " FK"
                lines.append(
                    f"        {_mermaid_id(col_type)} {col_safe}{pk_marker}"
                )
        else:
            # If no columns found, add a placeholder from signatures.
            sig = table.get("signatures", {})
            columns_meta = sig.get("columns", [])
            if isinstance(columns_meta, list):
                for col_entry in columns_meta:
                    if isinstance(col_entry, dict):
                        cname = col_entry.get("name", "unknown")
                        ctype = col_entry.get("type", col_entry.get("data_type", "string"))
                        pk_marker = ""
                        if col_entry.get("primary_key"):
                            pk_marker = " PK"
                        lines.append(
                            f"        {_mermaid_id(ctype)} {_mermaid_id(cname)}{pk_marker}"
                        )
            elif isinstance(columns_meta, dict):
                for cname, ctype in columns_meta.items():
                    lines.append(
                        f"        {_mermaid_id(str(ctype))} {_mermaid_id(cname)}"
                    )
        lines.append("    }")

    # Relationships.
    seen_rels: set[tuple[str, str]] = set()
    for from_table, to_table, label in relationships:
        from_safe = _mermaid_id(from_table)
        to_safe = _mermaid_id(to_table)
        rel_key = (from_safe, to_safe)
        if rel_key in seen_rels:
            continue
        seen_rels.add(rel_key)
        # Use }o--|| for many-to-one (FK referencing a PK).
        lines.append(f"    {from_safe} }}o--|| {to_safe} : {_quote(label)}")

    return "\n".join(lines) + "\n"


def _table_name_from_id(node_id: str) -> str | None:
    """Extract the table name from a node ID like pg:public.users or pg:public.users.email."""
    if ":" not in node_id:
        return None
    qual = node_id.split(":", 1)[1]
    parts = qual.split(".")
    # For table nodes: pg:public.users -> parts = [public, users]
    # For column nodes: pg:public.users.email -> parts = [public, users, email]
    if len(parts) >= 2:
        return parts[-1] if len(parts) == 2 else parts[-2]
    return parts[0] if parts else None


def _is_fk_column(col_id: str, fk_edges: list[dict]) -> bool:
    """Check whether a column node is the source of an FK reference."""
    return any(e["from"] == col_id for e in fk_edges)


# ---------------------------------------------------------------------------
# Feature Slice View
# ---------------------------------------------------------------------------

def _matches_any_pattern(file_path: str, patterns: list[str]) -> bool:
    """Check whether a file path matches any of the given patterns.

    Patterns can be exact file paths or glob patterns.
    """
    for pattern in patterns:
        if file_path == pattern:
            return True
        if fnmatch.fnmatch(file_path, pattern):
            return True
    return False


def generate_feature_slice(
    graph: Graph,
    feature_files: list[str],
) -> tuple[str, dict]:
    """Extract and render the subgraph relevant to a set of files.

    Returns (mermaid_str, subgraph_json_dict).
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Find nodes whose file matches any of the feature patterns.
    matched_node_ids: set[str] = set()
    for node in nodes:
        if _matches_any_pattern(node["file"], feature_files):
            matched_node_ids.add(node["id"])

    # Expand to include nodes connected by one hop (direct neighbors).
    neighbor_ids: set[str] = set()
    for edge in edges:
        if edge["from"] in matched_node_ids:
            neighbor_ids.add(edge["to"])
        if edge["to"] in matched_node_ids:
            neighbor_ids.add(edge["from"])

    all_relevant_ids = matched_node_ids | neighbor_ids

    # Extract relevant nodes and edges.
    relevant_nodes = [n for n in nodes if n["id"] in all_relevant_ids]
    relevant_edges = [
        e for e in edges
        if e["from"] in all_relevant_ids and e["to"] in all_relevant_ids
    ]

    # Build subgraph JSON.
    subgraph: dict[str, Any] = {
        "feature_files": feature_files,
        "nodes": relevant_nodes,
        "edges": relevant_edges,
        "matched_file_nodes": sorted(matched_node_ids),
        "neighbor_nodes": sorted(neighbor_ids - matched_node_ids),
    }

    # Build Mermaid diagram.
    if not relevant_nodes:
        mermaid = (
            "flowchart TB\n"
            "    empty[\"No nodes match the given feature files\"]\n"
        )
        return mermaid, subgraph

    lines: list[str] = ["flowchart TB"]

    # Group relevant nodes by container for visual clarity.
    container_groups: dict[str, list[dict]] = defaultdict(list)
    for node in relevant_nodes:
        container = LANGUAGE_CONTAINER.get(node["language"], "External")
        container_groups[container].append(node)

    for container in sorted(container_groups):
        cid = _mermaid_id(container)
        lines.append(f"    subgraph {cid}[{_quote(container)}]")
        for node in sorted(container_groups[container], key=lambda n: n["id"]):
            nid = _mermaid_id(node["id"])
            label = node["name"]
            # Mark nodes that directly match the feature files.
            if node["id"] in matched_node_ids:
                label = f"{label} *"
            lines.append(f"        {nid}[{_quote(label)}]")
        lines.append("    end")

    # Edges.
    for edge in relevant_edges:
        src = _mermaid_id(edge["from"])
        dst = _mermaid_id(edge["to"])
        lines.append(f"    {src} -->|{_quote(edge['type'])}| {dst}")

    # Style matched nodes differently.
    for node_id in sorted(matched_node_ids):
        nid = _mermaid_id(node_id)
        lines.append(f"    style {nid} fill:#f9f,stroke:#333,stroke-width:2px")

    mermaid = "\n".join(lines) + "\n"
    return mermaid, subgraph


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_view(output_dir: Path, filename: str, content: str) -> Path:
    """Write a view file and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Mermaid diagrams from the canonical architecture graph.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path(".architecture/architecture.graph.json"),
        help="Path to architecture.graph.json (default: .architecture/architecture.graph.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".architecture/views"),
        help="Output directory for generated views (default: .architecture/views)",
    )
    parser.add_argument(
        "--feature-files",
        type=str,
        default=None,
        help="Comma-separated file paths or glob patterns for feature slice extraction",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    graph = load_graph(args.graph)
    output_dir: Path = args.output_dir
    generated: list[Path] = []

    # Container view.
    content = generate_container_view(graph)
    p = write_view(output_dir, "containers.mmd", content)
    generated.append(p)

    # Backend component view.
    content = generate_backend_component_view(graph)
    p = write_view(output_dir, "backend_components.mmd", content)
    generated.append(p)

    # Frontend component view.
    content = generate_frontend_component_view(graph)
    p = write_view(output_dir, "frontend_components.mmd", content)
    generated.append(p)

    # Database ERD.
    content = generate_db_erd(graph)
    p = write_view(output_dir, "db_erd.mmd", content)
    generated.append(p)

    # Feature slice (optional).
    if args.feature_files:
        feature_list = [f.strip() for f in args.feature_files.split(",") if f.strip()]
        if feature_list:
            mermaid, subgraph_json = generate_feature_slice(graph, feature_list)
            p = write_view(output_dir, "feature_slice.mmd", mermaid)
            generated.append(p)
            json_path = output_dir / "feature_slice.json"
            json_path.write_text(
                json.dumps(subgraph_json, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            generated.append(json_path)

    # Report results.
    print(f"Generated {len(generated)} view(s) in {output_dir}/")
    for p in generated:
        print(f"  - {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
