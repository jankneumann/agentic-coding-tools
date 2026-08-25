"""Tests for Layer 2 LoopState opacity (D6).

Asserts that after a Layer-2 phase callback (built via make_phase_callback)
returns, the driver-visible LoopState delta is bounded:
- last_handoff_id is updated to the new handoff_id.
- handoff_ids gains exactly one new entry (the new handoff_id).
- No sub-agent transcript or intermediate state leaks into LoopState.

Spec reference: skill-workflow / Autopilot Phase Sub-Agent Isolation —
Sub-agent return surfaces only outcome and handoff_id.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

import phase_agent  # noqa: E402
from phase_agent import make_phase_callback  # noqa: E402
from phase_record import PhaseRecord  # noqa: E402

from autopilot import LoopState  # noqa: E402


def _runner_returning(handoff_id: str = "h-NEW") -> Any:
    """Runner that returns a fixed (outcome, handoff_id) and a verbose
    'transcript' that should NOT escape into LoopState."""

    def runner(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        # The runner internally would have a long sub-agent transcript;
        # but the driver only sees the (outcome, handoff_id) tuple.
        return "continue", handoff_id

    return runner


@pytest.fixture
def state() -> LoopState:
    return LoopState(
        change_id="opacity-test",
        current_phase="IMPLEMENT",
        iteration=1,
        total_iterations=3,
        findings_trend=[5, 2],
        handoff_ids=["h-PRIOR-1", "h-PRIOR-2"],
        last_handoff_id="h-PRIOR-2",
    )


class TestBoundedStateDelta:
    """The driver state delta after callback return is bounded."""

    @staticmethod
    def _pin_archetype(
        monkeypatch: pytest.MonkeyPatch, resolved: dict[str, Any] | None,
    ) -> None:
        """Pin the coordinator archetype lookup.

        `_build_options` reaches a live coordinator through
        `coordination_bridge.try_resolve_archetype_for_phase`. Left unpinned,
        the delta these tests assert depends on the environment rather than on
        the code: resolution succeeds on a developer machine with a
        coordinator configured and writes `phase_archetype`, and fails with
        ECONNREFUSED on a CI runner and does not. `phase_agent` imports the
        bridge as a module specifically so this call can be patched, so pin it
        and cover both branches explicitly.
        """
        monkeypatch.setattr(
            phase_agent.coordination_bridge,
            "try_resolve_archetype_for_phase",
            lambda *args, **kwargs: resolved,
        )

    def test_delta_is_only_last_handoff_id_and_one_new_id(
        self, state: LoopState, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._pin_archetype(monkeypatch, None)

        before = asdict(deepcopy(state))
        callback = make_phase_callback(
            phase="IMPLEMENT",
            subagent_runner=_runner_returning("h-NEW"),
        )
        outcome = callback(state)
        after = asdict(state)

        assert outcome == "continue"

        # The point of this assertion is that it is an equality, not a subset:
        # the callback may write these fields and no others, so a phase that
        # starts splatting sub-agent state into LoopState fails here.
        diff_keys = {k for k in before if before[k] != after[k]}
        assert diff_keys == {"last_handoff_id", "handoff_ids"}

        # last_handoff_id is the new id
        assert after["last_handoff_id"] == "h-NEW"
        # handoff_ids gained exactly one entry, at the end
        assert after["handoff_ids"] == before["handoff_ids"] + ["h-NEW"]

    def test_resolved_archetype_widens_the_delta_by_exactly_one_field(
        self, state: LoopState, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful archetype resolution adds `phase_archetype` and
        nothing else.

        `phase_archetype` joined the writable set in `a4eca530
        feat(autopilot): per-phase archetype resolution + LoopState v3` --
        `_build_options` records the resolved name in
        `state_dict["_resolved_archetype"]` and the callback propagates it.
        That is a deliberate, bounded addition; this asserts it stays bounded
        instead of becoming general-purpose scratch space.
        """
        self._pin_archetype(
            monkeypatch,
            {
                "archetype": "implementer-heavy",
                "model": "test-model",
                "system_prompt": "test-prompt",
            },
        )

        before = asdict(deepcopy(state))
        callback = make_phase_callback(
            phase="IMPLEMENT",
            subagent_runner=_runner_returning("h-NEW"),
        )
        outcome = callback(state)
        after = asdict(state)

        assert outcome == "continue"
        diff_keys = {k for k in before if before[k] != after[k]}
        assert diff_keys == {"last_handoff_id", "handoff_ids", "phase_archetype"}
        assert after["phase_archetype"] == "implementer-heavy"

    def test_no_transcript_field_appears(self, state: LoopState) -> None:
        """LoopState should not gain a transcript-like field after the call."""
        forbidden_keys = {
            "transcript", "messages", "tool_uses", "subagent_log",
            "intermediate_state", "raw_response",
        }
        callback = make_phase_callback(
            phase="VALIDATE",
            subagent_runner=_runner_returning("h-V"),
        )
        callback(state)
        state_keys = set(asdict(state).keys())
        leaked = forbidden_keys & state_keys
        assert not leaked, f"transcript-like keys leaked into LoopState: {leaked}"

    def test_findings_trend_unchanged(self, state: LoopState) -> None:
        """Sub-agent does not mutate findings_trend through the callback."""
        before = list(state.findings_trend)
        callback = make_phase_callback(
            phase="IMPL_REVIEW",
            subagent_runner=_runner_returning("h-R"),
        )
        callback(state)
        assert state.findings_trend == before


class TestIncomingHandoffLoader:
    """The incoming handoff loader is called with state.last_handoff_id."""

    def test_loader_receives_last_handoff_id(self, state: LoopState) -> None:
        captured: list[str | None] = []

        def loader(handoff_id: str | None) -> PhaseRecord:
            captured.append(handoff_id)
            return PhaseRecord(
                change_id="opacity-test",
                phase_name="prev",
                agent_type="autopilot",
                summary="loaded from coordinator",
            )

        callback = make_phase_callback(
            phase="IMPLEMENT",
            subagent_runner=_runner_returning("h-X"),
            incoming_handoff_loader=loader,
        )
        callback(state)
        assert captured == ["h-PRIOR-2"]

    def test_loader_called_even_when_no_prior_handoff(self) -> None:
        empty_state = LoopState(change_id="fresh")
        captured: list[str | None] = []

        def loader(handoff_id: str | None) -> PhaseRecord:
            captured.append(handoff_id)
            return PhaseRecord(
                change_id="fresh",
                phase_name="bootstrap",
                agent_type="autopilot",
                summary="empty",
            )

        callback = make_phase_callback(
            phase="IMPLEMENT",
            subagent_runner=_runner_returning("h-FIRST"),
            incoming_handoff_loader=loader,
        )
        callback(empty_state)
        assert captured == [None]
        assert empty_state.last_handoff_id == "h-FIRST"


class TestOutcomeOnly:
    """Callback returns only the outcome string to the driver."""

    def test_callback_return_type_is_str(self, state: LoopState) -> None:
        callback = make_phase_callback(
            phase="IMPLEMENT",
            subagent_runner=_runner_returning("h-Y"),
        )
        result = callback(state)
        assert isinstance(result, str)

    def test_callback_returns_runner_outcome_verbatim(
        self, state: LoopState,
    ) -> None:
        def runner(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
            return "escalate", "h-Z"

        callback = make_phase_callback(
            phase="VALIDATE",
            subagent_runner=runner,
        )
        assert callback(state) == "escalate"
        assert state.last_handoff_id == "h-Z"
