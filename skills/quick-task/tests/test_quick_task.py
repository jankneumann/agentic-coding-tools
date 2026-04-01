"""Tests for quick-task dispatch."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from quick_task import check_complexity, parse_args


class TestParseArgs:
    def test_basic_prompt(self):
        args = parse_args(["Fix", "the", "bug"])
        assert args.prompt == ["Fix", "the", "bug"]
        assert args.vendor is None
        assert args.timeout == 300

    def test_vendor_flag(self):
        args = parse_args(["--vendor", "codex", "Fix", "bug"])
        assert args.vendor == "codex"
        assert args.prompt == ["Fix", "bug"]

    def test_timeout_flag(self):
        args = parse_args(["--timeout", "600", "Do", "something"])
        assert args.timeout == 600

    def test_cwd_flag(self):
        args = parse_args(["--cwd", "/tmp", "task"])
        assert args.cwd == "/tmp"

    def test_defaults(self):
        args = parse_args(["hello"])
        assert args.vendor is None
        assert args.timeout == 300
        assert args.cwd == "."


class TestComplexityCheck:
    def test_short_prompt_passes(self):
        assert check_complexity("Fix the bug in main.py") is None

    def test_long_prompt_warns(self):
        long_prompt = " ".join(["word"] * 501)
        warning = check_complexity(long_prompt)
        assert warning is not None
        assert "501 words" in warning
        assert "/plan-feature" in warning

    def test_many_file_refs_warns(self):
        prompt = (
            "Fix src/a.py src/b.py src/c.py "
            "src/d.py src/e.py src/f.py"
        )
        warning = check_complexity(prompt)
        assert warning is not None
        assert "/plan-feature" in warning

    def test_few_file_refs_passes(self):
        prompt = "Fix src/a.py and src/b.py"
        assert check_complexity(prompt) is None

    def test_exactly_500_words_passes(self):
        prompt = " ".join(["word"] * 500)
        assert check_complexity(prompt) is None
