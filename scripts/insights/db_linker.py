#!/usr/bin/env python3
"""DB linker — match Python ORM/SQL patterns to Postgres tables and append edges.

Reads the canonical architecture graph along with python_analysis.json and
postgres_analysis.json, discovers backend-to-database relationships via ORM
model usage and SQL pattern matching, and writes the updated graph back.

Usage:
    python scripts/insights/db_linker.py --input-dir .architecture --output .architecture/architecture.graph.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import EdgeType  # noqa: E402
from arch_utils.graph_io import load_graph, save_json  # noqa: E402
from arch_utils.node_id import make_node_id  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Edge = dict[str, Any]


# ---------------------------------------------------------------------------
# Edge deduplication
# ---------------------------------------------------------------------------

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
# Backend-to-database linking
# ---------------------------------------------------------------------------


def link_backend_to_database(
    py_data: dict[str, Any] | None,
    pg_data: dict[str, Any] | None,
) -> list[Edge]:
    """Match Python ORM model usage and SQL patterns to DB table names.

    Returns a list of backend->database edges with db_access type.
    """
    if py_data is None or pg_data is None:
        return []
    edges: list[Edge] = []
    table_names: set[str] = set()
    table_qualified: dict[str, str] = {}
    for table in pg_data.get("tables", []):
        schema = table.get("schema", "public")
        name = table.get("name", "")
        qualified = f"{schema}.{name}"
        table_names.add(name.lower())
        table_qualified[name.lower()] = qualified

    existing_db_edges: set[tuple[str, str]] = set()
    for da in py_data.get("db_access", py_data.get("db_access_edges", [])):
        from_qn = da.get("function", da.get("from", ""))
        for table in da.get("tables", []):
            existing_db_edges.add((from_qn, table.lower()))

    for func in py_data.get("functions", []):
        func_qn = func.get("qualified_name", func.get("name", ""))
        func_nid = make_node_id("py", func_qn)
        for table_ref in func.get("db_tables", []):
            table_lower = table_ref.lower()
            if (func_qn, table_lower) in existing_db_edges:
                continue
            if table_lower in table_qualified:
                table_nid = make_node_id("pg", table_qualified[table_lower])
                edges.append({
                    "from": func_nid,
                    "to": table_nid,
                    "type": EdgeType.DB_ACCESS,
                    "confidence": "medium",
                    "evidence": f"table_ref:{table_ref}",
                })
        for sql_pattern in func.get("sql_patterns", []):
            sql_lower = sql_pattern.lower()
            for table_name, qualified in table_qualified.items():
                if table_name in sql_lower and (func_qn, table_name) not in existing_db_edges:
                    table_nid = make_node_id("pg", qualified)
                    edges.append({
                        "from": func_nid,
                        "to": table_nid,
                        "type": EdgeType.DB_ACCESS,
                        "confidence": "low",
                        "evidence": f"sql_pattern:{sql_pattern[:80]}",
                    })
                    existing_db_edges.add((func_qn, table_name))
    return edges


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run(input_dir: Path, output_path: Path) -> int:
    """Load graph and analysis files, link backend to database, write updated graph."""
    logger.info("Loading architecture graph and analysis files...")

    graph = load_graph(input_dir / "architecture.graph.json")
    if not graph:
        logger.error(
            "architecture.graph.json not found or empty. "
            "Run graph_builder.py first."
        )
        return 1

    py_data = load_graph(input_dir / "python_analysis.json", quiet=True) or None
    pg_data = load_graph(input_dir / "postgres_analysis.json", quiet=True) or None

    if py_data is None or pg_data is None:
        missing = []
        if py_data is None:
            missing.append("python_analysis.json")
        if pg_data is None:
            missing.append("postgres_analysis.json")
        logger.info(
            f"  [skip] DB linking requires both python and postgres analysis; "
            f"missing: {', '.join(missing)}"
        )
        return 0

    # --- Link backend to database ---
    logger.info("Linking backend functions to database tables...")
    new_edges = link_backend_to_database(py_data, pg_data)
    logger.info(f"  Found {len(new_edges)} new backend->database edge(s)")

    if not new_edges:
        logger.info("No new edges to add. Graph unchanged.")
        return 0

    # --- Append and deduplicate ---
    existing_edges: list[Edge] = graph.get("edges", [])
    all_edges = existing_edges + new_edges
    all_edges = deduplicate_edges(all_edges)

    # --- Validate edges against node IDs ---
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    all_edges = validate_edges(all_edges, node_ids)

    graph["edges"] = all_edges

    # --- Write updated graph ---
    save_json(output_path, graph)
    logger.info(
        f"Wrote {output_path} "
        f"({len(graph.get('nodes', []))} nodes, {len(all_edges)} edges)"
    )

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Link Python backend functions to Postgres tables via ORM model "
            "usage and SQL pattern matching, appending db_access edges to the "
            "canonical architecture graph."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing the graph and analysis JSON files (default: .architecture)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/architecture.graph.json"),
        help="Output path for the updated graph (default: .architecture/architecture.graph.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    return run(input_dir=args.input_dir, output_path=args.output)


if __name__ == "__main__":
    sys.exit(main())
