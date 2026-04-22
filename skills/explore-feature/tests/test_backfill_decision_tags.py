"""Tests for the backfill classifier that proposes `architectural:` tags
for untagged Decisions in archived session-logs.

Design: see openspec/changes/add-decision-index/design.md §Backfill strategy

Classifier goals:
- Route decisions to the best-matching capability via keyword overlap.
- Report a confidence score that distinguishes clear winners from ambiguous cases.
- Only emit proposals — never edit files. Edits happen after agent review.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

_SKILLS_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR / "explore-feature" / "scripts"))

from backfill_decision_tags import (  # noqa: E402
    ClassificationProposal,
    classify_decision,
    propose_tags_for_archive,
)

# ── Keyword map fixtures ────────────────────────────────────────────


KEYWORD_MAP = {
    "software-factory-tooling": [
        "worktree",
        "branch",
        "merge_worktrees",
        "git-worktree",
        "archive_index",
    ],
    "agent-coordinator": [
        "coordinator",
        "lock",
        "claim",
        "work_queue",
        "agent registry",
    ],
    "skill-workflow": [
        "session-log",
        "sanitize",
        "phase entry",
        "tasks.md",
        "proposal",
    ],
    "codebase-analysis": [
        "tree-sitter",
        "exemplar",
        "spec compliance",
    ],
}


# ── classify_decision — single-decision routing ─────────────────────


class TestClassifyDecision:
    def test_routes_decision_to_best_keyword_match(self) -> None:
        proposals = classify_decision(
            title="Pin worktrees during overnight pauses",
            rationale="prevents GC during idle",
            keyword_map=KEYWORD_MAP,
        )

        assert len(proposals) >= 1
        top_capability, top_confidence = proposals[0]
        assert top_capability == "software-factory-tooling"
        assert top_confidence > 0.5

    def test_returns_empty_when_no_keyword_matches(self) -> None:
        proposals = classify_decision(
            title="Some wholly unrelated decision",
            rationale="nothing to see here",
            keyword_map=KEYWORD_MAP,
        )
        assert proposals == []

    def test_ambiguous_hits_lower_confidence(self) -> None:
        """When multiple capabilities tie on hit counts, confidence is lower."""
        proposals = classify_decision(
            title="Worktree coordinator",
            rationale="spans both areas",
            keyword_map=KEYWORD_MAP,
        )
        # Both worktree (→ software-factory-tooling) and coordinator (→ agent-coordinator) hit once.
        assert len(proposals) >= 2
        top_conf = proposals[0][1]
        runner_up_conf = proposals[1][1]
        # Ambiguity shows as: runner-up not crushed by the winner
        assert runner_up_conf >= top_conf * 0.4

    def test_clear_winner_higher_confidence(self) -> None:
        """Multiple keyword hits on one capability → high confidence."""
        proposals = classify_decision(
            title="Use merge_worktrees branch-aware registry to track worktree lifecycle",
            rationale="archive_index and worktree lifecycle should share the walker",
            keyword_map=KEYWORD_MAP,
        )
        top_capability, top_confidence = proposals[0]
        assert top_capability == "software-factory-tooling"
        assert top_confidence > 0.8

    def test_returns_multiple_candidates_with_descending_confidence(self) -> None:
        """When multiple capabilities match, return them all, sorted."""
        proposals = classify_decision(
            title="Refine session-log sanitize to preserve worktree paths",
            rationale="skill-workflow tests should continue to pass after worktree edits",
            keyword_map=KEYWORD_MAP,
        )
        assert len(proposals) >= 2
        confidences = [c for _, c in proposals]
        assert confidences == sorted(confidences, reverse=True)


# ── propose_tags_for_archive — walk + classify + emit JSON ──────────


def _write_session_log(change_dir: Path, content: str) -> Path:
    change_dir.mkdir(parents=True, exist_ok=True)
    log = change_dir / "session-log.md"
    log.write_text(dedent(content).lstrip("\n"))
    return log


class TestProposeTagsForArchive:
    def test_walks_archive_and_emits_proposals_json(self, tmp_path: Path) -> None:
        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-add-worktree-isolation",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            """,
        )
        _write_session_log(
            archive / "2026-02-08-coordinator-mcp-setup",
            """
            # Session Log

            ## Phase: Implementation (2026-02-08)

            ### Decisions
            1. **Register coordinator MCP server** — enables lock/claim primitives
            """,
        )

        output = tmp_path / "proposals.json"
        report = propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=output,
        )

        assert output.is_file()
        data = json.loads(output.read_text())
        assert data["archive_root"].endswith("archive")
        assert data["total_decisions_scanned"] == 2
        assert len(data["proposals"]) == 2

        # And the returned report mirrors the JSON
        assert report.total_decisions_scanned == 2
        assert len(report.proposals) == 2

    def test_skips_already_tagged_decisions(self, tmp_path: Path) -> None:
        """Only untagged Decisions become proposals — tagged ones stay as-is."""
        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-worktree",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees** `architectural: software-factory-tooling` — already tagged
            2. **Use merge_worktrees for branch convergence** — untagged candidate
            """,
        )

        report = propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )

        assert report.total_decisions_scanned == 1
        assert len(report.proposals) == 1
        assert report.proposals[0].title.startswith("Use merge_worktrees")

    def test_proposal_carries_change_context(self, tmp_path: Path) -> None:
        """Each proposal records enough to locate the source bullet."""
        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-add-worktree-isolation",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            """,
        )

        report = propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )

        p = report.proposals[0]
        assert isinstance(p, ClassificationProposal)
        assert p.change_id == "2026-02-06-add-worktree-isolation"
        assert p.phase_name == "Plan"
        assert p.phase_date == date(2026, 2, 6)
        assert p.decision_index == 1
        assert p.title == "Pin worktrees during overnight pauses"
        assert p.rationale == "prevents GC during idle"
        assert p.proposed_capability == "software-factory-tooling"
        assert p.confidence > 0.5

    def test_deterministic_output_across_runs(self, tmp_path: Path) -> None:
        """Same input → same JSON (byte-identical, sorted)."""
        archive = tmp_path / "archive"
        for change_id in [
            "2026-02-06-a",
            "2026-02-08-b",
            "2026-03-01-c",
        ]:
            _write_session_log(
                archive / change_id,
                f"""
                # Session Log

                ## Phase: Plan (2026-02-06)

                ### Decisions
                1. **Worktree decision for {change_id}** — branch-aware change
                """,
            )

        out1 = tmp_path / "run1.json"
        out2 = tmp_path / "run2.json"
        propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=out1,
        )
        propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=out2,
        )

        # Byte-identical output except for the `generated_at` timestamp.
        # Strip timestamps and compare.
        def _strip_ts(path: Path) -> dict:
            d = json.loads(path.read_text())
            d.pop("generated_at", None)
            return d

        assert _strip_ts(out1) == _strip_ts(out2)

    def test_no_session_log_returns_empty_report(self, tmp_path: Path) -> None:
        """Archive root with no session-logs → empty proposals, no errors."""
        archive = tmp_path / "empty_archive"
        archive.mkdir()

        report = propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )

        assert report.total_decisions_scanned == 0
        assert report.proposals == []

    def test_confidence_bucketing_counts_match(self, tmp_path: Path) -> None:
        """Report includes counts of high/medium/low confidence + no-match proposals."""
        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-clear-winner",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Use merge_worktrees branch-aware archive_index registry** — worktree-heavy
            """,
        )
        _write_session_log(
            archive / "2026-02-08-no-match",
            """
            # Session Log

            ## Phase: Plan (2026-02-08)

            ### Decisions
            1. **Pick a shade of blue for the UI** — unrelated to any capability
            """,
        )

        report = propose_tags_for_archive(
            archive_root=archive,
            keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )

        total = (
            report.high_confidence
            + report.medium_confidence
            + report.low_confidence
            + report.no_match
        )
        assert total == report.total_decisions_scanned
