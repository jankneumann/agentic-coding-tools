"""Tests for phase-outcome shadow adjudication (roadmap ri-07).

Covers spec scenarios (openspec/specs/skill-workflow/spec.md, "Phase
Outcome Shadow Adjudication"):
- A shadow record per phase transition appends claimed and judged
  outcomes with the evidence Noul
- transition() runs on the claimed outcome unchanged
- The adjudication degrades silently on unavailability
- A replayed apply-outcome call does not duplicate the shadow entry
- Disagreement attribution is exercised against a fixture shadow period

Design decisions: D1 (adjudication inside apply_phase_outcome, on the real
production path), D2 (question shape), D3 (independently best-effort
signal gathering), D4 (shared envelope reused from gatekeeper_shadow), D5
(attribution mechanism now, real-sprint data later), D6 (no record_degraded
reuse).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import system_one_decisions  # noqa: E402

import phase_agent  # noqa: E402
from autopilot import transition, LoopState  # noqa: E402
from phase_outcome_shadow import (  # noqa: E402
    attribute_disagreements,
    build_outcome_adjudication_entry,
    git_diff_stat,
    read_local_handoff,
    test_output_tail as _test_output_tail_fn,
)


def _spy_decide(monkeypatch, *, returns) -> MagicMock:
    mock = MagicMock(return_value=returns)
    monkeypatch.setattr(system_one_decisions, "decide", mock)
    return mock


def _choice_answer(choice: str, *, confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(choice=choice, confidence=confidence, probabilities={})


def _noul_answer(value: float) -> SimpleNamespace:
    return SimpleNamespace(noul=value)


def _answers(*, outcome: str, evidence: float) -> dict[str, object]:
    return {
        "outcome": _choice_answer(outcome),
        "evidence_supports_outcome": _noul_answer(evidence),
    }


def _shadow_entries(history: list[dict]) -> list[dict]:
    return [e for e in history if e.get("phase") == "PHASE_OUTCOME_SHADOW"]


# ---------------------------------------------------------------------------
# Signal gatherers (D3)
# ---------------------------------------------------------------------------


class TestGitDiffStat:
    def test_missing_worktree_returns_none(self, tmp_path: Path) -> None:
        assert git_diff_stat(tmp_path / "does-not-exist") is None

    def test_real_repo_returns_stat_or_none(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "checkout", "-q", "-b", "main"], cwd=repo, check=True)
        (repo / "f.txt").write_text("one\n")
        subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
            cwd=repo, check=True,
        )
        # No upstream/no diff yet -- main...HEAD is empty, git_diff_stat
        # returns None for an empty (but successful) diff.
        result = git_diff_stat(repo)
        assert result is None


class TestTestOutputTail:
    def test_missing_report_returns_none(self, tmp_path: Path) -> None:
        assert _test_output_tail_fn(tmp_path) is None

    def test_present_report_returns_tail(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text("\n".join(f"line {i}" for i in range(100)))

        tail = _test_output_tail_fn(tmp_path, lines=5)

        assert tail is not None
        assert "line 99" in tail
        assert "line 0" not in tail


class TestReadLocalHandoff:
    def test_no_handoffs_dir_returns_none(self, tmp_path: Path) -> None:
        assert read_local_handoff(tmp_path, "IMPLEMENT", "h1") is None

    def test_matching_file_is_read(self, tmp_path: Path) -> None:
        """The real writer names this "implementation-<n>.json" for
        IMPLEMENT (PhaseRecord._phase_slug() of handoff_builder's
        "Implementation" name, not a naive lowercase of "IMPLEMENT") --
        Codex regression, PR #592 P2."""
        handoffs = tmp_path / "handoffs"
        handoffs.mkdir()
        (handoffs / "implementation-1.json").write_text(json.dumps({"payload": {"summary": "did work"}}))

        record = read_local_handoff(tmp_path, "IMPLEMENT", "h1")

        assert record == {"payload": {"summary": "did work"}}

    def test_matching_file_is_read_for_validate(self, tmp_path: Path) -> None:
        handoffs = tmp_path / "handoffs"
        handoffs.mkdir()
        (handoffs / "validation-1.json").write_text(json.dumps({"payload": {"summary": "ran tests"}}))

        record = read_local_handoff(tmp_path, "VALIDATE", "h1")

        assert record == {"payload": {"summary": "ran tests"}}

    def test_matching_file_is_read_for_iteration_phase(self, tmp_path: Path) -> None:
        """PLAN_ITERATE's real handoff name embeds the iteration count
        ("Plan Iteration 3" -> "plan-iteration-3-<n>.json"); the slug
        prefix alone (without a known iteration number) still matches via
        the glob's own wildcard suffix."""
        handoffs = tmp_path / "handoffs"
        handoffs.mkdir()
        (handoffs / "plan-iteration-3-1.json").write_text(json.dumps({"payload": {"summary": "refined"}}))

        record = read_local_handoff(tmp_path, "PLAN_ITERATE", "h1")

        assert record == {"payload": {"summary": "refined"}}

    def test_old_naive_slug_no_longer_used(self, tmp_path: Path) -> None:
        """A file under the OLD, incorrect "implement-*" slug is not found --
        confirms the fix actually changed the glob prefix, not just added a
        second match."""
        handoffs = tmp_path / "handoffs"
        handoffs.mkdir()
        (handoffs / "implement-1.json").write_text(json.dumps({"payload": {}}))

        assert read_local_handoff(tmp_path, "IMPLEMENT", "h1") is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        handoffs = tmp_path / "handoffs"
        handoffs.mkdir()
        (handoffs / "implementation-1.json").write_text("{not json")

        assert read_local_handoff(tmp_path, "IMPLEMENT", "h1") is None


