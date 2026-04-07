"""Tests for the coupling analyzer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_coupling import _extract_file_from_node_id, analyze

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_graph(tmp_path: Path, nodes: list[dict], edges: list[dict]) -> None:
    """Write a minimal architecture graph file."""
    graph_dir = tmp_path / "docs" / "architecture-analysis"
    graph_dir.mkdir(parents=True, exist_ok=True)
    graph = {"nodes": nodes, "edges": edges}
    (graph_dir / "architecture.graph.json").write_text(
        json.dumps(graph), encoding="utf-8"
    )


def _write_impact(tmp_path: Path, nodes: list[dict]) -> None:
    """Write a minimal high_impact_nodes file."""
    graph_dir = tmp_path / "docs" / "architecture-analysis"
    graph_dir.mkdir(parents=True, exist_ok=True)
    (graph_dir / "high_impact_nodes.json").write_text(
        json.dumps(nodes), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 1. Node ID file extraction
# ---------------------------------------------------------------------------


class TestNodeIdExtraction:
    def test_python_node_id(self) -> None:
        assert _extract_file_from_node_id("py:src/foo.py::bar") == "src/foo.py"

    def test_simple_path(self) -> None:
        assert _extract_file_from_node_id("src/foo.py") == "src/foo.py"

    def test_no_function(self) -> None:
        assert _extract_file_from_node_id("py:src/foo.py") == "src/foo.py"


# ---------------------------------------------------------------------------
# 2. Skipped when no graph
# ---------------------------------------------------------------------------


class TestMissingGraph:
    def test_skipped_when_no_graph(self, tmp_path: Path) -> None:
        result = analyze(str(tmp_path))
        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)


# ---------------------------------------------------------------------------
# 3. Fan-out detection
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_high_fan_out_detected(self, tmp_path: Path) -> None:
        nodes = [{"id": f"py:mod{i}.py" } for i in range(15)]
        edges = [
            {"source": "py:mod0.py", "target": f"py:mod{i}.py"}
            for i in range(1, 12)
        ]
        _write_graph(tmp_path, nodes, edges)
        result = analyze(str(tmp_path))
        fan_out_findings = [
            f for f in result.findings
            if "fan-out" in f.title.lower()
        ]
        assert len(fan_out_findings) >= 1

    def test_low_fan_out_no_finding(self, tmp_path: Path) -> None:
        nodes = [{"id": "py:a.py"}, {"id": "py:b.py"}]
        edges = [{"source": "py:a.py", "target": "py:b.py"}]
        _write_graph(tmp_path, nodes, edges)
        result = analyze(str(tmp_path))
        fan_out_findings = [
            f for f in result.findings
            if "fan-out" in f.title.lower()
        ]
        assert len(fan_out_findings) == 0


# ---------------------------------------------------------------------------
# 4. Fan-in detection
# ---------------------------------------------------------------------------


class TestFanIn:
    def test_high_fan_in_detected(self, tmp_path: Path) -> None:
        nodes = [{"id": f"py:mod{i}.py"} for i in range(15)]
        edges = [
            {"source": f"py:mod{i}.py", "target": "py:mod0.py"}
            for i in range(1, 12)
        ]
        _write_graph(tmp_path, nodes, edges)
        result = analyze(str(tmp_path))
        fan_in_findings = [
            f for f in result.findings
            if "fan-in" in f.title.lower()
        ]
        assert len(fan_in_findings) >= 1


# ---------------------------------------------------------------------------
# 5. Hub node detection
# ---------------------------------------------------------------------------


class TestHubNode:
    def test_hub_detected(self, tmp_path: Path) -> None:
        # Create a node with high fan-in AND fan-out
        nodes = [{"id": f"py:mod{i}.py"} for i in range(20)]
        edges = []
        # mod0 depends on mod1..mod9 (fan-out=9)
        for i in range(1, 10):
            edges.append({"source": "py:mod0.py", "target": f"py:mod{i}.py"})
        # mod10..mod19 depend on mod0 (fan-in=10)
        for i in range(10, 20):
            edges.append({"source": f"py:mod{i}.py", "target": "py:mod0.py"})
        _write_graph(tmp_path, nodes, edges)
        result = analyze(str(tmp_path))
        hub_findings = [f for f in result.findings if "hub" in f.title.lower()]
        assert len(hub_findings) >= 1


# ---------------------------------------------------------------------------
# 6. High-impact nodes
# ---------------------------------------------------------------------------


class TestHighImpact:
    def test_impact_node_detected(self, tmp_path: Path) -> None:
        _write_graph(tmp_path, [], [])
        _write_impact(tmp_path, [
            {"node_id": "py:core.py::init", "dependent_count": 20},
        ])
        result = analyze(str(tmp_path))
        impact_findings = [
            f for f in result.findings if "impact" in f.title.lower()
        ]
        assert len(impact_findings) == 1

    def test_low_impact_ignored(self, tmp_path: Path) -> None:
        _write_graph(tmp_path, [], [])
        _write_impact(tmp_path, [
            {"node_id": "py:helper.py::util", "dependent_count": 3},
        ])
        result = analyze(str(tmp_path))
        impact_findings = [
            f for f in result.findings if "impact" in f.title.lower()
        ]
        assert len(impact_findings) == 0
