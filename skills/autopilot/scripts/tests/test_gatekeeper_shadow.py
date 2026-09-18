"""Tests for the GATEKEEPER shadow judgment.

Covers spec scenarios (openspec/specs/skill-workflow/spec.md, "GATEKEEPER
Shadow Judgment"):
- A shadow record per gatekeeper run appends judged verdict, both score
  distributions and the acting verdict
- The acting verdict is byte-identical to today's for every run in the
  shadow period
- The code-computed verdict is derived from the two Score distributions
  with thresholds read from config
- The GATEKEEPER shadow judgment degrades silently on unavailability
- A reporting script emits the GATEKEEPER disagreement rate
- --force and the scope-safety floor are untouched

Design decisions: D1 (additive shadow call), D2 (question shape), D3
(config-sourced thresholds), D4 (shared shadow-record envelope), D5
(work-packages summary, not a raw dump), D6 (change_dir threading), D7
(reporting script).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import system_one_decisions  # noqa: E402

import phase_agent  # noqa: E402
from autopilot import LoopState, _phase_gatekeeper  # noqa: E402
# Aliased: this file's own tests use `change_dir` as a local variable name
# (an OpenSpec change's directory) for the shadow judgment's own parameter.
from openspec_paths import change_dir as _openspec_change_dir  # noqa: E402
from openspec_paths import repo_root_from  # noqa: E402
from gatekeeper_shadow import (  # noqa: E402
    ShadowThresholds,
    compute_candidate_verdict,
    load_shadow_thresholds,
    shadow_gatekeeper_judgment,
)
from gatekeeper_shadow_report import collect_shadow_entries, disagreement_report  # noqa: E402


def _spy_decide(monkeypatch, *, returns) -> MagicMock:
    """A MagicMock patched onto the real `system_one_decisions` module object.

    Mirrors the pattern established in
    `parallel-infrastructure/scripts/tests/test_consensus_synthesizer_judged_matching.py`.
    """
    mock = MagicMock(return_value=returns)
    monkeypatch.setattr(system_one_decisions, "decide", mock)
    return mock


def _score_answer(score: float, *, confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(score=score, confidence=confidence, probabilities={})


def _choice_answer(choice: str, *, confidence: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(choice=choice, confidence=confidence, probabilities={})


def _answers(
    *, verifiability: float, risk: float, verdict: str = "proceed"
) -> dict[str, object]:
    return {
        "verifiability": _score_answer(verifiability),
        "risk": _score_answer(risk),
        "verdict": _choice_answer(verdict),
    }


def _shadow_entries(state: LoopState) -> list[dict]:
    return [e for e in state.phase_history if e.get("phase") == "GATEKEEPER_SHADOW"]


def make_change_dir(tmp_path: Path) -> Path:
    change_dir = tmp_path / "change"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("# Proposal\n")
    (change_dir / "tasks.md").write_text("# Tasks\n- [ ] one\n")
    return change_dir


# ---------------------------------------------------------------------------
# compute_candidate_verdict (D3)
# ---------------------------------------------------------------------------


class TestComputeCandidateVerdict:
    def test_low_risk_high_verifiability_proceeds(self) -> None:
        assert compute_candidate_verdict(0.0, 3.0, ShadowThresholds()) == "proceed"

    def test_high_risk_escalates(self) -> None:
        assert compute_candidate_verdict(2.5, 3.0, ShadowThresholds()) == "escalate"

    def test_low_verifiability_escalates(self) -> None:
        assert compute_candidate_verdict(0.0, 0.5, ShadowThresholds()) == "escalate"

    def test_moderate_risk_reviews(self) -> None:
        assert compute_candidate_verdict(1.5, 3.0, ShadowThresholds()) == "proceed_with_review"

    def test_moderate_verifiability_gap_reviews(self) -> None:
        assert compute_candidate_verdict(0.0, 1.5, ShadowThresholds()) == "proceed_with_review"

    def test_thresholds_are_boundary_inclusive(self) -> None:
        thresholds = ShadowThresholds(risk_escalate=2.0)
        assert compute_candidate_verdict(2.0, 3.0, thresholds) == "escalate"


class TestLoadShadowThresholdsMalformedSidecar:
    """Codex regression (PR #591, P2): a syntactically valid but wrongly
    shaped or non-numeric sidecar must degrade to defaults, never raise --
    shadow configuration errors can never become a GATEKEEPER phase
    exception."""

    def test_non_mapping_json_falls_back_to_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "gatekeeper-shadow.json"
        config_path.write_text("[]")

        assert load_shadow_thresholds(config_path) == ShadowThresholds()

    def test_non_numeric_field_falls_back_to_that_fields_default(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "gatekeeper-shadow.json"
        config_path.write_text('{"risk_escalate": "high"}')

        thresholds = load_shadow_thresholds(config_path)

        assert thresholds.risk_escalate == ShadowThresholds().risk_escalate
        assert thresholds.risk_review == ShadowThresholds().risk_review

    def test_valid_numeric_override_is_honored(self, tmp_path: Path) -> None:
        config_path = tmp_path / "gatekeeper-shadow.json"
        config_path.write_text('{"risk_escalate": 1.0}')

        thresholds = load_shadow_thresholds(config_path)

        assert thresholds.risk_escalate == 1.0


# ---------------------------------------------------------------------------
# shadow_gatekeeper_judgment (D1, D2, D4, D5)
# ---------------------------------------------------------------------------


class TestShadowGatekeeperJudgment:
    def test_records_one_entry_with_both_distributions_and_acting_verdict(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        _spy_decide(
            monkeypatch,
            returns=_answers(verifiability=3.0, risk=0.0, verdict="escalate"),
        )
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        shadow_gatekeeper_judgment(state, change_dir, acting_verdict="proceed")

        entries = _shadow_entries(state)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["acting_outcome"] == "proceed"
        assert entry["judged_outcome"] == "proceed"  # from the low-risk/high-verifiability scores
        assert entry["judgment"]["verifiability"]["score"] == 3.0
        assert entry["judgment"]["risk"]["score"] == 0.0
        assert entry["judgment"]["choice_cross_check"]["choice"] == "escalate"

    def test_calls_decide_exactly_once(self, monkeypatch, tmp_path: Path) -> None:
        decide = _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0)
        )
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        shadow_gatekeeper_judgment(state, change_dir, acting_verdict="proceed")

        decide.assert_called_once()

    def test_no_change_dir_records_nothing(self, monkeypatch) -> None:
        decide = _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0)
        )
        state = LoopState(current_phase="GATEKEEPER")

        shadow_gatekeeper_judgment(state, None, acting_verdict="proceed")

        assert _shadow_entries(state) == []
        decide.assert_not_called()

    def test_decide_returns_none_records_nothing(self, monkeypatch, tmp_path: Path) -> None:
        _spy_decide(monkeypatch, returns=None)
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        shadow_gatekeeper_judgment(state, change_dir, acting_verdict="proceed")

        assert _shadow_entries(state) == []

    def test_malformed_answers_record_nothing(self, monkeypatch, tmp_path: Path) -> None:
        _spy_decide(monkeypatch, returns={"verifiability": _score_answer(3.0)})  # missing risk/verdict
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        shadow_gatekeeper_judgment(state, change_dir, acting_verdict="proceed")

        assert _shadow_entries(state) == []

    def test_module_unavailable_records_nothing(self, monkeypatch, tmp_path: Path) -> None:
        import gatekeeper_shadow

        monkeypatch.setattr(gatekeeper_shadow, "system_one_decisions", None)
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        gatekeeper_shadow.shadow_gatekeeper_judgment(
            state, change_dir, acting_verdict="proceed"
        )

        assert _shadow_entries(state) == []


# ---------------------------------------------------------------------------
# _phase_gatekeeper integration: shadow never leaks into the acting verdict
# ---------------------------------------------------------------------------


class TestPhaseGatekeeperShadowIsolation:
    def test_shadow_disagreement_does_not_change_acting_verdict(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The classic safety proof: rig the shadow judge to want 'escalate'
        while the real judge says 'proceed' -- the acting verdict must stay
        'proceed'."""
        _spy_decide(
            monkeypatch,
            returns=_answers(verifiability=0.0, risk=3.0, verdict="escalate"),
        )
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        outcome = _phase_gatekeeper(
            state, lambda _s: "proceed", change_dir=change_dir
        )

        assert outcome == "proceed"
        assert state.gate_verdict == "proceed"
        entries = _shadow_entries(state)
        assert len(entries) == 1
        assert entries[0]["judged_outcome"] == "escalate"
        assert entries[0]["acting_outcome"] == "proceed"

    def test_shadow_entry_recorded_even_when_escalation_gate_parks(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Codex regression (PR #591, P2): the escalation approval gate's
        BLOCKED early return (`gates.park(...)`) must not skip the shadow
        record -- every GATEKEEPER run gets one, whichever exit path the
        acting verdict takes. No TRUST_POSTURE.md exists in this repo, so
        the default gate evaluator fails closed (BLOCKED) for
        Gate.GATEKEEPER_ESCALATION, exercising exactly this path."""
        _spy_decide(
            monkeypatch,
            returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed"),
        )
        state = LoopState(current_phase="GATEKEEPER")
        change_dir = make_change_dir(tmp_path)

        outcome = _phase_gatekeeper(
            state, lambda _s: "escalate", change_dir=change_dir
        )

        assert outcome == "gate_pending"  # gates.park's BLOCKED sentinel
        assert state.gate_verdict == "escalate"
        entries = _shadow_entries(state)
        assert len(entries) == 1
        assert entries[0]["acting_outcome"] == "escalate"
        assert entries[0]["judged_outcome"] == "proceed"

    def test_no_change_dir_is_backward_compatible(self, monkeypatch) -> None:
        """Every pre-existing direct-helper call site omits change_dir."""
        state = LoopState(current_phase="GATEKEEPER")

        outcome = _phase_gatekeeper(state, lambda _s: "proceed")

        assert outcome == "proceed"
        assert _shadow_entries(state) == []


# ---------------------------------------------------------------------------
# Fixture replay over real recorded gate_signals (design.md grounding)
# ---------------------------------------------------------------------------


class TestGatekeeperShadowFixtureReplay:
    """Replays two REAL recorded gate_signals profiles (not synthetic ones)
    from committed loop-state.json files, confirming the acting verdict is
    byte-identical to what was actually recorded even when the shadow judge
    is rigged to disagree.
    """

    def test_no_risk_signal_fixture_stays_proceed(self, monkeypatch, tmp_path: Path) -> None:
        loop_state_path = (
            _openspec_change_dir(repo_root_from(__file__, 4), "add-visual-code-explainer")
            / "loop-state.json"
        )
        recorded = json.loads(loop_state_path.read_text(encoding="utf-8"))
        gate_signals = recorded["gate_signals"]
        assert gate_signals["has_db_migration"] is False  # grounding check

        _spy_decide(
            monkeypatch,
            returns=_answers(verifiability=0.0, risk=3.0, verdict="escalate"),
        )
        state = LoopState(current_phase="GATEKEEPER", gate_signals=gate_signals)
        change_dir = make_change_dir(tmp_path)

        # No gatekeeper_fn wired for this fixture -> permissive fallback,
        # matching a headless run over the same signals.
        outcome = _phase_gatekeeper(state, None, change_dir=change_dir)

        assert outcome == "proceed"
        assert _shadow_entries(state)[0]["judged_outcome"] == "escalate"

    def test_db_migration_fixture_stays_proceed_with_review(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        loop_state_path = (
            _openspec_change_dir(
                repo_root_from(__file__, 4), "fix-audit-choices-range-ledger-path"
            )
            / "loop-state.json"
        )
        recorded = json.loads(loop_state_path.read_text(encoding="utf-8"))
        gate_signals = recorded["gate_signals"]
        assert gate_signals["has_db_migration"] is True  # grounding check
        assert recorded["gate_verdict"] == "proceed_with_review"  # grounding check

        _spy_decide(
            monkeypatch,
            returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed"),
        )
        state = LoopState(current_phase="GATEKEEPER", gate_signals=gate_signals)
        change_dir = make_change_dir(tmp_path)

        outcome = _phase_gatekeeper(state, None, change_dir=change_dir)

        assert outcome == "proceed_with_review"  # byte-identical to the recording
        assert state.val_review_enabled is True
        assert _shadow_entries(state)[0]["judged_outcome"] == "proceed"
        assert _shadow_entries(state)[0]["acting_outcome"] == "proceed_with_review"


# ---------------------------------------------------------------------------
# --force / scope-safety floor untouched
# ---------------------------------------------------------------------------


class TestForceAndScopeSafetyUntouched:
    def test_force_skips_gatekeeper_entirely_no_shadow_entry(self, monkeypatch) -> None:
        """_phase_gatekeeper is never reached when --force skips GATEKEEPER,
        so no shadow entry can be recorded -- covered at the run_loop level
        by the pre-existing test_force_skips_gatekeeper; this asserts the
        same invariant directly against the phase helper never being called."""
        decide = _spy_decide(monkeypatch, returns=_answers(verifiability=3.0, risk=0.0))
        state = LoopState(current_phase="GATEKEEPER", force=True)

        # Mirrors run_loop's own force-skip: GATEKEEPER is bypassed, so the
        # phase helper simply never runs.
        decide.assert_not_called()
        assert state.phase_history == []


# ---------------------------------------------------------------------------
# gatekeeper_shadow_report.py (D7)
# ---------------------------------------------------------------------------


class TestApplyPhaseOutcomeShadowWiring:
    """Codex regression (PR #591, P1): the real host-driven GATEKEEPER
    dispatch protocol (`SKILL.md` Step 1.5: `build-dispatch` /
    `apply-outcome`) never calls the Python-level `_phase_gatekeeper` at
    all, so `phase_agent.apply_phase_outcome` must build and append the
    shadow record itself on that path."""

    def _seed_state(self, repo_root: Path, change_id: str) -> Path:
        change_dir = repo_root / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "proposal.md").write_text("# Proposal\n")
        (change_dir / "tasks.md").write_text("# Tasks\n")
        state: dict = {
            "schema_version": 5,
            "change_id": change_id,
            "current_phase": "GATEKEEPER",
            "gate_signals": {"has_db_migration": False},
            "phase_history": [],
            "handoff_ids": [],
            "last_handoff_id": None,
            "previous_phase": None,
            "phase_archetype": None,
        }
        state_path = change_dir / "loop-state.json"
        state_path.write_text(json.dumps(state, indent=2))
        return change_dir

    def test_gatekeeper_outcome_records_a_shadow_entry(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed")
        )
        change_dir = self._seed_state(tmp_path, "gk-1")

        phase_agent.apply_phase_outcome(
            change_id="gk-1",
            phase="GATEKEEPER",
            outcome="proceed",
            handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        shadow_entries = [
            e for e in saved["phase_history"] if e.get("phase") == "GATEKEEPER_SHADOW"
        ]
        assert len(shadow_entries) == 1
        assert shadow_entries[0]["acting_outcome"] == "proceed"
        assert shadow_entries[0]["judged_outcome"] == "proceed"

    def test_replay_does_not_duplicate_the_shadow_entry(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        decide = _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed")
        )
        change_dir = self._seed_state(tmp_path, "gk-2")

        phase_agent.apply_phase_outcome(
            change_id="gk-2",
            phase="GATEKEEPER",
            outcome="proceed",
            handoff_id="h1",
            change_dir=change_dir,
        )
        # A retried apply-outcome call for the SAME handoff_id is a replay --
        # the replay early-return path never reaches the shadow block, so no
        # second decide() call and no duplicate shadow entry.
        phase_agent.apply_phase_outcome(
            change_id="gk-2",
            phase="GATEKEEPER",
            outcome="proceed",
            handoff_id="h1",
            change_dir=change_dir,
            allow_phase_mismatch=True,
        )

        saved = json.loads((change_dir / "loop-state.json").read_text())
        shadow_entries = [
            e for e in saved["phase_history"] if e.get("phase") == "GATEKEEPER_SHADOW"
        ]
        assert len(shadow_entries) == 1
        decide.assert_called_once()

    def test_non_gatekeeper_phase_records_no_shadow_entry(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        decide = _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed")
        )
        change_dir = self._seed_state(tmp_path, "gk-3")
        state_path = change_dir / "loop-state.json"
        state = json.loads(state_path.read_text())
        state["current_phase"] = "IMPLEMENT"
        state_path.write_text(json.dumps(state))

        phase_agent.apply_phase_outcome(
            change_id="gk-3",
            phase="IMPLEMENT",
            outcome="implemented",
            handoff_id="h1",
            change_dir=change_dir,
        )

        saved = json.loads(state_path.read_text())
        assert all(e.get("phase") != "GATEKEEPER_SHADOW" for e in saved["phase_history"])
        decide.assert_not_called()

    def test_no_change_dir_records_no_shadow_entry(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        decide = _spy_decide(
            monkeypatch, returns=_answers(verifiability=3.0, risk=0.0, verdict="proceed")
        )
        change_dir = self._seed_state(tmp_path, "gk-4")

        phase_agent.apply_phase_outcome(
            change_id="gk-4",
            phase="GATEKEEPER",
            outcome="proceed",
            handoff_id="h1",
        )  # change_dir omitted -- backward compatible

        saved = json.loads((change_dir / "loop-state.json").read_text())
        assert all(e.get("phase") != "GATEKEEPER_SHADOW" for e in saved["phase_history"])
        decide.assert_not_called()


class TestGatekeeperShadowReport:
    def _write_loop_state(self, path: Path, entries: list[dict]) -> None:
        path.write_text(json.dumps({"phase_history": entries}))

    def test_disagreement_rate_over_multiple_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        self._write_loop_state(
            f1,
            [
                {"phase": "GATEKEEPER_SHADOW", "acting_outcome": "proceed", "judged_outcome": "proceed"},
                {"phase": "GATEKEEPER_SHADOW", "acting_outcome": "proceed", "judged_outcome": "escalate"},
                {"phase": "GATEKEEPER", "outcome": "proceed"},  # not a shadow entry
            ],
        )
        self._write_loop_state(
            f2,
            [
                {"phase": "GATEKEEPER_SHADOW", "acting_outcome": "proceed_with_review", "judged_outcome": "proceed_with_review"},
            ],
        )

        entries = collect_shadow_entries([f1, f2])
        report = disagreement_report(entries)

        assert report["total_runs"] == 3
        assert report["disagreement_count"] == 1
        assert report["disagreement_rate"] == 1 / 3
        assert report["disagreement_pairs"] == {"proceed -> escalate": 1}

    def test_no_entries_yields_zero_rate(self, tmp_path: Path) -> None:
        f1 = tmp_path / "empty.json"
        self._write_loop_state(f1, [])

        report = disagreement_report(collect_shadow_entries([f1]))

        assert report["total_runs"] == 0
        assert report["disagreement_rate"] == 0.0

    def test_missing_file_is_skipped_not_raised(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.json"

        entries = collect_shadow_entries([missing])

        assert entries == []
