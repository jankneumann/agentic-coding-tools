#!/usr/bin/env python3
"""Graph builder — construct the canonical architecture graph from Layer 1 outputs.

Reads python_analysis.json, ts_analysis.json, and postgres_analysis.json and
produces architecture.graph.json containing nodes, edges, entrypoints, and
snapshot metadata.

Usage:
    python scripts/insights/graph_builder.py --input-dir docs/architecture-analysis --output docs/architecture-analysis/architecture.graph.json
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import DEPENDENCY_EDGE_TYPES, EdgeType  # noqa: E402
from arch_utils.node_id import make_node_id  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Node = dict[str, Any]
Edge = dict[str, Any]
Entrypoint = dict[str, Any]
Snapshot = dict[str, Any]
Graph = dict[str, Any]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def get_git_sha() -> str:
    """Obtain the current HEAD git SHA, returning 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# File loading helpers
# ---------------------------------------------------------------------------


def load_intermediate(path: Path) -> dict[str, Any] | None:
    """Load a JSON intermediate file, returning None if missing or invalid."""
    if not path.exists():
        logger.info(f"  [skip] {path.name} not found")
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        logger.info(f"  [ok]   {path.name} loaded")
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"  [warn] {path.name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Python analysis ingestion
# ---------------------------------------------------------------------------


