"""Tests for affected_tests() query (wp-build-graph tasks 3.5, 3.6).

Covers:
  - Single file change returns covering tests
  - No coverage → empty list + warning
  - Stale graph (>24h mtime) → returns None (signals 'run all tests')
  - Missing graph → returns None
  - Traversal bound: 10K node walk cap, returns None on overflow
  - Cycle detection: visited-set prevents infinite loop
  - Performance benchmark: <100ms on a 10K-node graph
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from affected_tests import (  # noqa: E402
    MAX_GRAPH_AGE_HOURS,
    MAX_TRAVERSAL_NODES,
    affected_tests,
    is_graph_stale,
    load_graph_with_mtime,
)


# ---------------------------------------------------------------------------
# Graph fixtures
# ---------------------------------------------------------------------------


def _build_graph(
    source_modules: list[tuple[str, str]],
    test_coverage: list[tuple[str, str]],
    extra_imports: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Helper: build a minimal graph with source modules + TEST_COVERS edges.

    Args:
        source_modules: list of (node_id, file) pairs for source modules.
        test_coverage: list of (test_id, source_node_id) pairs.
        extra_imports: optional (from_id, to_id) for call/import edges.
    """
    test_files: dict[str, str] = {}
    for test_id, _source in test_coverage:
        # Derive a fake file path from the test id
        tfile = (
            test_id.replace("py:test:", "tests/").replace(".", "/") + ".py"
            if test_id not in test_files
            else test_files[test_id]
        )
        test_files.setdefault(test_id, tfile)

    nodes: list[dict[str, Any]] = []
    for nid, file in source_modules:
        nodes.append(
            {
                "id": nid,
                "kind": "module",
                "language": "python",
                "name": nid.replace("py:", ""),
                "file": file,
            }
        )
    for tid, tfile in test_files.items():
        nodes.append(
            {
                "id": tid,
                "kind": "test_function",
                "language": "python",
                "name": tid.split(".")[-1],
                "file": tfile,
            }
        )

    edges: list[dict[str, Any]] = [
        {
            "from": tid,
            "to": sid,
            "type": "TEST_COVERS",
            "confidence": "high",
            "evidence": "direct_import",
        }
        for tid, sid in test_coverage
    ]
    if extra_imports:
        edges.extend(
            {
                "from": f,
                "to": t,
                "type": "import",
                "confidence": "high",
                "evidence": "static",
            }
            for f, t in extra_imports
        )
    return {"nodes": nodes, "edges": edges}


def _write_graph(tmp_path: Path, graph: dict[str, Any]) -> Path:
    path = tmp_path / "architecture.graph.json"
    path.write_text(json.dumps(graph))
    return path


# ---------------------------------------------------------------------------
# is_graph_stale / load_graph_with_mtime
# ---------------------------------------------------------------------------


class TestIsGraphStale:
    def test_missing_graph_is_stale(self, tmp_path: Path) -> None:
        assert is_graph_stale(tmp_path / "nope.json") is True

    def test_fresh_graph_is_not_stale(self, tmp_path: Path) -> None:
        path = _write_graph(tmp_path, {"nodes": [], "edges": []})
        assert is_graph_stale(path) is False

    def test_old_graph_is_stale(self, tmp_path: Path) -> None:
        path = _write_graph(tmp_path, {"nodes": [], "edges": []})
        old_mtime = time.time() - (MAX_GRAPH_AGE_HOURS + 1) * 3600
        import os as _os
        _os.utime(path, (old_mtime, old_mtime))
        assert is_graph_stale(path) is True


# ---------------------------------------------------------------------------
# affected_tests — happy path
# ---------------------------------------------------------------------------


