"""Tests for the judged decision-tag backfill classifier (ri-12).

Covers: _classify_phase_decisions's batched-question shape and degradation
contract (whole-batch and per-decision), and propose_tags_for_archive's
wiring of the judgment -- including that all decisions in one session-log
phase are answered in a single batched call, that a "none" choice is
excluded from proposed edits, and that the keyword map stays the fallback
when the judgment is unavailable, unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

_SKILLS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SKILLS_DIR / "explore-feature" / "scripts"))

import backfill_decision_tags as bdt  # noqa: E402

KEYWORD_MAP = {
    "software-factory-tooling": ["worktree", "branch"],
    "agent-coordinator": ["coordinator", "lock"],
    "skill-workflow": ["session-log", "sanitize"],
    "codebase-analysis": ["tree-sitter", "exemplar"],
}


def _choice_answer(choice: str, confidence: float, probabilities: dict | None = None) -> dict:
    return {
        "choice": choice,
        "confidence": confidence,
        "probabilities": probabilities or {choice: confidence},
    }


def _write_session_log(change_dir: Path, content: str) -> Path:
    change_dir.mkdir(parents=True, exist_ok=True)
    log = change_dir / "session-log.md"
    log.write_text(dedent(content).lstrip("\n"))
    return log


class TestClassifyPhaseDecisions:
    def test_no_module_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(bdt, "system_one_decisions", None)
        result = bdt._classify_phase_decisions(
            [(1, "Pin worktrees", "prevents GC")], KEYWORD_MAP,
        )
        assert result is None

    def test_no_decisions_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        assert bdt._classify_phase_decisions([], KEYWORD_MAP) is None
        fake_module.decide.assert_not_called()

    def test_decide_returns_none(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        result = bdt._classify_phase_decisions(
            [(1, "Pin worktrees", "prevents GC")], KEYWORD_MAP,
        )
        assert result is None

    def test_batches_one_question_per_decision(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        decisions = [
            (1, "Pin worktrees", "prevents GC"),
            (2, "Register coordinator MCP server", "enables lock/claim"),
        ]
        bdt._classify_phase_decisions(decisions, KEYWORD_MAP)
        state, questions = fake_module.decide.call_args[0]
        assert set(questions) == {"capability_1", "capability_2"}
        assert {d["index"] for d in state["decisions"]} == {1, 2}
        assert set(questions["capability_1"]["criteria"]) == set(KEYWORD_MAP) | {"none"}

    def test_confident_answer_is_used(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer(
                "software-factory-tooling", 0.9,
                {"software-factory-tooling": 0.9, "agent-coordinator": 0.1},
            ),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        result = bdt._classify_phase_decisions(
            [(1, "Pin worktrees", "prevents GC")], KEYWORD_MAP,
        )
        cap, confidence, probabilities = result[1]
        assert cap == "software-factory-tooling"
        assert confidence == 0.9
        assert probabilities == {"software-factory-tooling": 0.9, "agent-coordinator": 0.1}

    def test_none_choice_maps_to_none_capability(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer("none", 0.7),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        result = bdt._classify_phase_decisions(
            [(1, "Pick a shade of blue", "unrelated")], KEYWORD_MAP,
        )
        cap, confidence, _probabilities = result[1]
        assert cap is None
        assert confidence == 0.7

    def test_unrecognized_choice_is_absent_from_result(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer("something_invented", 0.9),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        result = bdt._classify_phase_decisions(
            [(1, "Pin worktrees", "prevents GC")], KEYWORD_MAP,
        )
        assert 1 not in result

    def test_one_malformed_decision_does_not_discard_the_rest_of_the_batch(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer("software-factory-tooling", 0.9),
            # capability_2 missing entirely -- a partial response.
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        decisions = [
            (1, "Pin worktrees", "prevents GC"),
            (2, "Register coordinator MCP server", "enables lock/claim"),
        ]
        result = bdt._classify_phase_decisions(decisions, KEYWORD_MAP)
        assert 1 in result
        assert 2 not in result

    def test_dry_run_is_threaded_into_decide(self, monkeypatch) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)
        bdt._classify_phase_decisions(
            [(1, "Pin worktrees", "prevents GC")], KEYWORD_MAP, dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True


class TestProposeTagsForArchiveJudgedOverride:
    def test_single_batched_call_per_phase(self, monkeypatch, tmp_path: Path) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer("software-factory-tooling", 0.9),
            "capability_2": _choice_answer("agent-coordinator", 0.9),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-two-decisions",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            2. **Register coordinator MCP server** — enables lock/claim primitives
            """,
        )

        bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )
        assert fake_module.decide.call_count == 1, (
            "both decisions in the same phase must be answered by one call"
        )

    def test_judged_choice_populates_the_proposal(self, monkeypatch, tmp_path: Path) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer(
                "software-factory-tooling", 0.87,
                {"software-factory-tooling": 0.87, "agent-coordinator": 0.05},
            ),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-worktree",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            """,
        )

        report = bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )
        p = report.proposals[0]
        assert p.proposed_capability == "software-factory-tooling"
        assert p.confidence == 0.87
        assert report.high_confidence == 1

    def test_none_choice_is_excluded_from_proposed_edits(self, monkeypatch, tmp_path: Path) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = {
            "capability_1": _choice_answer("none", 0.8),
        }
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-unrelated",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pick a shade of blue for the UI** — unrelated to any capability
            """,
        )

        report = bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )
        p = report.proposals[0]
        assert p.proposed_capability is None
        assert report.no_match == 1

    def test_repeated_phase_name_and_date_are_batched_as_separate_blocks(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Codex P1 (PR #600): a session-log can repeat the same `## Phase:`
        name and date across multiple distinct blocks (e.g. multi-round plan
        review). Grouping by (phase_name, phase_date) alone would merge their
        decisions -- both blocks' "1." collide on one `decision_index` key,
        so a single answer gets silently applied to two unrelated decisions.
        Each block MUST get its own batched call and its own answer.
        """
        fake_module = MagicMock()
        fake_module.decide.side_effect = [
            {"capability_1": _choice_answer("software-factory-tooling", 0.9)},
            {"capability_1": _choice_answer("agent-coordinator", 0.85)},
        ]
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-09-11-repeated-phase",
            """
            # Session Log

            ## Phase: Plan Review (2026-09-11)

            ### Decisions
            1. **Return the proposal to PLAN_FIX** — worktree pin missing

            ## Phase: Plan Review (2026-09-11)

            ### Decisions
            1. **Return revision 3 to PLAN_FIX** — coordinator lock contract gap
            """,
        )

        report = bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )

        assert fake_module.decide.call_count == 2, (
            "each repeated-name-and-date block must get its own batched call"
        )
        by_title = {p.title: p for p in report.proposals}
        assert (
            by_title["Return the proposal to PLAN_FIX"].proposed_capability
            == "software-factory-tooling"
        )
        assert (
            by_title["Return revision 3 to PLAN_FIX"].proposed_capability
            == "agent-coordinator"
        )

    def test_unavailable_judgment_falls_back_to_keyword_map_unchanged(self, monkeypatch, tmp_path: Path) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

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

        report = bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json",
        )
        p = report.proposals[0]
        assert p.proposed_capability == "software-factory-tooling"
        assert p.confidence > 0.5

    def test_dry_run_reaches_the_judgment(self, monkeypatch, tmp_path: Path) -> None:
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-worktree",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            """,
        )

        bdt.propose_tags_for_archive(
            archive_root=archive, keyword_map=KEYWORD_MAP,
            output_path=tmp_path / "proposals.json", dry_run=True,
        )
        assert fake_module.decide.call_args.kwargs["dry_run"] is True

    def test_no_file_is_written_by_the_script_without_an_output_path(self, monkeypatch, tmp_path: Path) -> None:
        """propose_tags_for_archive only proposes -- it never edits markdown,
        and writes JSON only when the caller explicitly asks for it."""
        fake_module = MagicMock()
        fake_module.decide.return_value = None
        monkeypatch.setattr(bdt, "system_one_decisions", fake_module)

        archive = tmp_path / "archive"
        _write_session_log(
            archive / "2026-02-06-worktree",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** — prevents GC during idle
            """,
        )

        bdt.propose_tags_for_archive(archive_root=archive, keyword_map=KEYWORD_MAP)
        assert list(tmp_path.glob("*.json")) == []
