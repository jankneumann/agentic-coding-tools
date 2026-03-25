"""Tests for insights/flow_tracer.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_flow_tracer_infers_flows(input_dir: Path) -> None:
    """flow_tracer should infer cross-layer flows from a linked graph."""
    from insights.graph_builder import build_graph
    from insights.cross_layer_linker import run_cross_layer_linking
    from insights.db_linker import run as run_db_linker
    from insights.flow_tracer import main as flow_tracer_main

    # Build and link the graph
    graph_path = input_dir / "architecture.graph.json"
    build_graph(input_dir=input_dir, output_path=graph_path)
    run_cross_layer_linking(input_dir=input_dir, output_path=graph_path)
    run_db_linker(input_dir=input_dir, output_path=graph_path)

    # Run flow tracer
    flows_path = input_dir / "cross_layer_flows.json"
    rc = flow_tracer_main([
        "--input-dir", str(input_dir),
        "--output", str(flows_path),
    ])
    assert rc == 0
    assert flows_path.exists()

    with open(flows_path) as f:
        data = json.load(f)

    assert "flows" in data
    assert "generated_at" in data


def test_flow_tracer_function_api(built_graph: dict[str, Any]) -> None:
    """flow_tracer.infer_cross_layer_flows should work with in-memory graph."""
    from insights.flow_tracer import infer_cross_layer_flows

    flows = infer_cross_layer_flows(
        built_graph["nodes"],
        built_graph["edges"],
        built_graph["entrypoints"],
    )
    assert isinstance(flows, list)
    # Flows may be empty if no api_call edges exist in unlinked graph
    for flow in flows:
        assert "frontend_component" in flow
        assert "backend_handler" in flow
        assert "db_tables" in flow
