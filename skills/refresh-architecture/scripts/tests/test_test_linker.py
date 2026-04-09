"""Tests for the test_linker insight module (wp-build-graph tasks 3.1-3.4).

Covers:
  - Test node extraction (function-level + class-level) from Python test files
  - Parametrized test handling (pytest.mark.parametrize)
  - Async test markers
  - Fixture-using test tags
  - TEST_COVERS edge creation via direct imports
  - Standard library / third-party import exclusion
  - Edge confidence ("high" for direct imports, "medium" for transitive)
  - Node ID schema: py:test:<module>.<function> (per contract)
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "insights") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "insights"))

from insights.test_linker import (  # noqa: E402
    TestNode,
    build_test_covers_edges,
    discover_test_files,
    extract_test_nodes,
    is_stdlib_module,
    run,
)


# ---------------------------------------------------------------------------
# discover_test_files
# ---------------------------------------------------------------------------


class TestDiscoverTestFiles:
    def test_finds_test_prefixed_files(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_foo.py").write_text("")
        (tmp_path / "tests" / "test_bar.py").write_text("")
        (tmp_path / "tests" / "helpers.py").write_text("")
        files = discover_test_files(tmp_path)
        names = sorted(f.name for f in files)
        assert names == ["test_bar.py", "test_foo.py"]

    def test_finds_suffix_style(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo_test.py").write_text("")
        files = discover_test_files(tmp_path)
        assert any(f.name == "foo_test.py" for f in files)

    def test_skips_non_python(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_foo.py").write_text("")
        (tmp_path / "tests" / "test_bar.txt").write_text("")
        files = discover_test_files(tmp_path)
        assert all(f.suffix == ".py" for f in files)

    def test_skips_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "tests" / "__pycache__").mkdir(parents=True)
        (tmp_path / "tests" / "__pycache__" / "test_x.cpython-312.pyc").write_text("")
        (tmp_path / "tests" / "test_y.py").write_text("")
        files = discover_test_files(tmp_path)
        assert all("__pycache__" not in str(f) for f in files)

    def test_empty_tree(self, tmp_path: Path) -> None:
        assert discover_test_files(tmp_path) == []


# ---------------------------------------------------------------------------
# extract_test_nodes
# ---------------------------------------------------------------------------


class TestExtractTestNodes:
    def _write(self, tmp_path: Path, source: str) -> Path:
        path = tmp_path / "test_sample.py"
        path.write_text(textwrap.dedent(source))
        return path

    def test_function_level_test(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            def test_add():
                assert 1 + 1 == 2
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        assert len(nodes) == 1
        node = nodes[0]
        assert node.name == "test_add"
        assert node.kind == "test_function"
        assert node.id == "py:test:test_sample.test_add"
        assert "test" in node.tags
        assert node.file == "test_sample.py"

    def test_non_test_function_skipped(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            def helper_only():
                pass

            def test_real():
                pass
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        names = [n.name for n in nodes]
        assert "helper_only" not in names
        assert "test_real" in names

    def test_class_level_test(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            class TestUsers:
                def test_create(self):
                    pass
                def test_delete(self):
                    pass
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        kinds = sorted(n.kind for n in nodes)
        # Expect one test_class + two test_functions
        assert kinds == ["test_class", "test_function", "test_function"]
        class_node = next(n for n in nodes if n.kind == "test_class")
        assert class_node.name == "TestUsers"
        assert class_node.id == "py:test:test_sample.TestUsers"
        # Inner method ids include the class in their qualified name
        method_ids = sorted(n.id for n in nodes if n.kind == "test_function")
        assert method_ids == [
            "py:test:test_sample.TestUsers.test_create",
            "py:test:test_sample.TestUsers.test_delete",
        ]

    def test_parametrize_tag(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            import pytest

            @pytest.mark.parametrize("x", [1, 2])
            def test_param(x):
                assert x > 0
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        test_fn = next(n for n in nodes if n.name == "test_param")
        assert "parametrized" in test_fn.tags

    def test_async_tag(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            async def test_coroutine():
                pass
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        assert "async" in nodes[0].tags

    def test_fixture_using_tag(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            def test_with_fixture(tmp_path, monkeypatch):
                pass
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        assert "fixture_using" in nodes[0].tags

    def test_span_fields_present(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            """
            def test_a():
                pass


            def test_b():
                pass
            """,
        )
        nodes = extract_test_nodes(path, repo_root=tmp_path)
        for n in nodes:
            assert n.span_start >= 1
            assert n.span_end >= n.span_start

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        """Malformed test files must not crash the pipeline."""
        path = tmp_path / "test_bad.py"
        path.write_text("def test_x(:\n    pass\n")
        # Should not raise; returns empty list
        assert extract_test_nodes(path, repo_root=tmp_path) == []


# ---------------------------------------------------------------------------
# is_stdlib_module
# ---------------------------------------------------------------------------


class TestIsStdlibModule:
    """is_stdlib_module returns True for *any* module that must NOT get
    a TEST_COVERS edge — both the Python stdlib AND a known 3rd-party
    blocklist (pytest, yaml, etc.)."""

    @pytest.mark.parametrize(
        "mod",
        ["os", "sys", "json", "pathlib", "typing", "collections.abc", "dataclasses"],
    )
    def test_stdlib_true(self, mod: str) -> None:
        assert is_stdlib_module(mod) is True

    @pytest.mark.parametrize("mod", ["pytest", "yaml", "numpy"])
    def test_third_party_blocklist_true(self, mod: str) -> None:
        """Known third-party packages are also excluded from source linking."""
        assert is_stdlib_module(mod) is True

    @pytest.mark.parametrize(
        "mod",
        ["mymodule", "src.feature_flags", "agent_coordinator.locks", ""],
    )
    def test_candidate_source_false(self, mod: str) -> None:
        """Anything not stdlib or blocklisted is a potential source node."""
        assert is_stdlib_module(mod) is False


# ---------------------------------------------------------------------------
# build_test_covers_edges
# ---------------------------------------------------------------------------


class TestBuildTestCoversEdges:
    def _make_nodes(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "py:feature_flags",
                "kind": "module",
                "language": "python",
                "name": "feature_flags",
                "file": "feature_flags.py",
            },
            {
                "id": "py:feature_flags.resolve_flag",
                "kind": "function",
                "language": "python",
                "name": "resolve_flag",
                "file": "feature_flags.py",
            },
            {
                "id": "py:locks",
                "kind": "module",
                "language": "python",
                "name": "locks",
                "file": "locks.py",
            },
        ]

    def _make_test_node(self, imports: list[str]) -> TestNode:
        return TestNode(
            id="py:test:test_feature_flags.test_basic",
            kind="test_function",
            name="test_basic",
            file="tests/test_feature_flags.py",
            span_start=1,
            span_end=5,
            tags=["test"],
            imports=imports,
        )

    def test_direct_module_import_creates_edge(self) -> None:
        nodes = self._make_nodes()
        test_node = self._make_test_node(["feature_flags"])
        edges = build_test_covers_edges([test_node], nodes)
        assert len(edges) == 1
        e = edges[0]
        assert e["from"] == test_node.id
        assert e["to"] == "py:feature_flags"
        assert e["type"] == "TEST_COVERS"
        assert e["confidence"] == "high"
        assert e["evidence"] == "direct_import"

    def test_from_import_creates_function_edge(self) -> None:
        nodes = self._make_nodes()
        # `from feature_flags import resolve_flag` records the qualified target
        test_node = self._make_test_node(["feature_flags.resolve_flag"])
        edges = build_test_covers_edges([test_node], nodes)
        # Should create an edge to the function AND the module
        targets = {e["to"] for e in edges}
        assert "py:feature_flags.resolve_flag" in targets
        assert all(e["confidence"] == "high" for e in edges)

    def test_stdlib_imports_excluded(self) -> None:
        nodes = self._make_nodes()
        test_node = self._make_test_node(["os", "pathlib", "pytest"])
        edges = build_test_covers_edges([test_node], nodes)
        assert edges == []

    def test_unknown_module_excluded(self) -> None:
        """Imports that don't correspond to any graph node are dropped."""
        nodes = self._make_nodes()
        test_node = self._make_test_node(["some_missing_module"])
        edges = build_test_covers_edges([test_node], nodes)
        assert edges == []

    def test_src_prefix_normalization(self) -> None:
        """`src.feature_flags` should match `py:feature_flags` (strip src prefix)."""
        nodes = self._make_nodes()
        test_node = self._make_test_node(["src.feature_flags"])
        edges = build_test_covers_edges([test_node], nodes)
        assert len(edges) == 1
        assert edges[0]["to"] == "py:feature_flags"