def ingest_python(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert python_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- modules ---
    for mod in data.get("modules", []):
        nid = make_node_id("py", mod.get("qualified_name", mod.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "module",
            "language": "python",
            "name": mod.get("name", ""),
            "file": mod.get("file", ""),
            "span": mod.get("span", {"start": 1, "end": 1}),
            "tags": mod.get("tags", []),
            "signatures": mod.get("signatures", {}),
        })

    # --- classes ---
    for cls in data.get("classes", []):
        nid = make_node_id("py", cls.get("qualified_name", cls.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "class",
            "language": "python",
            "name": cls.get("name", ""),
            "file": cls.get("file", ""),
            "span": cls.get("span", {"start": 1, "end": 1}),
            "tags": cls.get("tags", []),
            "signatures": cls.get("signatures", {}),
        })

    # --- functions ---
    for func in data.get("functions", []):
        nid = make_node_id("py", func.get("qualified_name", func.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        tags = list(func.get("tags", []))
        node = {
            "id": nid,
            "kind": "function",
            "language": "python",
            "name": func.get("name", ""),
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": tags,
            "signatures": func.get("signatures", {}),
        }
        nodes.append(node)

        # Detect entrypoints from decorators/tags
        for ep in func.get("entrypoints", []):
            ep_entry: Entrypoint = {"node_id": nid, "kind": ep.get("kind", "route")}
            if ep.get("method"):
                ep_entry["method"] = ep["method"]
            if ep.get("path"):
                ep_entry["path"] = ep["path"]
            entrypoints.append(ep_entry)
            if "entrypoint" not in tags:
                tags.append("entrypoint")

    # --- intra-language edges: calls ---
    name_to_nid: dict[str, str] = {}
    for func in data.get("functions", []):
        qn = func.get("qualified_name", func.get("name", ""))
        nid = make_node_id("py", qn)
        name_to_nid[qn] = nid
        short = func.get("name", "")
        if short and short not in name_to_nid:
            name_to_nid[short] = nid

    for func in data.get("functions", []):
        from_qn = func.get("qualified_name", func.get("name", ""))
        from_id = make_node_id("py", from_qn)
        for call_name in func.get("calls", []):
            to_id = name_to_nid.get(call_name)
            if to_id and to_id != from_id:
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "type": EdgeType.CALL,
                    "confidence": "high",
                    "evidence": f"ast:call:{call_name}",
                })

    # --- intra-language edges: imports ---
    for edge in data.get("import_graph", data.get("import_edges", [])):
        from_id = make_node_id("py", edge.get("from", ""))
        to_id = make_node_id("py", edge.get("to", ""))
        if from_id != to_id:
            edges.append({
                "from": from_id,
                "to": to_id,
                "type": EdgeType.IMPORT,
                "confidence": "high",
                "evidence": "ast:import",
            })

    # --- intra-language edges: db_access ---
    for da in data.get("db_access", data.get("db_access_edges", [])):
        func_qn = da.get("function", da.get("from", ""))
        from_id = make_node_id("py", func_qn)
        for table_name in da.get("tables", []):
            if not table_name:
                continue
            to_id = make_node_id(
                "pg", f"public.{table_name}" if "." not in table_name else table_name
            )
            edges.append({
                "from": from_id,
                "to": to_id,
                "type": EdgeType.DB_ACCESS,
                "confidence": da.get("confidence", "medium"),
                "evidence": f"orm:{da.get('pattern', 'model_usage')}",
            })

    # --- entrypoints from entry_points array ---
    for ep in data.get("entry_points", []):
        func_qn = ep.get("function", "")
        func_nid = make_node_id("py", func_qn)
        if func_nid in node_ids:
            ep_entry = {"node_id": func_nid, "kind": ep.get("kind", "route")}
            if ep.get("method"):
                ep_entry["method"] = ep["method"]
            if ep.get("path"):
                ep_entry["path"] = ep["path"]
            entrypoints.append(ep_entry)

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# TypeScript analysis ingestion
# ---------------------------------------------------------------------------


def ingest_typescript(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert ts_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- modules ---
    for mod in data.get("modules", []):
        nid = make_node_id("ts", mod.get("qualified_name", mod.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "module",
            "language": "typescript",
            "name": mod.get("name", ""),
            "file": mod.get("file", ""),
            "span": mod.get("span", {"start": 1, "end": 1}),
            "tags": mod.get("tags", []),
            "signatures": mod.get("signatures", {}),
        })

    # --- components ---
    for comp in data.get("components", []):
        nid = make_node_id("ts", comp.get("qualified_name", comp.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "component",
            "language": "typescript",
            "name": comp.get("name", ""),
            "file": comp.get("file", ""),
            "span": comp.get("span", {"start": 1, "end": 1}),
            "tags": comp.get("tags", []),
            "signatures": comp.get("signatures", {}),
        })

    # --- hooks ---
    for hook in data.get("hooks", []):
        nid = make_node_id("ts", hook.get("qualified_name", hook.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "hook",
            "language": "typescript",
            "name": hook.get("name", ""),
            "file": hook.get("file", ""),
            "span": hook.get("span", {"start": 1, "end": 1}),
            "tags": hook.get("tags", []),
            "signatures": hook.get("signatures", {}),
        })

    # --- functions ---
    for func in data.get("functions", []):
        nid = make_node_id("ts", func.get("qualified_name", func.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "function",
            "language": "typescript",
            "name": func.get("name", ""),
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": func.get("tags", []),
            "signatures": func.get("signatures", {}),
        })

    # --- intra-language edges: imports ---
    for edge in data.get("import_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": EdgeType.IMPORT,
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:import"),
        })

    # --- intra-language edges: component_child ---
    for edge in data.get("component_child_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": EdgeType.COMPONENT_CHILD,
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "jsx:child_component"),
        })

    # --- intra-language edges: hook_usage ---
    for edge in data.get("hook_usage_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": EdgeType.HOOK_USAGE,
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:hook_call"),
        })

    # --- intra-language edges: calls ---
    for edge in data.get("call_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": EdgeType.CALL,
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:call"),
        })

    # --- entrypoints ---
    for ep in data.get("entrypoints", []):
        nid = make_node_id("ts", ep.get("qualified_name", ep.get("node_id", "")))
        ep_entry: Entrypoint = {"node_id": nid, "kind": ep.get("kind", "event_handler")}
        if ep.get("method"):
            ep_entry["method"] = ep["method"]
        if ep.get("path"):
            ep_entry["path"] = ep["path"]
        entrypoints.append(ep_entry)

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# Postgres analysis ingestion
# ---------------------------------------------------------------------------


