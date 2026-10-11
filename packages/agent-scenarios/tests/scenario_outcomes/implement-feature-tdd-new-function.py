"""Outcomes for implement-feature-tdd-new-function."""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import Outcome

BROKEN_GATE = "new-test-exists"
_IMPL = (
    "def shout(text):\n    return text.upper()\n\n\n"
    "def word_count(text):\n    return len(text.split())\n"
)


def golden(workdir: Path) -> Outcome:
    test = (
        "from src.textutil import word_count\n\n\n"
        "def test_word_count():\n    assert word_count('a b  c') == 3\n"
    )
    return Outcome(
        new_branch="feature/word-count",
        write_files={"tests/test_word_count.py": test, "src/textutil.py": _IMPL},
        commit_message="feat: add word_count",
    )


def broken(workdir: Path) -> Outcome:
    # Implementation without the test.
    return Outcome(
        new_branch="feature/word-count",
        write_files={"src/textutil.py": _IMPL},
        commit_message="feat: add word_count",
    )