# ---------------------------------------------------------------------------
# build_outcome_adjudication_entry (D1, D2, D4)
# ---------------------------------------------------------------------------


class TestBuildOutcomeAdjudicationEntry:
    def test_records_claimed_and_judged_outcome_with_evidence_noul(self, monkeypatch) -> None:
        _spy_decide(monkeypatch, returns=_answers(outcome="failed", evidence=0.1))

        entry = build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=["complete", "failed"],
            handoff_record={"summary": "x"},
            diff_stat="1 file changed",
            test_output_tail="tail",
        )

        assert entry is not None
        assert entry["phase"] == "PHASE_OUTCOME_SHADOW"
        assert entry["acting_outcome"] == "complete"
        assert entry["judged_outcome"] == "failed"
        assert entry["judgment"]["evidence_noul"] == 0.1
        assert entry["judgment"]["phase"] == "IMPLEMENT"

    def test_calls_decide_exactly_once(self, monkeypatch) -> None:
        decide = _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))

        build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=["complete", "failed"],
            handoff_record=None,
            diff_stat="1 file changed",
            test_output_tail=None,
        )

        decide.assert_called_once()

    def test_module_unavailable_returns_none(self, monkeypatch) -> None:
        import phase_outcome_shadow

        monkeypatch.setattr(phase_outcome_shadow, "system_one_decisions", None)

        entry = phase_outcome_shadow.build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=["complete", "failed"],
            handoff_record=None,
            diff_stat="stat",
            test_output_tail=None,
        )

        assert entry is None

    def test_decide_returns_none_yields_none(self, monkeypatch) -> None:
        _spy_decide(monkeypatch, returns=None)

        entry = build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=["complete", "failed"],
            handoff_record=None,
            diff_stat="stat",
            test_output_tail=None,
        )

        assert entry is None

    def test_every_signal_absent_short_circuits_without_calling_decide(self, monkeypatch) -> None:
        decide = _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))

        entry = build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=[],
            handoff_record=None,
            diff_stat=None,
            test_output_tail=None,
        )

        assert entry is None
        decide.assert_not_called()

    def test_malformed_answers_return_none(self, monkeypatch) -> None:
        _spy_decide(monkeypatch, returns={"outcome": _choice_answer("complete")})  # missing evidence

        entry = build_outcome_adjudication_entry(
            phase="IMPLEMENT",
            claimed_outcome="complete",
            expected_outcomes=["complete", "failed"],
            handoff_record=None,
            diff_stat="stat",
            test_output_tail=None,
        )

        assert entry is None


# ---------------------------------------------------------------------------
# apply_phase_outcome wiring (D1) -- the real production insertion point
# ---------------------------------------------------------------------------


