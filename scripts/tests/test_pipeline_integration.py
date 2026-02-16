"""Integration test for the full 3-layer architecture pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


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
    assert "## System Overview" in content
    assert "## Module Responsibility Map" in content
    assert "## Dependency Layers" in content
    assert "## Entry Points" in content
    assert "## Architecture Health" in content
    assert "## High-Impact Nodes" in content
    assert "## Code Health Indicators" in content
    assert "## Parallel Modification Zones" in content


def test_report_generation_with_config(input_dir: Path) -> None:
    """Report generation with an explicit config file should respect settings."""
    from compile_architecture_graph import compile_graph

    compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=False,
    )

    # Write a config that omits parallel_zones and sets project identity
    config_path = input_dir / "architecture.config.yaml"
    config_data = {
        "project": {
            "name": "test-project",
            "description": "A test project",
            "primary_language": "rust",
            "protocol": "http",
        },
        "report": {
            "sections": [
                "system_overview",
                "module_map",
                "entry_points",
                "health",
            ],
        },
        "health": {
            "expected_categories": ["orphan", "disconnected_flow"],
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    from reports.architecture_report import main as report_main

    report_path = input_dir / "architecture.report.md"
    rc = report_main([
        "--input-dir", str(input_dir),
        "--output", str(report_path),
        "--config", str(config_path),
    ])

    assert rc == 0
    content = report_path.read_text()

    # Project identity should appear
    assert "**test-project**" in content
    assert "A test project" in content

    # Protocol override
    assert "HTTP service" in content

    # Language override
    assert "Rust" in content

    # Included sections should be present
    assert "## System Overview" in content
    assert "## Module Responsibility Map" in content
    assert "## Entry Points" in content
    assert "## Architecture Health" in content

    # Omitted sections should be absent
    assert "## Parallel Modification Zones" not in content
    assert "## Dependency Layers" not in content
    assert "## Code Health Indicators" not in content
    assert "## Architecture Diagrams" not in content


def test_report_no_config_backwards_compatible(input_dir: Path) -> None:
    """Report without a config file should produce identical output to pre-config."""
    from compile_architecture_graph import compile_graph

    compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=False,
    )

    from reports.architecture_report import main as report_main

    report_path = input_dir / "architecture.report.md"
    # No --config flag — should use defaults
    rc = report_main([
        "--input-dir", str(input_dir),
        "--output", str(report_path),
    ])

    assert rc == 0
    content = report_path.read_text()

    # All default sections should be present
    assert "## System Overview" in content
    assert "## Module Responsibility Map" in content
    assert "## Dependency Layers" in content
    assert "## Entry Points" in content
    assert "## Architecture Health" in content
    assert "## High-Impact Nodes" in content
    assert "## Code Health Indicators" in content
    assert "## Parallel Modification Zones" in content


def test_health_custom_expected_categories(input_dir: Path) -> None:
    """Config can mark additional categories as expected."""
    from compile_architecture_graph import compile_graph

    compile_graph(
        input_dir=input_dir,
        output_dir=input_dir,
        summary_limit=50,
        emit_sqlite_flag=False,
    )

    config_path = input_dir / "architecture.config.yaml"
    config_data = {
        "health": {
            "expected_categories": ["disconnected_flow", "orphan"],
            "category_explanations": {
                "orphan": "Orphaned symbols are intentionally unused in this project",
            },
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    from reports.architecture_report import main as report_main

    report_path = input_dir / "architecture.report.md"
    rc = report_main([
        "--input-dir", str(input_dir),
        "--output", str(report_path),
        "--config", str(config_path),
    ])

    assert rc == 0
    content = report_path.read_text()

    # Both categories should be marked expected if they appear
    if "Orphan" in content:
        assert "(expected)" in content


def test_config_schema_defaults() -> None:
    """ReportConfig defaults should match the pre-config hardcoded behaviour."""
    from reports.config_schema import (
        DEFAULT_SECTIONS,
        ReportConfig,
        load_config,
    )

    # Loading with no file returns defaults
    cfg = load_config(Path("/nonexistent/path.yaml"))
    assert isinstance(cfg, ReportConfig)
    assert cfg.report.sections == DEFAULT_SECTIONS
    assert "disconnected_flow" in cfg.health.expected_categories
    assert cfg.project.name == ""
    assert cfg.project.primary_language == ""


def test_config_schema_warns_on_unknown_section(tmp_path: Path) -> None:
    """Unknown section names should produce warnings."""
    import warnings

    config_path = tmp_path / "test.yaml"
    config_data = {
        "report": {
            "sections": ["system_overview", "nonexistent_section"],
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    from reports.config_schema import load_config

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cfg = load_config(config_path)
        warning_messages = [str(x.message) for x in w]
        assert any("nonexistent_section" in msg for msg in warning_messages)
    assert "nonexistent_section" in cfg.report.sections


def test_config_schema_warns_on_unknown_top_level_key(tmp_path: Path) -> None:
    """Unknown top-level config keys should produce warnings."""
    import warnings

    config_path = tmp_path / "test.yaml"
    config_data = {
        "project": {"name": "test"},
        "experimental": {"foo": "bar"},
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    from reports.config_schema import load_config

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        load_config(config_path)
        warning_messages = [str(x.message) for x in w]
        assert any("experimental" in msg for msg in warning_messages)
