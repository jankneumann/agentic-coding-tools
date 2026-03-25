"""Tests for insights/summary_builder.py."""

from __future__ import annotations

from typing import Any


def test_generate_summary_schema(built_graph: dict[str, Any]) -> None:
    """summary_builder should produce a summary with the expected schema."""
    from insights.summary_builder import generate_summary

    summary = generate_summary(
        graph=built_graph,
        flows=[],
        disconnected_endpoints=[],
        disconnected_frontend_calls=[],
        high_impact_nodes=[],
        summary_limit=50,
        git_sha="test123",
        generated_at="2026-01-01T00:00:00Z",
    )

    assert summary["generated_at"] == "2026-01-01T00:00:00Z"
    assert summary["git_sha"] == "test123"
    assert "stats" in summary
    assert "cross_layer_flows" in summary
    assert "disconnected_endpoints" in summary
    assert "disconnected_frontend_calls" in summary
    assert "high_impact_nodes" in summary


def test_generate_summary_stats(built_graph: dict[str, Any]) -> None:
    """Summary stats should reflect the graph contents."""
    from insights.summary_builder import generate_summary

    summary = generate_summary(
        graph=built_graph,
        flows=[],
        disconnected_endpoints=[],
        disconnected_frontend_calls=[],
        high_impact_nodes=[],
        summary_limit=50,
        git_sha="test",
        generated_at="2026-01-01T00:00:00Z",
    )

    stats = summary["stats"]
    assert stats["total_nodes"] == len(built_graph["nodes"])
    assert stats["total_edges"] == len(built_graph["edges"])
    assert "by_language" in stats


def test_generate_summary_adaptive_limit(built_graph: dict[str, Any]) -> None:
    """Summary should respect the summary_limit for flows."""
    from insights.summary_builder import generate_summary

    flows = [
        {"confidence": "high", "frontend_component": "a", "backend_handler": "b"},
        {"confidence": "medium", "frontend_component": "c", "backend_handler": "d"},
        {"confidence": "low", "frontend_component": "e", "backend_handler": "f"},
    ]

    summary = generate_summary(
        graph=built_graph,
        flows=flows,
        disconnected_endpoints=[],
        disconnected_frontend_calls=[],
        high_impact_nodes=[],
        summary_limit=2,
        git_sha="test",
        generated_at="2026-01-01T00:00:00Z",
    )

    # Only 2 flows should be included (high first, then medium)
    assert len(summary["cross_layer_flows"]) == 2
    assert summary["cross_layer_flows"][0]["confidence"] == "high"
    assert summary["cross_layer_flows"][1]["confidence"] == "medium"


def test_find_disconnected_endpoints(built_graph: dict[str, Any]) -> None:
    """find_disconnected_endpoints should detect routes without api_call edges."""
    from insights.summary_builder import find_disconnected_endpoints

    disconnected = find_disconnected_endpoints(built_graph)
    assert isinstance(disconnected, list)
    # In the unlinked graph, all route entrypoints should be disconnected
    for ep in disconnected:
        assert "node_id" in ep
        assert "path" in ep
