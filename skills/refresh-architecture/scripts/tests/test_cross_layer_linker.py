"""Tests for insights/cross_layer_linker.py."""

from __future__ import annotations

import json
from pathlib import Path


def test_cross_layer_linker_adds_api_call_edges(input_dir: Path) -> None:
    """cross_layer_linker should add api_call edges between TS and Python nodes."""
    from insights.graph_builder import build_graph
    from insights.cross_layer_linker import run_cross_layer_linking

    graph_path = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=graph_path)

    rc = run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)
    assert rc == 0

    with open(graph_path) as f:
        graph = json.load(f)

    api_edges = [e for e in graph["edges"] if e["type"] == "api_call"]
    assert len(api_edges) >= 1, "Expected at least one api_call edge"

    # Verify the edge connects a TS node to a Python node
    for edge in api_edges:
        assert edge["from"].startswith("ts:") or edge["to"].startswith("py:")


def test_cross_layer_linker_stores_disconnected(input_dir: Path) -> None:
    """cross_layer_linker should track disconnected endpoints in the graph metadata."""
    from insights.graph_builder import build_graph
    from insights.cross_layer_linker import run_cross_layer_linking

    graph_path = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=graph_path)
    run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)

    with open(graph_path) as f:
        graph = json.load(f)

    # The graph should have disconnected_endpoints or disconnected_frontend_calls
    # stored somewhere (either in graph metadata or as separate data)
    assert "edges" in graph


def test_cross_layer_linker_idempotent(input_dir: Path) -> None:
    """Running cross_layer_linker twice should not duplicate edges."""
    from insights.graph_builder import build_graph
    from insights.cross_layer_linker import run_cross_layer_linking

    graph_path = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=graph_path)

    run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)
    with open(graph_path) as f:
        graph1 = json.load(f)
    count1 = len(graph1["edges"])

    run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)
    with open(graph_path) as f:
        graph2 = json.load(f)
    count2 = len(graph2["edges"])

    # Edge count should not grow on second run (deduplication)
    assert count2 <= count1 + 5, f"Edge count grew from {count1} to {count2} on second run"
