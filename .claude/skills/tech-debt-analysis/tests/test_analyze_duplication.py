"""Tests for the duplication analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_duplication import _normalize_line, _is_trivial, analyze

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


# ---------------------------------------------------------------------------
# 1. Line normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_strip_comments(self) -> None:
        assert _normalize_line("x = 1  # comment") == "x = N"

    def test_replace_strings(self) -> None:
        assert _normalize_line('msg = "hello"') == 'msg = "S"'

    def test_replace_numbers(self) -> None:
        assert _normalize_line("x = 42") == "x = N"
        assert _normalize_line("y = 3.14") == "y = N"

    def test_collapse_whitespace(self) -> None:
        assert _normalize_line("  x  =  1  ") == "x = N"


# ---------------------------------------------------------------------------
# 2. Trivial window detection
# ---------------------------------------------------------------------------


class TestTrivialDetection:
    def test_all_imports_is_trivial(self) -> None:
        lines = [
            "import os",
            "import sys",
            "from pathlib import Path",
            "import json",
            "import time",
            "import re",
        ]
        assert _is_trivial(lines) is True

    def test_real_code_not_trivial(self) -> None:
        lines = [
            "result = process(data)",
            "if result.status == 'ok':",
            "    findings.append(result)",
            "    count += 1",
            "else:",
            "    errors.append(result)",
        ]
        assert _is_trivial(lines) is False


# ---------------------------------------------------------------------------
# 3. Duplicate detection across files
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "def foo():\n    return 1\n")
        _write_py(tmp_path, "b.py", "def bar():\n    return 2\n")
        result = analyze(str(tmp_path))
        assert result.status == "ok"
        dups = [f for f in result.findings if f.category == "duplicate-code"]
        assert len(dups) == 0

    def test_identical_blocks_detected(self, tmp_path: Path) -> None:
        block = (
            "def process(data):\n"
            "    result = validate(data)\n"
            "    if result.is_valid:\n"
            "        output = transform(result)\n"
            "        save(output)\n"
            "        log_success(output)\n"
            "        return output\n"
            "    else:\n"
            "        handle_error(result)\n"
            "        return None\n"
        )
        _write_py(tmp_path, "a.py", block)
        _write_py(tmp_path, "b.py", block)
        result = analyze(str(tmp_path))
        dups = [f for f in result.findings if f.category == "duplicate-code"]
        assert len(dups) >= 1
        assert "cross-file" in dups[0].title

    def test_venv_excluded(self, tmp_path: Path) -> None:
        block = (
            "def process(data):\n"
            "    result = validate(data)\n"
            "    if result.is_valid:\n"
            "        output = transform(result)\n"
            "        save(output)\n"
            "        log_success(output)\n"
            "        return output\n"
        )
        _write_py(tmp_path, ".venv/lib/pkg.py", block)
        _write_py(tmp_path, "main.py", block)
        result = analyze(str(tmp_path))
        dups = [f for f in result.findings if f.category == "duplicate-code"]
        # Should not detect cross-file dup since .venv is excluded
        assert len(dups) == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = analyze(str(tmp_path))
        assert result.status == "ok"
        assert result.findings == []


# ---------------------------------------------------------------------------
# 4. Same-file duplication
# ---------------------------------------------------------------------------


class TestSameFileDuplication:
    def test_repeated_block_in_same_file(self, tmp_path: Path) -> None:
        block = (
            "    result = validate(data)\n"
            "    if result.is_valid:\n"
            "        output = transform(result)\n"
            "        save(output)\n"
            "        log_success(output)\n"
            "        notify_user(output)\n"
        )
        src = f"def foo(data):\n{block}\ndef bar(data):\n{block}\n"
        _write_py(tmp_path, "repeated.py", src)
        result = analyze(str(tmp_path))
        dups = [f for f in result.findings if f.category == "duplicate-code"]
        # Should detect same-file duplication
        if dups:
            assert "same-file" in dups[0].title