class TestApplyPhaseOutcomeWiring:
    def _seed_state(self, repo_root: Path, change_id: str, *, phase: str = "IMPLEMENT") -> Path:
        change_dir = repo_root / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 5,
            "change_id": change_id,
            "current_phase": phase,
            "phase_history": [],
            "handoff_ids": [],
            "last_handoff_id": None,
            "previous_phase": None,
            "phase_archetype": None,
        }
        (change_dir / "loop-state.json").write_text(json.dumps(state, indent=2))
        return change_dir

    def test_implement_outcome_gets_adjudicated(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))
        change_dir = self._seed_state(tmp_path, "po-1")

        phase_agent.apply_phase_outcome(
            change_id="po-1",
            phase="IMPLEMENT",
            outcome="complete",
            handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        entries = _shadow_entries(saved["phase_history"])
        assert len(entries) == 1
        assert entries[0]["acting_outcome"] == "complete"
        assert entries[0]["judged_outcome"] == "complete"

    def test_disagreement_does_not_change_claimed_outcome_or_transition(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The safety proof: the judge disagrees, but the recorded claimed
        outcome and a subsequent transition() call are unaffected."""
        monkeypatch.chdir(tmp_path)
        _spy_decide(monkeypatch, returns=_answers(outcome="failed", evidence=0.1))
        change_dir = self._seed_state(tmp_path, "po-2")

        phase_agent.apply_phase_outcome(
            change_id="po-2",
            phase="IMPLEMENT",
            outcome="complete",
            handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        bare_entry = next(e for e in saved["phase_history"] if e.get("outcome") == "complete")
        assert bare_entry["phase"] == "IMPLEMENT"

        state = LoopState(current_phase="IMPLEMENT")
        assert transition(state, "complete") == "IMPL_ITERATE"

    def test_replay_does_not_duplicate_entry_or_call_decide_twice(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        decide = _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))
        change_dir = self._seed_state(tmp_path, "po-3")

        phase_agent.apply_phase_outcome(
            change_id="po-3", phase="IMPLEMENT", outcome="complete", handoff_id="h1",
            change_dir=change_dir,
        )
        phase_agent.apply_phase_outcome(
            change_id="po-3", phase="IMPLEMENT", outcome="complete", handoff_id="h1",
            change_dir=change_dir, allow_phase_mismatch=True,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        assert len(_shadow_entries(saved["phase_history"])) == 1
        decide.assert_called_once()

    def test_gatekeeper_phase_is_not_double_shadowed(self, monkeypatch, tmp_path: Path) -> None:
        """GATEKEEPER keeps using its own ri-06 shadow path, not this one."""
        monkeypatch.chdir(tmp_path)
        _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))
        change_dir = self._seed_state(tmp_path, "po-4", phase="GATEKEEPER")

        phase_agent.apply_phase_outcome(
            change_id="po-4", phase="GATEKEEPER", outcome="proceed", handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        assert _shadow_entries(saved["phase_history"]) == []

    def test_no_change_dir_records_nothing(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        decide = _spy_decide(monkeypatch, returns=_answers(outcome="complete", evidence=0.9))
        change_dir = self._seed_state(tmp_path, "po-5")

        phase_agent.apply_phase_outcome(
            change_id="po-5", phase="IMPLEMENT", outcome="complete", handoff_id="h1",
        )  # change_dir omitted

        saved = json.loads((change_dir / "loop-state.json").read_text())
        assert _shadow_entries(saved["phase_history"]) == []
        decide.assert_not_called()

    def test_module_unavailable_records_nothing(self, monkeypatch, tmp_path: Path) -> None:
        import phase_agent as pa

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(pa, "phase_outcome_shadow", None)
        change_dir = self._seed_state(tmp_path, "po-6")

        pa.apply_phase_outcome(
            change_id="po-6", phase="IMPLEMENT", outcome="complete", handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        assert _shadow_entries(saved["phase_history"]) == []


# ---------------------------------------------------------------------------
# attribute_disagreements (D5) -- fixture only, real-sprint data deferred
# ---------------------------------------------------------------------------


class TestAttributeDisagreements:
    def test_attributes_each_side(self) -> None:
        entries = [
            {"acting_outcome": "complete", "judged_outcome": "failed"},  # disagreement
            {"acting_outcome": "complete", "judged_outcome": "complete"},  # agreement, skipped
            {"acting_outcome": "failed", "judged_outcome": "complete"},  # disagreement
        ]
        # index 0: review found the claim ("complete") wrong -> judged vindicated
        # index 2: review found the claim ("failed") correct -> claimed vindicated
        review_findings = {0: True, 2: False}

        result = attribute_disagreements(entries, review_findings)

        assert len(result) == 2
        assert result[0]["vindicated"] == "judged"
        assert result[1]["vindicated"] == "claimed"

    def test_unreviewed_disagreement_is_not_attributed(self) -> None:
        entries = [{"acting_outcome": "complete", "judged_outcome": "failed"}]

        result = attribute_disagreements(entries, review_findings={})

        assert result == []

    def test_agreements_are_never_attributed(self) -> None:
        entries = [{"acting_outcome": "complete", "judged_outcome": "complete"}]

        result = attribute_disagreements(entries, review_findings={0: True})

        assert result == []
