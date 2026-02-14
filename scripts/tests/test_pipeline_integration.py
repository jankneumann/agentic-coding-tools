"""Integration test for the full 3-layer architecture pipeline."""

from __future__ import annotations

import json
from pathlib import Path


def test_full_pipeline(input_dir: Path) -> None:
    """The full compile_graph pipeline should produce all expected artifacts."""
    from compile_architecture_graph import compile_graph

    rc = compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=False,
    )

    assert rc == 0

    # Check all expected outputs exist
    graph_path = input_dir / "architecture.graph.json"
    summary_path = input_dir / "architecture.summary.json"
    flows_path = input_dir / "cross_layer_flows.json"
    impact_path = input_dir / "high_impact_nodes.json"

    assert graph_path.exists(), "architecture.graph.json not generated"
    assert summary_path.exists(), "architecture.summary.json not generated"
    assert flows_path.exists(), "cross_layer_flows.json not generated"
    assert impact_path.exists(), "high_impact_nodes.json not generated"

    # Validate graph schema
    with open(graph_path) as f:
        graph = json.load(f)
    assert "nodes" in graph
    assert "edges" in graph
    assert "entrypoints" in graph
    assert "snapshots" in graph
    assert len(graph["nodes"]) > 0

    # Validate summary schema
    with open(summary_path) as f:
        summary = json.load(f)
    assert "stats" in summary
    assert "cross_layer_flows" in summary
    assert "disconnected_endpoints" in summary
    assert "high_impact_nodes" in summary

    # Validate flows schema
    with open(flows_path) as f:
        flows_data = json.load(f)
    assert "flows" in flows_data
    assert "generated_at" in flows_data

    # Validate impact schema
    with open(impact_path) as f:
        impact_data = json.load(f)
    assert "high_impact_nodes" in impact_data
    assert "threshold" in impact_data


def test_full_pipeline_with_sqlite(input_dir: Path) -> None:
    """The pipeline with --sqlite should also produce architecture.sqlite."""
    from compile_architecture_graph import compile_graph

    rc = compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=True,
    )

    assert rc == 0
    assert (input_dir / "architecture.sqlite").exists()


def test_report_generation(input_dir: Path) -> None:
    """The report aggregator should produce a Markdown report from pipeline outputs."""
    from compile_architecture_graph import compile_graph

    # First run the full pipeline
    compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=False,
    )

    # Then generate the report
    from reports.architecture_report import main as report_main

    report_path = input_dir / "architecture.report.md"
    rc = report_main([
        "--input-dir", str(input_dir),
        "--output", str(report_path),
    ])

    assert rc == 0
    assert report_path.exists()

    content = report_path.read_text()
    assert "# Architecture Report" in content
    assert "## Overview" in content
    assert "## Cross-Layer Flows" in content
    assert "## High-Impact Nodes" in content
