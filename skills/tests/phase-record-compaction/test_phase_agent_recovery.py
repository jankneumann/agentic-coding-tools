"""Tests for phase_agent crash recovery (D8).

Three scenarios per the spec:
1. First-attempt success — runner returns valid result on attempt 1.
2. Malformed-output retry — first call returns garbage; second returns
   a valid (outcome, handoff_id); driver gets the second result.
3. Escalation after 3 failures — runner raises every time; driver writes
   a phase-failed PhaseRecord and raises PhaseEscalationError.

Spec reference: skill-workflow / Phase Sub-Agent Crash Recovery — all three.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from phase_agent import (  # noqa: E402
    PhaseEscalationError,
    run_phase_subagent,
)
from phase_record import PhaseRecord  # noqa: E402


def _incoming() -> PhaseRecord:
    return PhaseRecord(
        change_id="ch-1",
        phase_name="Plan",
        agent_type="autopilot",
        summary="Plan converged.",
    )


class _ScriptedRunner:
    """Returns a scripted sequence of results / raises."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        self.calls.append({"prompt": prompt, "options": options})
        if not self.script:
            raise RuntimeError("ScriptedRunner exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestFirstAttemptSuccess:
    def test_single_call_returns_runner_result(self, workdir: Path) -> None:
        runner = _ScriptedRunner([("continue", "h-1")])
        outcome, handoff_id = run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert outcome == "continue"
        assert handoff_id == "h-1"
        assert len(runner.calls) == 1


class TestMalformedRetry:
    def test_garbage_then_valid_returns_second(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            ("not a tuple of len 2",),       # malformed: tuple of length 1
            ("continue", "h-2"),              # valid second attempt
        ])
        outcome, handoff_id = run_phase_subagent(
            phase="IMPL_REVIEW",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert (outcome, handoff_id) == ("continue", "h-2")
        assert len(runner.calls) == 2

    def test_empty_handoff_id_retries(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            ("continue", ""),                 # malformed: empty handoff_id
            ("continue", "h-3"),              # valid
        ])
        outcome, handoff_id = run_phase_subagent(
            phase="VALIDATE",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert handoff_id == "h-3"
        assert len(runner.calls) == 2

    def test_runner_exception_then_valid(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            RuntimeError("transient network glitch"),
            ("continue", "h-4"),
        ])
        outcome, handoff_id = run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert (outcome, handoff_id) == ("continue", "h-4")
        assert len(runner.calls) == 2


class TestEscalationAfterMaxAttempts:
    def test_three_failures_raise_PhaseEscalationError(
        self, workdir: Path,
    ) -> None:
        runner = _ScriptedRunner([
            RuntimeError("attempt 1 failed"),
            RuntimeError("attempt 2 failed"),
            RuntimeError("attempt 3 failed"),
        ])
        with pytest.raises(PhaseEscalationError) as excinfo:
            run_phase_subagent(
                phase="IMPLEMENT",
                state_dict={"change_id": "ch-1"},
                incoming_handoff=_incoming(),
                subagent_runner=runner,
            )
        assert excinfo.value.phase == "IMPLEMENT"
        assert excinfo.value.attempts == 3
        assert "attempt 3 failed" in excinfo.value.last_error
        assert len(runner.calls) == 3

    def test_three_malformed_results_raise(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            "not a tuple",
            ("only one",),
            ("", "h-id"),                       # empty outcome
        ])
        with pytest.raises(PhaseEscalationError):
            run_phase_subagent(
                phase="VALIDATE",
                state_dict={"change_id": "ch-1"},
                incoming_handoff=_incoming(),
                subagent_runner=runner,
                max_attempts=3,
            )

    def test_escalation_writes_phase_failed_record(
        self, workdir: Path,
    ) -> None:
        """The driver writes a phase-failed PhaseRecord before raising
        so the operator has a structured account of the failure."""
        captured: list[dict[str, Any]] = []

        def coord_writer(**kwargs: Any) -> dict[str, Any]:
            captured.append(kwargs)
            return {"handoff_id": "h-failed"}

        runner = _ScriptedRunner([
            RuntimeError("e1"),
            RuntimeError("e2"),
            RuntimeError("e3"),
        ])
        with pytest.raises(PhaseEscalationError):
            run_phase_subagent(
                phase="IMPLEMENT",
                state_dict={"change_id": "ch-1"},
                incoming_handoff=_incoming(),
                subagent_runner=runner,
                coordinator_writer=coord_writer,
            )

        # Coordinator writer was called once with a phase-failed record
        assert len(captured) == 1
        call = captured[0]
        assert call["agent_id"] == "autopilot"
        assert "failed" in call["summary"].lower()
        # The phase-failed record's content (handoff payload) should
        # mention the failed phase
        payload = call["content"]
        assert payload["agent_name"] == "autopilot"

    def test_custom_max_attempts_respected(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            RuntimeError("e1"),
            RuntimeError("e2"),
        ])
        with pytest.raises(PhaseEscalationError) as excinfo:
            run_phase_subagent(
                phase="IMPLEMENT",
                state_dict={"change_id": "ch-1"},
                incoming_handoff=_incoming(),
                subagent_runner=runner,
                max_attempts=2,
            )
        assert excinfo.value.attempts == 2
        assert len(runner.calls) == 2


class TestSameIncomingHandoffOnRetry:
    """Each retry passes the SAME incoming handoff (D8)."""

    def test_prompt_unchanged_across_retries(self, workdir: Path) -> None:
        runner = _ScriptedRunner([
            RuntimeError("e1"),
            ("continue", "h-final"),
        ])
        run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert len(runner.calls) == 2
        # Both calls received the identical prompt
        assert runner.calls[0]["prompt"] == runner.calls[1]["prompt"]
