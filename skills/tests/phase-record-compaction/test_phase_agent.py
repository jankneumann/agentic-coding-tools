"""Tests for phase_agent.run_phase_subagent return contract (D6).

Asserts:
- run_phase_subagent returns exactly (outcome: str, handoff_id: str).
- The driver-visible result does not include the sub-agent transcript.
- The standard prompt scaffold (artifacts manifest, incoming PhaseRecord
  JSON, phase task instructions) is assembled and passed to the runner.
- isolation: "worktree" only for phase == "IMPLEMENT" (D7).

Spec reference: skill-workflow / Autopilot Phase Sub-Agent Isolation —
all scenarios.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from phase_agent import run_phase_subagent  # noqa: E402
from phase_record import PhaseRecord  # noqa: E402


def _incoming() -> PhaseRecord:
    return PhaseRecord(
        change_id="ch-1",
        phase_name="Plan",
        agent_type="autopilot",
        summary="Plan converged. 0 blocking findings.",
    )


class _CapturingRunner:
    """Stand-in subagent runner; records inputs and returns canned output."""

    def __init__(
        self,
        result: tuple[str, str] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result if result is not None else ("continue", "h-NEW")
        self._raise = raise_exc

    def __call__(
        self, *, prompt: str, options: dict[str, Any],
    ) -> tuple[str, str]:
        self.calls.append({"prompt": prompt, "options": options})
        if self._raise is not None:
            raise self._raise
        return self._result


class TestReturnContract:
    """run_phase_subagent surfaces exactly (outcome, handoff_id)."""

    def test_returns_tuple_of_strings(self) -> None:
        runner = _CapturingRunner(result=("continue", "h-42"))
        outcome, handoff_id = run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1", "iteration": 0},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert outcome == "continue"
        assert handoff_id == "h-42"

    def test_no_transcript_in_return(self) -> None:
        # The return is a 2-tuple, not a dict / not the runner output dict.
        runner = _CapturingRunner(result=("escalate", "h-X"))
        result = run_phase_subagent(
            phase="VALIDATE",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(x, str) for x in result)


class TestPromptScaffold:
    """The standard prompt is assembled from the three required pieces."""

    def test_prompt_includes_phase_name(self) -> None:
        runner = _CapturingRunner()
        run_phase_subagent(
            phase="IMPL_REVIEW",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        prompt = runner.calls[0]["prompt"]
        assert "IMPL_REVIEW" in prompt

    def test_prompt_includes_incoming_handoff_json(self) -> None:
        runner = _CapturingRunner()
        incoming = PhaseRecord(
            change_id="ch-1",
            phase_name="Plan",
            agent_type="autopilot",
            summary="Custom summary marker XYZ123.",
        )
        run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=incoming,
            subagent_runner=runner,
        )
        prompt = runner.calls[0]["prompt"]
        # The incoming PhaseRecord summary should appear verbatim in the prompt.
        assert "XYZ123" in prompt

    def test_prompt_includes_artifacts_manifest_when_provided(self) -> None:
        runner = _CapturingRunner()
        manifest = ["openspec/changes/ch-1/proposal.md", "openspec/changes/ch-1/tasks.md"]
        run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
            artifacts_manifest=manifest,
        )
        prompt = runner.calls[0]["prompt"]
        for path in manifest:
            assert path in prompt


class TestWorktreeIsolation:
    """isolation: worktree only for IMPLEMENT (D7)."""

    def test_implement_uses_worktree_isolation(self) -> None:
        runner = _CapturingRunner()
        run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        opts = runner.calls[0]["options"]
        assert opts.get("isolation") == "worktree"

    def test_impl_review_runs_in_shared_checkout(self) -> None:
        runner = _CapturingRunner()
        run_phase_subagent(
            phase="IMPL_REVIEW",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        opts = runner.calls[0]["options"]
        # IMPL_REVIEW is read-mostly; no worktree isolation
        assert opts.get("isolation") != "worktree"

    def test_validate_runs_in_shared_checkout(self) -> None:
        runner = _CapturingRunner()
        run_phase_subagent(
            phase="VALIDATE",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
        )
        opts = runner.calls[0]["options"]
        assert opts.get("isolation") != "worktree"