def ingest_postgres(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert postgres_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- tables ---
    for table in data.get("tables", []):
        schema = table.get("schema", "public")
        table_name = table.get("name", "")
        qualified = f"{schema}.{table_name}"
        nid = make_node_id("pg", qualified)
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "table",
            "language": "sql",
            "name": table_name,
            "file": table.get("file", table.get("migration_file", "")),
            "span": table.get("span", {"start": 1, "end": 1}),
            "tags": table.get("tags", []),
            "signatures": table.get("signatures", {}),
        })

        # --- columns as nodes (optional, if present) ---
        for col in table.get("columns", []):
            col_qualified = f"{qualified}.{col.get('name', '')}"
            col_nid = make_node_id("pg", col_qualified)
            if col_nid in node_ids:
                continue
            node_ids.add(col_nid)
            nodes.append({
                "id": col_nid,
                "kind": "column",
                "language": "sql",
                "name": col.get("name", ""),
                "file": table.get("file", table.get("migration_file", "")),
                "span": col.get("span", {"start": 1, "end": 1}),
                "tags": col.get("tags", []),
                "signatures": col.get("signatures", {"type": col.get("type", "")}),
            })

    # --- indexes ---
    for idx in data.get("indexes", []):
        nid = make_node_id("pg", idx.get("qualified_name", idx.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "index",
            "language": "sql",
            "name": idx.get("name", ""),
            "file": idx.get("file", ""),
            "span": idx.get("span", {"start": 1, "end": 1}),
            "tags": idx.get("tags", []),
            "signatures": idx.get("signatures", {}),
        })

    # --- stored functions ---
    for func in data.get("stored_functions", []):
        schema = func.get("schema", "public")
        func_name = func.get("name", "")
        qualified = f"{schema}.{func_name}"
        nid = make_node_id("pg", qualified)
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "stored_function",
            "language": "sql",
            "name": func_name,
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": func.get("tags", []),
            "signatures": func.get("signatures", {}),
        })

    # --- triggers ---
    for trigger in data.get("triggers", []):
        nid = make_node_id("pg", trigger.get("qualified_name", trigger.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "trigger",
            "language": "sql",
            "name": trigger.get("name", ""),
            "file": trigger.get("file", ""),
            "span": trigger.get("span", {"start": 1, "end": 1}),
            "tags": trigger.get("tags", []),
            "signatures": trigger.get("signatures", {}),
        })

    # --- migrations as entrypoints ---
    for migration in data.get("migrations", []):
        nid = make_node_id("pg", migration.get("qualified_name", migration.get("name", "")))
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append({
                "id": nid,
                "kind": "migration",
                "language": "sql",
                "name": migration.get("name", ""),
                "file": migration.get("file", ""),
                "span": migration.get("span", {"start": 1, "end": 1}),
                "tags": migration.get("tags", []),
                "signatures": migration.get("signatures", {}),
            })
        entrypoints.append({
            "node_id": nid,
            "kind": "migration",
        })

    # --- foreign key edges ---
    for fk in data.get("foreign_keys", []):
        from_table = fk.get("from_table", "")
        to_table = fk.get("to_table", "")
        # from_table / to_table are already schema-qualified (e.g. "public.users")
        # from analyze_postgres.py's _qualify() helper — do NOT prepend schema again
        from_id = make_node_id("pg", from_table)
        to_id = make_node_id("pg", to_table)
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": EdgeType.FK_REFERENCE,
            "confidence": "high",
            "evidence": fk.get("evidence", f"fk:{fk.get('constraint_name', 'unnamed')}"),
        })

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------


