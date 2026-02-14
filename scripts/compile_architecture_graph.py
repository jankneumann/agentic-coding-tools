#!/usr/bin/env python3
"""Thin orchestrator that delegates to Layer 2 insight modules.

Reads per-language intermediate analysis outputs and produces the unified
canonical architecture graph by running the insight modules in sequence
(stages 1-3) then concurrently (stages 4-6):

  Sequential (graph mutations):
    1. graph_builder      — ingest Layer 1 JSON → architecture.graph.json
    2. cross_layer_linker — append frontend→backend api_call edges
    3. db_linker           — append backend→database db_access edges

  Concurrent (read-only analysis from the linked graph):
    4. flow_tracer        — infer cross-layer flows
    5. impact_ranker      — compute high-impact nodes
    6. summary_builder    — compile summary (depends on 4 & 5 outputs)

Optionally emits architecture.sqlite for queryable storage.

Usage:
    python scripts/compile_architecture_graph.py [--input-dir .architecture] \\
        [--output-dir .architecture] [--summary-limit 50] [--sqlite]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "insights"))

from arch_utils.graph_io import load_graph, save_json  # noqa: E402
from insights import cross_layer_linker  # noqa: E402
from insights import db_linker  # noqa: E402
from insights import flow_tracer  # noqa: E402
from insights import graph_builder  # noqa: E402
from insights import impact_ranker  # noqa: E402
from insights import summary_builder  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite output (kept here — not worth a separate module)
# ---------------------------------------------------------------------------


def emit_sqlite(graph: dict[str, Any], output_path: Path) -> None:
    """Write the canonical graph to a SQLite database for queryable storage."""
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(str(output_path))
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            git_sha TEXT NOT NULL,
            tool_versions TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            language TEXT NOT NULL,
            name TEXT NOT NULL,
            file TEXT NOT NULL,
            span_start INTEGER,
            span_end INTEGER,
            tags TEXT,
            signatures TEXT
        );

        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            type TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence TEXT NOT NULL,
            FOREIGN KEY (from_node) REFERENCES nodes(id),
            FOREIGN KEY (to_node) REFERENCES nodes(id)
        );

        CREATE TABLE entrypoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            method TEXT,
            path TEXT,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE INDEX idx_nodes_language ON nodes(language);
        CREATE INDEX idx_nodes_kind ON nodes(kind);
        CREATE INDEX idx_edges_from ON edges(from_node);
        CREATE INDEX idx_edges_to ON edges(to_node);
        CREATE INDEX idx_edges_type ON edges(type);
        CREATE INDEX idx_edges_confidence ON edges(confidence);
        CREATE INDEX idx_entrypoints_kind ON entrypoints(kind);
    """)

    for snap in graph.get("snapshots", []):
        cursor.execute(
            "INSERT INTO snapshots (generated_at, git_sha, tool_versions, notes) VALUES (?, ?, ?, ?)",
            (
                snap["generated_at"],
                snap["git_sha"],
                json.dumps(snap.get("tool_versions", {})),
                json.dumps(snap.get("notes", [])),
            ),
        )

    for node in graph.get("nodes", []):
        span = node.get("span", {})
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, kind, language, name, file, span_start, span_end, tags, signatures) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node["id"],
                node["kind"],
                node["language"],
                node["name"],
                node["file"],
                span.get("start"),
                span.get("end"),
                json.dumps(node.get("tags", [])),
                json.dumps(node.get("signatures", {})),
            ),
        )

    for edge in graph.get("edges", []):
        cursor.execute(
            "INSERT INTO edges (from_node, to_node, type, confidence, evidence) VALUES (?, ?, ?, ?, ?)",
            (edge["from"], edge["to"], edge["type"], edge["confidence"], edge["evidence"]),
        )

    for ep in graph.get("entrypoints", []):
        cursor.execute(
            "INSERT INTO entrypoints (node_id, kind, method, path) VALUES (?, ?, ?, ?)",
            (ep["node_id"], ep["kind"], ep.get("method"), ep.get("path")),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Async insight runners
# ---------------------------------------------------------------------------


async def _run_flow_tracer(graph: dict[str, Any], output_path: Path) -> None:
    """Run flow tracing in a thread to avoid blocking the event loop."""
    def _work() -> list[dict[str, Any]]:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        entrypoints = graph.get("entrypoints", [])
        return flow_tracer.infer_cross_layer_flows(nodes, edges, entrypoints)

    flows = await asyncio.to_thread(_work)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flows": flows,
    }
    save_json(output_path, result)
    logger.info(f"  flow_tracer: {len(flows)} flows → {output_path}")


