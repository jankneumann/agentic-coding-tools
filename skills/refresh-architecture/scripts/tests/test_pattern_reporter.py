"""Tests for the pattern reporter insight module."""

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

from insights.pattern_reporter import compute_pattern_insights, main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enrichment() -> dict[str, Any]:
    return {
        "python_patterns": {
            "bare_except": {
                "count": 2,
                "items": [
                    {"file": "a.py", "line": 5, "enclosing_node": None},
                    {"file": "b.py", "line": 10, "enclosing_node": None},
                ],
            },
            "broad_except": {
                "count": 3,
                "items": [
                    {"file": "a.py", "line": 15, "enclosing_node": None},
                    {"file": "a.py", "line": 25, "enclosing_node": None},
                    {"file": "c.py", "line": 5, "enclosing_node": None},
                ],
            },
            "context_managers": {"count": 1, "items": [
                {"file": "a.py", "line": 30, "enclosing_node": None},
            ]},
            "type_hints": {
                "count": 4,
                "items": [
                    {"file": "a.py", "line": 1, "function": "foo", "kind": "return_type",
                     "enclosing_node": None},
                    {"file": "a.py", "line": 1, "parameter": "x", "kind": "param_type",
                     "enclosing_node": None},
                    {"file": "b.py", "line": 1, "function": "bar", "kind": "return_type",
                     "enclosing_node": None},
                    {"file": "b.py", "line": 1, "parameter": "y", "kind": "param_type",
                     "enclosing_node": None},
                ],
            },
            "assertions": {"count": 0, "items": []},
        },
        "typescript_patterns": {
            "empty_catch": {"count": 1, "items": [
                {"file": "x.ts", "line": 3, "is_empty": True, "enclosing_node": None},
            ]},
            "catch_clauses": {"count": 2, "items": [
                {"file": "x.ts", "line": 3, "is_empty": True, "enclosing_node": None},
                {"file": "x.ts", "line": 10, "is_empty": False, "enclosing_node": None},
            ]},
            "dynamic_imports": {"count": 0, "items": []},
        },
        "security_patterns": {
            "total": 1,
            "by_severity": {"high": 1},
            "items": [
                {"file": "a.py", "line": 50, "category": "eval_exec",
                 "severity": "high", "detail": "eval() usage", "enclosing_node": None},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputePatternInsights:
    def test_python_patterns(self, enrichment: dict) -> None:
        result = compute_pattern_insights(enrichment)
        assert result["python_patterns"]["bare_except"]["count"] == 2
        assert result["python_patterns"]["broad_except"]["count"] == 3
        assert "a.py" in result["python_patterns"]["broad_except"]["files"]

    def test_type_hint_coverage(self, enrichment: dict) -> None:
        result = compute_pattern_insights(enrichment)
        assert result["type_hint_coverage"]["functions_with_return_type"] == 2
        assert result["type_hint_coverage"]["typed_parameters"] == 2

    def test_exception_handling(self, enrichment: dict) -> None:
        result = compute_pattern_insights(enrichment)
        assert result["exception_handling"]["bare_except"] == 2
        assert result["exception_handling"]["broad_except"] == 3
        assert result["exception_handling"]["total_except_issues"] == 5

    def test_typescript_patterns(self, enrichment: dict) -> None:
        result = compute_pattern_insights(enrichment)
        assert result["typescript_patterns"]["empty_catch"]["count"] == 1
        assert result["typescript_patterns"]["catch_clauses"]["count"] == 2

    def test_security(self, enrichment: dict) -> None:
        result = compute_pattern_insights(enrichment)
        assert result["security"]["total"] == 1
        assert result["security"]["by_severity"] == {"high": 1}
        assert "eval_exec" in result["security"]["by_category"]

    def test_empty_enrichment(self) -> None:
        result = compute_pattern_insights({})
        assert result["exception_handling"]["total_except_issues"] == 0
        assert result["security"]["total"] == 0


class TestCLI:
    def test_main(self, tmp_path: Path, enrichment: dict) -> None:
        input_dir = tmp_path / "arch"
        input_dir.mkdir()
        with open(input_dir / "treesitter_enrichment.json", "w") as f:
            json.dump(enrichment, f)
        output = tmp_path / "pattern_insights.json"

        rc = main(["--input-dir", str(input_dir), "--output", str(output)])
        assert rc == 0
        assert output.exists()
        data = json.loads(output.read_text())
        assert "python_patterns" in data
        assert "security" in data

    def test_missing_input(self, tmp_path: Path) -> None:
        rc = main(["--input-dir", str(tmp_path), "--output", str(tmp_path / "out.json")])
        assert rc == 0  # Graceful skip