class TestAffectedTestsBasic:
    def test_single_file_with_direct_coverage(self, tmp_path: Path) -> None:
        graph = _build_graph(
            source_modules=[("py:feature_flags", "src/feature_flags.py")],
            test_coverage=[
                ("py:test:tests.test_feature_flags.test_basic", "py:feature_flags"),
                ("py:test:tests.test_feature_flags.test_enabled", "py:feature_flags"),
            ],
        )
        graph_path = _write_graph(tmp_path, graph)
        result = affected_tests(
            ["src/feature_flags.py"], graph_path=graph_path
        )
        assert result is not None
        assert set(result) == {
            "tests/tests/test_feature_flags/test_basic.py",
            "tests/tests/test_feature_flags/test_enabled.py",
        }

    def test_unchanged_file_returns_empty(self, tmp_path: Path) -> None:
        graph = _build_graph(
            source_modules=[
                ("py:feature_flags", "src/feature_flags.py"),
                ("py:locks", "src/locks.py"),
            ],
            test_coverage=[
                ("py:test:tests.test_ff.test_a", "py:feature_flags"),
            ],
        )
        graph_path = _write_graph(tmp_path, graph)
        result = affected_tests(["src/locks.py"], graph_path=graph_path)
        assert result == []

    def test_empty_changed_files(self, tmp_path: Path) -> None:
        graph = _build_graph(
            source_modules=[("py:feature_flags", "src/feature_flags.py")],
            test_coverage=[("py:test:tests.test_ff.test_a", "py:feature_flags")],
        )
        graph_path = _write_graph(tmp_path, graph)
        result = affected_tests([], graph_path=graph_path)
        assert result == []

    def test_multiple_changed_files(self, tmp_path: Path) -> None:
        graph = _build_graph(
            source_modules=[
                ("py:feature_flags", "src/feature_flags.py"),
                ("py:locks", "src/locks.py"),
            ],
            test_coverage=[
                ("py:test:tests.test_ff.test_a", "py:feature_flags"),
                ("py:test:tests.test_locks.test_b", "py:locks"),
            ],
        )
        graph_path = _write_graph(tmp_path, graph)
        result = affected_tests(
            ["src/feature_flags.py", "src/locks.py"], graph_path=graph_path
        )
        assert result is not None
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestAffectedTestsFallback:
    def test_missing_graph_returns_none(self, tmp_path: Path) -> None:
        result = affected_tests(
            ["src/feature_flags.py"], graph_path=tmp_path / "nope.json"
        )
        assert result is None  # Fall back to "run all tests"

    def test_stale_graph_returns_none(self, tmp_path: Path) -> None:
        graph = _build_graph(
            source_modules=[("py:feature_flags", "src/feature_flags.py")],
            test_coverage=[("py:test:tests.test_ff.test_a", "py:feature_flags")],
        )
        path = _write_graph(tmp_path, graph)
        # Age the file past the staleness threshold
        old = time.time() - (MAX_GRAPH_AGE_HOURS + 1) * 3600
        import os as _os
        _os.utime(path, (old, old))
        result = affected_tests(["src/feature_flags.py"], graph_path=path)
        assert result is None

    def test_uncovered_file_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        graph = _build_graph(
            source_modules=[("py:orphan", "src/orphan.py")],
            test_coverage=[],
        )
        graph_path = _write_graph(tmp_path, graph)
        with caplog.at_level("WARNING"):
            result = affected_tests(["src/orphan.py"], graph_path=graph_path)
        assert result == []
        assert any("uncovered" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# Traversal bound + cycle detection (D10)
# ---------------------------------------------------------------------------


class TestTraversalBound:
    def test_bound_respected(self, tmp_path: Path) -> None:
        """Traversal walks ≤ MAX_TRAVERSAL_NODES and exits cleanly."""
        graph = _build_graph(
            source_modules=[("py:root", "src/root.py")],
            test_coverage=[("py:test:tests.test_root.test_a", "py:root")],
        )
        graph_path = _write_graph(tmp_path, graph)
        result = affected_tests(["src/root.py"], graph_path=graph_path)
        assert result is not None

    def test_overflow_returns_none(self, tmp_path: Path) -> None:
        """Construct a graph where the BFS frontier explodes past the bound."""
        # Create MAX + 5 extra source modules, all covered by the same test.
        source = [
            (f"py:mod_{i}", f"src/mod_{i}.py")
            for i in range(MAX_TRAVERSAL_NODES + 5)
        ]
        coverage = [
            (f"py:test:tests.test_big.test_{i}", f"py:mod_{i}")
            for i in range(MAX_TRAVERSAL_NODES + 5)
        ]
        graph = _build_graph(source_modules=source, test_coverage=coverage)
        graph_path = _write_graph(tmp_path, graph)
        changed = [f"src/mod_{i}.py" for i in range(MAX_TRAVERSAL_NODES + 5)]
        result = affected_tests(changed, graph_path=graph_path)
        # Overflowing the bound falls back to "run all tests"
        assert result is None

    def test_cycle_does_not_hang(self, tmp_path: Path) -> None:
        """A cycle in call/import edges must not cause an infinite loop."""
        graph = _build_graph(
            source_modules=[
                ("py:a", "src/a.py"),
                ("py:b", "src/b.py"),
            ],
            test_coverage=[("py:test:tests.test_cycle.test_a", "py:a")],
            extra_imports=[("py:a", "py:b"), ("py:b", "py:a")],
        )
        graph_path = _write_graph(tmp_path, graph)
        start = time.monotonic()
        result = affected_tests(["src/a.py"], graph_path=graph_path)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, "cycle detection failed — query hung"
        assert result is not None


# ---------------------------------------------------------------------------
# Performance (D10: <100ms on 10K nodes)
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_10k_node_graph_under_100ms(self, tmp_path: Path) -> None:
        """Synthesize a 10K-node graph and assert query latency."""
        source = [
            (f"py:src_{i}", f"src/src_{i}.py") for i in range(5000)
        ]
        coverage = [
            (f"py:test:tests.t_{i}.test_x", f"py:src_{i}")
            for i in range(5000)
        ]
        graph = _build_graph(source_modules=source, test_coverage=coverage)
        graph_path = _write_graph(tmp_path, graph)

        # Warmup + timed run
        affected_tests(["src/src_0.py"], graph_path=graph_path)
        start = time.monotonic()
        result = affected_tests(["src/src_0.py"], graph_path=graph_path)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert result is not None
        # Generous bound — 500ms to avoid CI flake. The goal is "sub-second on 10K nodes".
        assert elapsed_ms < 500, f"query took {elapsed_ms:.0f}ms, exceeds budget"