async def _run_impact_ranker(graph: dict[str, Any], output_path: Path, threshold: int = 5) -> None:
    """Run impact ranking in a thread."""
    def _work() -> list[dict[str, Any]]:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        return impact_ranker.compute_high_impact_nodes(nodes, edges, threshold)

    high_impact = await asyncio.to_thread(_work)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "total_high_impact": len(high_impact),
        "high_impact_nodes": high_impact,
    }
    save_json(output_path, result)
    logger.info(f"  impact_ranker: {len(high_impact)} high-impact nodes → {output_path}")


async def _run_summary_builder(
    graph: dict[str, Any],
    flows_path: Path,
    impact_path: Path,
    output_path: Path,
    summary_limit: int,
) -> None:
    """Run summary generation in a thread (depends on flows + impact results)."""
    def _work() -> dict[str, Any]:
        # Load the flows and impact data produced by the parallel tasks
        flows = _load_json_safe(flows_path, "flows")
        impact_data = _load_json_safe(impact_path, "high_impact_nodes")

        disconnected_eps = summary_builder.find_disconnected_endpoints(graph)
        disconnected_fc = summary_builder.find_disconnected_frontend_calls(graph)

        snapshots = graph.get("snapshots", [])
        git_sha = snapshots[-1].get("git_sha", "unknown") if snapshots else "unknown"
        generated_at = datetime.now(timezone.utc).isoformat()

        return summary_builder.generate_summary(
            graph, flows, disconnected_eps, disconnected_fc,
            impact_data, summary_limit, git_sha, generated_at,
        )

    result = await asyncio.to_thread(_work)
    save_json(output_path, result)
    logger.info(f"  summary_builder: → {output_path}")


def _load_json_safe(path: Path, list_key: str) -> list[dict[str, Any]]:
    """Load a JSON file and extract a list by key, returning [] on failure."""
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data.get(list_key), list):
            return data[list_key]
        return []
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# Orchestration pipeline
# ---------------------------------------------------------------------------


def compile_graph(
    input_dir: Path,
    output_dir: Path,
    summary_limit: int,
    emit_sqlite_flag: bool,
) -> int:
    """Run the full compilation pipeline by delegating to insight modules.

    Returns 0 on success, 1 on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / "architecture.graph.json"

    # ── Sequential stages (graph mutations) ──────────────────────────────

    # Stage 1: Build canonical graph from Layer 1 outputs
    logger.info("Stage 1: Building canonical graph...")
    rc = graph_builder.build_graph(input_dir=input_dir, output_path=graph_path)
    if rc != 0:
        logger.error("graph_builder failed.")
        return rc

    # Stage 2: Cross-language linking — frontend → backend
    logger.info("Stage 2: Cross-language linking (frontend → backend)...")
    rc = cross_layer_linker.run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)
    if rc != 0:
        logger.error("cross_layer_linker failed.")
        return rc

    # Stage 3: Cross-language linking — backend → database
    logger.info("Stage 3: Cross-language linking (backend → database)...")
    rc = db_linker.run(input_dir=input_dir, output_path=graph_path)
    if rc != 0:
        logger.error("db_linker failed.")
        return rc

    # ── Concurrent stages (read-only analysis) ───────────────────────────

    # Load the fully-linked graph once into memory for all read-only stages
    graph = load_graph(graph_path)
    if not graph:
        logger.error("Could not load linked graph.")
        return 1

    flows_path = output_dir / "cross_layer_flows.json"
    impact_path = output_dir / "high_impact_nodes.json"
    summary_path = output_dir / "architecture.summary.json"

    logger.info("Stages 4-6: Running analysis concurrently...")

    async def _run_parallel() -> None:
        # Stages 4 & 5 are fully independent
        flow_task = asyncio.create_task(_run_flow_tracer(graph, flows_path))
        impact_task = asyncio.create_task(_run_impact_ranker(graph, impact_path))

        # Wait for both to complete before running summary (which reads their output)
        await asyncio.gather(flow_task, impact_task)

        # Stage 6 depends on stages 4 & 5
        await _run_summary_builder(graph, flows_path, impact_path, summary_path, summary_limit)

    asyncio.run(_run_parallel())

    # ── Optional outputs ─────────────────────────────────────────────────

    if emit_sqlite_flag:
        logger.info("Emitting SQLite database...")
        sqlite_path = output_dir / "architecture.sqlite"
        emit_sqlite(graph, sqlite_path)
        logger.info(f"Wrote {sqlite_path}")

    logger.info("Compilation complete.")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compile per-language analysis outputs into a unified architecture graph.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing intermediate analysis JSON files (default: .architecture)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory for output files (default: .architecture)",
    )
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=50,
        help="Maximum number of flow entries in the summary (default: 50)",
    )
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Also emit architecture.sqlite for queryable storage",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    return compile_graph(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        summary_limit=args.summary_limit,
        emit_sqlite_flag=args.sqlite,
    )


if __name__ == "__main__":
    sys.exit(main())
