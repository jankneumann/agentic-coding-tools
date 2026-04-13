"""Tests for insights/graph_builder.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_build_graph_produces_valid_output(input_dir: Path) -> None:
    """graph_builder should produce architecture.graph.json with correct schema."""
    from insights.graph_builder import build_graph

    output = input_dir / "architecture.graph.json"
    rc = build_graph(input_dir=input_dir, output_path=output)

    assert rc == 0
    assert output.exists()

    with open(output) as f:
        graph = json.load(f)

    assert "nodes" in graph
    assert "edges" in graph
    assert "entrypoints" in graph
    assert "snapshots" in graph
    assert len(graph["nodes"]) > 0
    assert len(graph["snapshots"]) == 1


def test_build_graph_ingests_python_nodes(input_dir: Path) -> None:
    """graph_builder should create nodes from python_analysis.json."""
    from insights.graph_builder import build_graph

    output = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=output)

    with open(output) as f:
        graph = json.load(f)

    python_nodes = [n for n in graph["nodes"] if n["language"] == "python"]
    assert len(python_nodes) >= 2  # at least modules + functions

    node_ids = {n["id"] for n in graph["nodes"]}
    # Check that Python nodes use "py:" prefix
    assert any(nid.startswith("py:") for nid in node_ids)


def test_build_graph_ingests_typescript_nodes(input_dir: Path) -> None:
    """graph_builder should create nodes from ts_analysis.json."""
    from insights.graph_builder import build_graph

    output = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=output)

    with open(output) as f:
        graph = json.load(f)

    ts_nodes = [n for n in graph["nodes"] if n["language"] == "typescript"]
    assert len(ts_nodes) >= 1


def test_build_graph_ingests_postgres_nodes(input_dir: Path) -> None:
    """graph_builder should create nodes from postgres_analysis.json."""
    from insights.graph_builder import build_graph

    output = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=output)

    with open(output) as f:
        graph = json.load(f)

    sql_nodes = [n for n in graph["nodes"] if n["language"] == "sql"]
    assert len(sql_nodes) >= 2  # at least 2 tables


def test_build_graph_creates_entrypoints(input_dir: Path) -> None:
    """graph_builder should extract entrypoints from analyzers."""
    from insights.graph_builder import build_graph

    output = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=output)

    with open(output) as f:
        graph = json.load(f)

    assert len(graph["entrypoints"]) >= 1
    route_eps = [ep for ep in graph["entrypoints"] if ep["kind"] == "route"]
    assert len(route_eps) >= 1


def test_build_graph_deduplicates_nodes(input_dir: Path, python_analysis: dict[str, Any]) -> None:
    """graph_builder should not create duplicate node IDs."""
    from insights.graph_builder import build_graph

    # Duplicate a function in the fixture
    python_analysis["functions"].append(python_analysis["functions"][0])
    with open(input_dir / "python_analysis.json", "w") as f:
        json.dump(python_analysis, f)

    output = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=output)

    with open(output) as f:
        graph = json.load(f)

    node_ids = [n["id"] for n in graph["nodes"]]
    assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found"


def test_build_graph_handles_missing_analysis(tmp_path: Path) -> None:
    """graph_builder should return 1 when no analysis files exist."""
    from insights.graph_builder import build_graph

    output = tmp_path / "architecture.graph.json"
    rc = build_graph(input_dir=tmp_path, output_path=output)
    assert rc == 1
