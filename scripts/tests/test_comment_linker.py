"""Tests for the comment linker insight module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "insights") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "insights"))

from insights.comment_linker import compute_comment_insights, main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enrichment() -> dict[str, Any]:
    return {
        "comments": {
            "total": 5,
            "with_markers": 2,
            "items": [
                {"file": "a.py", "line": 1, "text": "# Setup", "language": "python",
                 "type": "inline", "markers": [], "enclosing_node": "py:a.foo"},
                {"file": "a.py", "line": 5, "text": "# TODO: refactor", "language": "python",
                 "type": "inline", "markers": ["TODO"], "enclosing_node": "py:a.foo"},
                {"file": "b.py", "line": 1, "text": "# Module B", "language": "python",
                 "type": "inline", "markers": [], "enclosing_node": None},
                {"file": "b.py", "line": 3, "text": "# FIXME: broken", "language": "python",
                 "type": "inline", "markers": ["FIXME"], "enclosing_node": "py:b.bar"},
                {"file": "c.ts", "line": 1, "text": "// comment", "language": "typescript",
                 "type": "inline", "markers": [], "enclosing_node": None},
            ],
        },
    }


@pytest.fixture
def graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:a.foo", "file": "a.py", "span": {"start": 1, "end": 10}},
            {"id": "py:b.bar", "file": "b.py", "span": {"start": 1, "end": 10}},
            {"id": "py:c.baz", "file": "c.py", "span": {"start": 1, "end": 5}},
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeCommentInsights:
    def test_summary(self, enrichment: dict, graph: dict) -> None:
        result = compute_comment_insights(enrichment, graph)
        assert result["summary"]["total_comments"] == 5
        assert result["summary"]["total_with_markers"] == 2
        assert result["summary"]["total_graph_nodes"] == 3
        assert result["summary"]["documented_nodes"] == 2
        assert "TODO" in result["summary"]["marker_totals"]
        assert "FIXME" in result["summary"]["marker_totals"]

    def test_marker_hotspots(self, enrichment: dict, graph: dict) -> None:
        result = compute_comment_insights(enrichment, graph)
        assert len(result["marker_hotspots"]) >= 1
        # a.py and b.py each have 1 marker
        hotspot_files = {h["file"] for h in result["marker_hotspots"]}
        assert "a.py" in hotspot_files
        assert "b.py" in hotspot_files

    def test_file_summaries(self, enrichment: dict, graph: dict) -> None:
        result = compute_comment_insights(enrichment, graph)
        summaries = {s["file"]: s for s in result["file_summaries"]}
        assert summaries["a.py"]["total_comments"] == 2
        assert summaries["a.py"]["with_markers"] == 1
        assert summaries["c.ts"]["languages"] == ["typescript"]

    def test_node_marker_map(self, enrichment: dict, graph: dict) -> None:
        result = compute_comment_insights(enrichment, graph)
        assert "py:a.foo" in result["node_marker_map"]
        assert result["node_marker_map"]["py:a.foo"]["markers"] == ["TODO"]

    def test_no_graph(self, enrichment: dict) -> None:
        result = compute_comment_insights(enrichment)
        assert result["summary"]["total_graph_nodes"] == 0
        assert result["summary"]["documentation_coverage"] == 0

    def test_empty_enrichment(self) -> None:
        result = compute_comment_insights({"comments": {"items": []}})
        assert result["summary"]["total_comments"] == 0


class TestCLI:
    def test_main(self, tmp_path: Path, enrichment: dict) -> None:
        input_dir = tmp_path / "arch"
        input_dir.mkdir()
        with open(input_dir / "treesitter_enrichment.json", "w") as f:
            json.dump(enrichment, f)
        output = tmp_path / "comment_insights.json"

        rc = main(["--input-dir", str(input_dir), "--output", str(output)])
        assert rc == 0
        assert output.exists()

    def test_missing_input(self, tmp_path: Path) -> None:
        rc = main(["--input-dir", str(tmp_path), "--output", str(tmp_path / "out.json")])
        assert rc == 0  # Graceful skip