# ---------------------------------------------------------------------------
# run() — end-to-end on a tiny fake repo + graph
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def test_end_to_end(self, tmp_path: Path) -> None:
        # Create a fake graph
        import json as _json

        graph = {
            "snapshots": [{"generated_at": "2024-01-01T00:00:00Z", "git_sha": "abc"}],
            "nodes": [
                {
                    "id": "py:feature_flags",
                    "kind": "module",
                    "language": "python",
                    "name": "feature_flags",
                    "file": "feature_flags.py",
                }
            ],
            "edges": [],
        }
        input_dir = tmp_path / "analysis"
        input_dir.mkdir()
        graph_path = input_dir / "architecture.graph.json"
        graph_path.write_text(_json.dumps(graph))

        # Create a test file in the fake repo
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_feature_flags.py").write_text(
            textwrap.dedent(
                """
                from feature_flags import resolve_flag

                def test_basic():
                    assert resolve_flag("X") is False
                """
            ).strip()
        )

        rc = run(
            input_dir=input_dir,
            output_path=graph_path,
            repo_root=tmp_path,
            test_dirs=[tests_dir],
        )
        assert rc == 0

        # Verify graph now has test nodes and TEST_COVERS edges
        updated = _json.loads(graph_path.read_text())
        node_ids = [n["id"] for n in updated["nodes"]]
        assert any(nid.startswith("py:test:") for nid in node_ids)
        edge_types = {e["type"] for e in updated["edges"]}
        assert "TEST_COVERS" in edge_types
