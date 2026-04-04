"""Tests for the complexity analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_complexity import (
    _count_complexity,
    _function_line_count,
    _max_nesting,
    _param_count,
    _should_skip,
    analyze,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def _parse_func(source: str):
    """Parse source and return the first function AST node."""
    import ast
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found in source")


# ---------------------------------------------------------------------------
# 1. Long Method detection
# ---------------------------------------------------------------------------


class TestLongMethod:
    def test_short_function_no_finding(self, tmp_path: Path) -> None:
        src = "def foo():\n" + "    x = 1\n" * 10
        _write_py(tmp_path, "short.py", src)
        result = analyze(str(tmp_path))
        assert result.status == "ok"
        long_methods = [f for f in result.findings if f.category == "long-method"]
        assert len(long_methods) == 0

    def test_long_function_detected(self, tmp_path: Path) -> None:
        src = "def big_func():\n" + "    x = 1\n" * 60
        _write_py(tmp_path, "long.py", src)
        result = analyze(str(tmp_path))
        long_methods = [f for f in result.findings if f.category == "long-method"]
        assert len(long_methods) == 1
        assert long_methods[0].severity == "medium"
        assert "big_func" in long_methods[0].title

    def test_very_long_function_high_severity(self, tmp_path: Path) -> None:
        src = "def huge():\n" + "    x = 1\n" * 110
        _write_py(tmp_path, "huge.py", src)
        result = analyze(str(tmp_path))
        long_methods = [f for f in result.findings if f.category == "long-method"]
        assert len(long_methods) == 1
        assert long_methods[0].severity == "high"


# ---------------------------------------------------------------------------
# 2. Large File detection
# ---------------------------------------------------------------------------


class TestLargeFile:
    def test_small_file_no_finding(self, tmp_path: Path) -> None:
        src = "x = 1\n" * 50
        _write_py(tmp_path, "small.py", src)
        result = analyze(str(tmp_path))
        large = [f for f in result.findings if f.category == "large-file"]
        assert len(large) == 0

    def test_large_file_detected(self, tmp_path: Path) -> None:
        src = "x = 1\n" * 510
        _write_py(tmp_path, "big.py", src)
        result = analyze(str(tmp_path))
        large = [f for f in result.findings if f.category == "large-file"]
        assert len(large) >= 1
        assert large[0].severity == "medium"

    def test_very_large_file_high_severity(self, tmp_path: Path) -> None:
        src = "x = 1\n" * 1100
        _write_py(tmp_path, "massive.py", src)
        result = analyze(str(tmp_path))
        large = [f for f in result.findings if f.category == "large-file"]
        assert len(large) >= 1
        assert large[0].severity == "high"


# ---------------------------------------------------------------------------
# 3. Cyclomatic complexity
# ---------------------------------------------------------------------------


class TestComplexity:
    def test_simple_function(self) -> None:
        node = _parse_func("def foo():\n    return 1\n")
        assert _count_complexity(node) == 1

    def test_if_adds_complexity(self) -> None:
        src = "def foo(x):\n    if x:\n        return 1\n    return 2\n"
        node = _parse_func(src)
        assert _count_complexity(node) == 2

    def test_loops_and_exceptions(self) -> None:
        src = (
            "def foo(items):\n"
            "    for i in items:\n"
            "        try:\n"
            "            process(i)\n"
            "        except ValueError:\n"
            "            pass\n"
        )
        node = _parse_func(src)
        # base(1) + for(1) + except(1) = 3
        assert _count_complexity(node) == 3

    def test_boolean_operators(self) -> None:
        src = "def foo(a, b, c):\n    if a and b or c:\n        pass\n"
        node = _parse_func(src)
        # base(1) + if(1) + and(1) + or(1) = 4
        assert _count_complexity(node) >= 4

    def test_complex_function_detected(self, tmp_path: Path) -> None:
        # Build a function with complexity >= 10
        branches = "\n".join(
            f"    if x == {i}:\n        return {i}" for i in range(12)
        )
        src = f"def branchy(x):\n{branches}\n"
        _write_py(tmp_path, "branchy.py", src)
        result = analyze(str(tmp_path))
        complex_funcs = [f for f in result.findings if f.category == "complex-function"]
        assert len(complex_funcs) == 1


# ---------------------------------------------------------------------------
# 4. Deep nesting
# ---------------------------------------------------------------------------


class TestNesting:
    def test_flat_function(self) -> None:
        node = _parse_func("def foo():\n    return 1\n")
        assert _max_nesting(node) == 0

    def test_single_if(self) -> None:
        src = "def foo(x):\n    if x:\n        pass\n"
        node = _parse_func(src)
        assert _max_nesting(node) == 1

    def test_nested_ifs(self) -> None:
        src = (
            "def foo(a, b, c, d, e):\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        pass\n"
        )
        node = _parse_func(src)
        assert _max_nesting(node) == 5


# ---------------------------------------------------------------------------
# 5. Parameter count
# ---------------------------------------------------------------------------


class TestParamCount:
    def test_no_params(self) -> None:
        node = _parse_func("def foo(): pass\n")
        assert _param_count(node) == 0

    def test_self_excluded(self) -> None:
        node = _parse_func("def foo(self, a, b): pass\n")
        assert _param_count(node) == 2

    def test_cls_excluded(self) -> None:
        node = _parse_func("def foo(cls, a): pass\n")
        assert _param_count(node) == 1

    def test_many_params_detected(self, tmp_path: Path) -> None:
        src = "def many(a, b, c, d, e, f, g):\n    pass\n"
        _write_py(tmp_path, "many_params.py", src)
        result = analyze(str(tmp_path))
        param_findings = [f for f in result.findings if f.category == "parameter-excess"]
        assert len(param_findings) == 1
        assert param_findings[0].metric_value == 7

    def test_args_kwargs_counted(self) -> None:
        node = _parse_func("def foo(a, b, *args, **kwargs): pass\n")
        assert _param_count(node) == 4  # a, b, *args, **kwargs


# ---------------------------------------------------------------------------
# 6. Directory exclusion
# ---------------------------------------------------------------------------


class TestDirectoryExclusion:
    def test_venv_excluded(self, tmp_path: Path) -> None:
        _write_py(tmp_path, ".venv/lib/big.py", "def f():\n" + "    x = 1\n" * 60)
        _write_py(tmp_path, "ok.py", "x = 1\n")
        result = analyze(str(tmp_path))
        assert all(
            ".venv" not in f.file_path for f in result.findings
        )

    def test_should_skip_helper(self) -> None:
        assert _should_skip(Path(".venv/lib/foo.py")) is True
        assert _should_skip(Path("src/main.py")) is False


# ---------------------------------------------------------------------------
# 7. Empty / no-Python directories
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_directory(self, tmp_path: Path) -> None:
        result = analyze(str(tmp_path))
        assert result.status == "ok"
        assert result.findings == []

    def test_syntax_error_file_skipped(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "bad.py", "def broken(\n")
        _write_py(tmp_path, "good.py", "x = 1\n")
        result = analyze(str(tmp_path))
        assert result.status == "ok"
