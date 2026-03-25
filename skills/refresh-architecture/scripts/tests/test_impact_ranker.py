"""Tests for insights/impact_ranker.py."""

from __future__ import annotations

from typing import Any


def test_compute_high_impact_nodes_returns_sorted(built_graph: dict[str, Any]) -> None:
    """impact_ranker should return nodes sorted by dependent count descending."""
    from insights.impact_ranker import compute_high_impact_nodes

    result = compute_high_impact_nodes(
        built_graph["nodes"],
        built_graph["edges"],
        threshold=1,  # low threshold to get results from small fixture
    )
    assert isinstance(result, list)
    for item in result:
        assert "id" in item
        assert "dependent_count" in item

    # Verify sorted descending
    counts = [r["dependent_count"] for r in result]
    assert counts == sorted(counts, reverse=True)


def test_compute_high_impact_nodes_threshold(built_graph: dict[str, Any]) -> None:
    """Nodes below the threshold should not appear in results."""
    from insights.impact_ranker import compute_high_impact_nodes

    # With a very high threshold, no nodes should qualify
    result = compute_high_impact_nodes(
        built_graph["nodes"],
        built_graph["edges"],
        threshold=9999,
    )
    assert result == []


def test_compute_high_impact_nodes_empty_graph() -> None:
    """impact_ranker should handle empty graph gracefully."""
    from insights.impact_ranker import compute_high_impact_nodes

    result = compute_high_impact_nodes([], [], threshold=5)
    assert result == []
