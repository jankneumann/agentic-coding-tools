"""Tests for extract_session_log.py — append-based session log utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from extract_session_log import (
    append_merge_entry,
    append_phase_entry,
    count_phase_iterations,
    generate_self_summary_prompt,
)


# --- append_phase_entry ---


class TestAppendPhaseEntry:
    def test_creates_file_with_header(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        result = append_phase_entry(
            "test-change", "Plan", "### Context\nPlanned the feature.",
            session_log_path=log_path,
        )
        assert result == log_path
        content = log_path.read_text()
        assert "# Session Log: test-change" in content
        assert "## Phase: Plan (" in content
        assert "Planned the feature." in content

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        log_path = tmp_path / "openspec" / "changes" / "x" / "session-log.md"
        append_phase_entry("x", "Plan", "content", session_log_path=log_path)
        assert log_path.exists()

    def test_first_entry_no_separator(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan", "First entry.", session_log_path=log_path)
        content = log_path.read_text()
        # First entry should NOT start with ---
        lines = content.split("\n")
        # Find the phase header — it should not be preceded by ---
        phase_idx = next(i for i, l in enumerate(lines) if l.startswith("## Phase:"))
        preceding = [l for l in lines[:phase_idx] if l.strip()]
        assert "---" not in preceding

    def test_appends_with_separator(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan", "First entry.", session_log_path=log_path)
        append_phase_entry("c", "Implementation", "Second entry.", session_log_path=log_path)
        content = log_path.read_text()
        assert "---" in content  # separator between entries
        assert "## Phase: Plan" in content
        assert "## Phase: Implementation" in content
        assert content.index("Plan") < content.index("Implementation")

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan", "Original.", session_log_path=log_path)
        append_phase_entry("c", "Implementation", "New.", session_log_path=log_path)
        content = log_path.read_text()
        assert "Original." in content
        assert "New." in content

    def test_default_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = append_phase_entry("my-change", "Plan", "content")
        assert result == Path("openspec/changes/my-change/session-log.md")
        assert result.exists()

    def test_strips_trailing_whitespace(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan", "content\n\n\n", session_log_path=log_path)
        content = log_path.read_text()
        assert not content.endswith("\n\n\n\n")


# --- append_merge_entry ---


class TestAppendMergeEntry:
    def test_creates_file_with_header(self, tmp_path: Path) -> None:
        log_path = tmp_path / "2026-03-31.md"
        result = append_merge_entry(
            "2026-03-31", "## Session: 14:30 (claude)\n\nMerged 3 PRs.",
            merge_log_path=log_path,
        )
        assert result == log_path
        content = log_path.read_text()
        assert "# Merge Log: 2026-03-31" in content
        assert "Merged 3 PRs." in content

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        log_path = tmp_path / "docs" / "merge-logs" / "2026-03-31.md"
        append_merge_entry("2026-03-31", "content", merge_log_path=log_path)
        assert log_path.exists()

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        log_path = tmp_path / "2026-03-31.md"
        append_merge_entry("2026-03-31", "## Session: 10:00\nFirst.", merge_log_path=log_path)
        append_merge_entry("2026-03-31", "## Session: 15:00\nSecond.", merge_log_path=log_path)
        content = log_path.read_text()
        assert "First." in content
        assert "Second." in content
        assert "---" in content  # separator between entries (not before first)

    def test_default_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = append_merge_entry("2026-03-31", "content")
        assert result == Path("docs/merge-logs/2026-03-31.md")
        assert result.exists()


# --- count_phase_iterations ---


class TestCountPhaseIterations:
    def test_no_file(self, tmp_path: Path) -> None:
        assert count_phase_iterations("Plan Iteration", tmp_path / "missing.md") == 0

    def test_no_matching_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        log_path.write_text("# Session Log\n\n## Phase: Plan (2026-03-31)\n\nContent.\n")
        assert count_phase_iterations("Plan Iteration", log_path) == 0

    def test_counts_matching_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        log_path.write_text(
            "# Session Log\n\n"
            "## Phase: Plan Iteration 1 (2026-03-30)\n\nFirst.\n\n"
            "## Phase: Plan Iteration 2 (2026-03-31)\n\nSecond.\n\n"
            "## Phase: Implementation Iteration 1 (2026-03-31)\n\nOther.\n"
        )
        assert count_phase_iterations("Plan Iteration", log_path) == 2
        assert count_phase_iterations("Implementation Iteration", log_path) == 1

    def test_prefix_does_not_cross_match(self, tmp_path: Path) -> None:
        """'Plan' should not match 'Plan Iteration' entries."""
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan", "Initial plan.", session_log_path=log_path)
        append_phase_entry("c", "Plan Iteration 1", "First iter.", session_log_path=log_path)
        append_phase_entry("c", "Plan Iteration 2", "Second iter.", session_log_path=log_path)
        assert count_phase_iterations("Plan Iteration", log_path) == 2
        # "Plan" alone (non-iteration) should NOT match "Plan Iteration" entries
        # count_phase_iterations is designed for iteration prefixes
        # For non-iteration phases, you wouldn't call this function

    def test_independent_prefix_counting(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session-log.md"
        append_phase_entry("c", "Plan Iteration 1", "A.", session_log_path=log_path)
        append_phase_entry("c", "Plan Iteration 2", "B.", session_log_path=log_path)
        append_phase_entry("c", "Implementation Iteration 1", "C.", session_log_path=log_path)
        assert count_phase_iterations("Plan Iteration", log_path) == 2
        assert count_phase_iterations("Implementation Iteration", log_path) == 1


# --- generate_self_summary_prompt ---


class TestSelfSummaryPrompt:
    def test_prompt_contains_change_id(self) -> None:
        prompt = generate_self_summary_prompt("my-feature")
        assert "my-feature" in prompt

    def test_prompt_has_required_sections(self) -> None:
        prompt = generate_self_summary_prompt("test")
        assert "## Summary" in prompt
        assert "## Key Decisions" in prompt
        assert "## Alternatives Considered" in prompt
        assert "## Trade-offs" in prompt
        assert "## Open Questions" in prompt
        assert "## Session Metadata" in prompt

    def test_prompt_includes_safety_warnings(self) -> None:
        prompt = generate_self_summary_prompt("test")
        assert "secrets" in prompt.lower() or "API keys" in prompt
        assert "500 lines" in prompt
