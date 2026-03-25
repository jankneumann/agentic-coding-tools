"""Tests for the tree-sitter enrichment engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from enrich_with_treesitter import (
    TREESITTER_AVAILABLE,
    TreeSitterEnricher,
    classify_comment,
    find_enclosing_node,
)

pytestmark = pytest.mark.skipif(
    not TREESITTER_AVAILABLE,
    reason="tree-sitter not installed",
)

QUERIES_DIR = SCRIPTS_DIR / "treesitter_queries"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enricher() -> TreeSitterEnricher:
    return TreeSitterEnricher(queries_dir=QUERIES_DIR)


@pytest.fixture
def enricher_with_graph() -> TreeSitterEnricher:
    graph = {
        "nodes": [
            {
                "id": "py:test_module.foo",
                "file": "test_module.py",
                "span": {"start": 1, "end": 10},
            },
            {
                "id": "py:test_module.bar",
                "file": "test_module.py",
                "span": {"start": 12, "end": 20},
            },
        ],
        "edges": [],
    }
    return TreeSitterEnricher(queries_dir=QUERIES_DIR, graph=graph)


@pytest.fixture
def py_src(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    return d


@pytest.fixture
def ts_src(tmp_path: Path) -> Path:
    d = tmp_path / "web"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# classify_comment
# ---------------------------------------------------------------------------


class TestClassifyComment:
    def test_plain_comment(self) -> None:
        result = classify_comment("# This is a comment")
        assert result["markers"] == []
        assert result["has_markers"] is False

    def test_todo_marker(self) -> None:
        result = classify_comment("# TODO: fix this later")
        assert "TODO" in result["markers"]
        assert result["has_markers"] is True

    def test_fixme_marker(self) -> None:
        result = classify_comment("# FIXME: broken")
        assert "FIXME" in result["markers"]

    def test_multiple_markers(self) -> None:
        result = classify_comment("# TODO FIXME HACK")
        assert len(result["markers"]) == 3

    def test_case_insensitive(self) -> None:
        result = classify_comment("# todo: lowercase")
        assert "TODO" in result["markers"]


# ---------------------------------------------------------------------------
# find_enclosing_node
# ---------------------------------------------------------------------------


class TestFindEnclosingNode:
    def test_finds_enclosing(self) -> None:
        nodes = [
            {"id": "a", "span": {"start": 1, "end": 10}},
            {"id": "b", "span": {"start": 3, "end": 7}},
        ]
        # Line 5 is inside both, but b is tighter
        assert find_enclosing_node(5, nodes) == "b"

    def test_no_match(self) -> None:
        nodes = [{"id": "a", "span": {"start": 1, "end": 5}}]
        assert find_enclosing_node(10, nodes) is None

    def test_empty_list(self) -> None:
        assert find_enclosing_node(5, []) is None


# ---------------------------------------------------------------------------
# Comment extraction
# ---------------------------------------------------------------------------


class TestCommentExtraction:
    def test_python_comments(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "# This is a comment\n"
            "x = 1  # inline\n"
            "# TODO: fix this\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["comments"]["total"] == 3
        assert output["comments"]["with_markers"] == 1

        # Check the TODO marker
        todo_comments = [c for c in output["comments"]["items"] if c["markers"]]
        assert len(todo_comments) == 1
        assert "TODO" in todo_comments[0]["markers"]

    def test_typescript_comments(self, enricher: TreeSitterEnricher, ts_src: Path) -> None:
        (ts_src / "test.ts").write_text(
            "// Line comment\n"
            "/* Block comment */\n"
            "// FIXME: broken\n"
        )
        enricher.enrich_typescript(ts_src)
        output = enricher.build_output()

        assert output["comments"]["total"] == 3
        comments = output["comments"]["items"]
        types = {c["type"] for c in comments}
        assert "inline" in types
        assert "block" in types

    def test_comment_node_association(
        self, enricher_with_graph: TreeSitterEnricher, py_src: Path
    ) -> None:
        (py_src / "test_module.py").write_text(
            "# line 1\n"
            "def foo():\n"
            "    # inside foo (line 3)\n"
            "    pass\n"
        )
        enricher_with_graph.enrich_python(py_src)
        output = enricher_with_graph.build_output()

        comments = output["comments"]["items"]
        # Comment on line 3 should be associated with foo (span 1-10)
        inner_comments = [c for c in comments if c["line"] == 3]
        assert len(inner_comments) == 1
        assert inner_comments[0]["enclosing_node"] == "py:test_module.foo"


# ---------------------------------------------------------------------------
# Python patterns
# ---------------------------------------------------------------------------


class TestPythonPatterns:
    def test_bare_except(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "try:\n"
            "    pass\n"
            "except:\n"
            "    pass\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["bare_except"]["count"] == 1

    def test_broad_except(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "try:\n"
            "    pass\n"
            "except Exception:\n"
            "    pass\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["broad_except"]["count"] == 1

    def test_typed_except_not_bare(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "try:\n"
            "    pass\n"
            "except ValueError:\n"
            "    pass\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["bare_except"]["count"] == 0

    def test_dotted_except_not_bare(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "import json\n"
            "try:\n"
            "    pass\n"
            "except json.JSONDecodeError:\n"
            "    pass\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["bare_except"]["count"] == 0

    def test_context_managers(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "with open('file') as f:\n"
            "    data = f.read()\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["context_managers"]["count"] == 1

    def test_type_hints(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "def greet(name: str) -> str:\n"
            "    return f'Hello {name}'\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        hints = output["python_patterns"]["type_hints"]["items"]
        kinds = {h["kind"] for h in hints}
        assert "return_type" in kinds
        assert "param_type" in kinds

    def test_assertions(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "assert True\n"
            "assert x > 0, 'x must be positive'\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["python_patterns"]["assertions"]["count"] == 2


# ---------------------------------------------------------------------------
# TypeScript patterns
# ---------------------------------------------------------------------------


class TestTypeScriptPatterns:
    def test_empty_catch(self, enricher: TreeSitterEnricher, ts_src: Path) -> None:
        (ts_src / "test.ts").write_text(
            "try {\n"
            "  doSomething();\n"
            "} catch {\n"
            "}\n"
        )
        enricher.enrich_typescript(ts_src)
        output = enricher.build_output()

        assert output["typescript_patterns"]["empty_catch"]["count"] == 1
        assert output["typescript_patterns"]["catch_clauses"]["count"] == 1

    def test_non_empty_catch(self, enricher: TreeSitterEnricher, ts_src: Path) -> None:
        (ts_src / "test.ts").write_text(
            "try {\n"
            "  doSomething();\n"
            "} catch (e) {\n"
            "  console.log(e);\n"
            "}\n"
        )
        enricher.enrich_typescript(ts_src)
        output = enricher.build_output()

        assert output["typescript_patterns"]["empty_catch"]["count"] == 0
        assert output["typescript_patterns"]["catch_clauses"]["count"] == 1

    def test_dynamic_import(self, enricher: TreeSitterEnricher, ts_src: Path) -> None:
        (ts_src / "test.ts").write_text(
            "const mod = await import('./module');\n"
        )
        enricher.enrich_typescript(ts_src)
        output = enricher.build_output()

        assert output["typescript_patterns"]["dynamic_imports"]["count"] == 1


# ---------------------------------------------------------------------------
# Security patterns
# ---------------------------------------------------------------------------


class TestSecurityPatterns:
    def test_eval_detection(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "result = eval('1 + 2')\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        assert output["security_patterns"]["total"] >= 1
        eval_findings = [
            f for f in output["security_patterns"]["items"]
            if f["category"] == "eval_exec"
        ]
        assert len(eval_findings) >= 1

    def test_exec_detection(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "exec('print(1)')\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        eval_findings = [
            f for f in output["security_patterns"]["items"]
            if f["category"] == "eval_exec"
        ]
        assert len(eval_findings) >= 1

    def test_no_false_positives(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "x = tuple()\n"
            "y = set()\n"
            "print('hello')\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        eval_findings = [
            f for f in output["security_patterns"]["items"]
            if f["category"] == "eval_exec"
        ]
        assert len(eval_findings) == 0

    def test_sql_concatenation(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "query = 'SELECT * FROM users WHERE id = ' + user_id\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        sql_findings = [
            f for f in output["security_patterns"]["items"]
            if f["category"] == "sql_concatenation"
        ]
        assert len(sql_findings) >= 1

    def test_hardcoded_secret(self, enricher: TreeSitterEnricher, py_src: Path) -> None:
        (py_src / "test.py").write_text(
            "api_key = 'sk-1234567890'\n"
        )
        enricher.enrich_python(py_src)
        output = enricher.build_output()

        secret_findings = [
            f for f in output["security_patterns"]["items"]
            if f["category"] == "hardcoded_secret"
        ]
        assert len(secret_findings) >= 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_main(self, py_src: Path, tmp_path: Path) -> None:
        from enrich_with_treesitter import main

        (py_src / "test.py").write_text("# Hello\nx = 1\n")
        output = tmp_path / "enrichment.json"

        rc = main([
            "--python-src", str(py_src),
            "--queries", str(QUERIES_DIR),
            "--output", str(output),
        ])
        assert rc == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "comments" in data
        assert "python_patterns" in data

    def test_missing_src_dir(self, tmp_path: Path) -> None:
        from enrich_with_treesitter import main

        output = tmp_path / "enrichment.json"
        rc = main([
            "--python-src", str(tmp_path / "nonexistent"),
            "--queries", str(QUERIES_DIR),
            "--output", str(output),
        ])
        assert rc == 0  # Graceful skip, not error