def deduplicate_nodes(nodes: list[Node]) -> list[Node]:
    """Remove duplicate nodes, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[Node] = []
    for node in nodes:
        if node["id"] not in seen:
            seen.add(node["id"])
            unique.append(node)
    return unique


_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def deduplicate_edges(edges: list[Edge]) -> list[Edge]:
    """Remove duplicate edges (same from, to, type), keeping highest confidence."""
    best: dict[tuple[str, str, str], Edge] = {}
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        existing = best.get(key)
        if existing is None or _CONFIDENCE_RANK.get(
            edge.get("confidence", "low"), 0
        ) > _CONFIDENCE_RANK.get(existing.get("confidence", "low"), 0):
            best[key] = edge
    return list(best.values())


# ---------------------------------------------------------------------------
# Edge validation
# ---------------------------------------------------------------------------


def validate_edges(edges: list[Edge], node_ids: set[str]) -> list[Edge]:
    """Remove edges that reference nodes not in the graph."""
    valid: list[Edge] = []
    for edge in edges:
        if edge["from"] in node_ids and edge["to"] in node_ids:
            valid.append(edge)
        else:
            missing = []
            if edge["from"] not in node_ids:
                missing.append(f"from={edge['from']}")
            if edge["to"] not in node_ids:
                missing.append(f"to={edge['to']}")
            logger.warning(
                f"  [warn] dropping edge {edge['from']} -> {edge['to']}: "
                f"missing node(s): {', '.join(missing)}"
            )
    return valid


# ---------------------------------------------------------------------------
# Main build pipeline
# ---------------------------------------------------------------------------


def build_graph(
    input_dir: Path,
    output_path: Path,
    *,
    emit_sqlite: bool = False,
) -> int:
    """Run the graph build pipeline. Returns 0 on success, 1 on failure."""
    logger.info("Loading intermediate analysis files...")

    py_data = load_intermediate(input_dir / "python_analysis.json")
    ts_data = load_intermediate(input_dir / "ts_analysis.json")
    pg_data = load_intermediate(input_dir / "postgres_analysis.json")

    if py_data is None and ts_data is None and pg_data is None:
        logger.error(
            "No intermediate analysis files found. "
            "Run the per-language analyzers first."
        )
        return 1

    notes: list[str] = []
    if py_data is None:
        notes.append("Python analysis not available")
    if ts_data is None:
        notes.append("TypeScript analysis not available")
    if pg_data is None:
        notes.append("Postgres analysis not available")

    # --- Ingest per-language data ---
    logger.info("Ingesting per-language data...")

    all_nodes: list[Node] = []
    all_edges: list[Edge] = []
    all_entrypoints: list[Entrypoint] = []

    if py_data is not None:
        nodes, edges, entrypoints = ingest_python(py_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)

    if ts_data is not None:
        nodes, edges, entrypoints = ingest_typescript(ts_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)

    if pg_data is not None:
        nodes, edges, entrypoints = ingest_postgres(pg_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)

    # --- Deduplicate ---
    all_nodes = deduplicate_nodes(all_nodes)
    all_edges = deduplicate_edges(all_edges)

    # Validate edges: drop any that reference missing nodes
    node_id_set = {n["id"] for n in all_nodes}
    all_edges = validate_edges(all_edges, node_id_set)

    # --- Build snapshot ---
    git_sha = get_git_sha()
    generated_at = datetime.now(timezone.utc).isoformat()

    tool_versions: dict[str, str] = {"graph_builder": "2.0.0"}
    for label, data in [("python_analyzer", py_data), ("ts_analyzer", ts_data), ("postgres_analyzer", pg_data)]:
        if data is not None and "tool_version" in data:
            tool_versions[label] = data["tool_version"]

    snapshot: Snapshot = {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "tool_versions": tool_versions,
        "notes": notes,
    }

    # --- Assemble the canonical graph ---
    graph: Graph = {
        "snapshots": [snapshot],
        "nodes": all_nodes,
        "edges": all_edges,
        "entrypoints": all_entrypoints,
    }

    # --- Write output ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(graph, f, indent=2)
    logger.info(f"Wrote {output_path}")

    logger.info(
        f"Graph build complete: "
        f"{len(all_nodes)} nodes, {len(all_edges)} edges, "
        f"{len(all_entrypoints)} entrypoints"
    )
    if notes:
        logger.info(f"  Notes: {'; '.join(notes)}")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Build canonical architecture graph from Layer 1 analysis outputs.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("docs/architecture-analysis"),
        help="Directory containing intermediate analysis JSON files (default: docs/architecture-analysis)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/architecture.graph.json"),
        help="Output path for the canonical graph (default: docs/architecture-analysis/architecture.graph.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    return build_graph(input_dir=args.input_dir, output_path=args.output)


if __name__ == "__main__":
    sys.exit(main())
