"""Injectable LLM-judge: skips with no backend, contributes with a fake backend."""

from __future__ import annotations

import json

from agent_scenarios import review_trajectory
from agent_scenarios.judge import TrajectoryJudgeBackend

_EVENTS = [
    {"role": "user", "content": [{"type": "text", "text": "fix add()"}]},
    {"role": "assistant", "content": [{"type": "tool_use", "tool_name": "Edit", "tool_input": {}}]},
]


class FakeBackend:
    """A scripted trajectory-judge backend (mirrors gen-eval's LLMBackend)."""

    def __init__(self, payload: dict, available: bool = True) -> None:
        self._payload = payload
        self._available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt: str, system: str | None = None) -> str:
        self.calls += 1
        return json.dumps(self._payload)


def test_skips_with_no_backend() -> None:
    verdict = review_trajectory(
        None, task_prompt="t", criteria="", transcript_events=_EVENTS, deterministic_status="pass"
    )
    assert verdict.status == "skip"
    assert "no judge backend" in verdict.reasoning


def test_skips_when_backend_unavailable() -> None:
    backend: TrajectoryJudgeBackend = FakeBackend({}, available=False)
    verdict = review_trajectory(
        backend,
        task_prompt="t",
        criteria="",
        transcript_events=_EVENTS,
        deterministic_status="pass",
    )
    assert verdict.status == "skip"


def test_contributes_pass_verdict() -> None:
    backend = FakeBackend({"pass": True, "confidence": 0.9, "reasoning": "clean", "findings": []})
    verdict = review_trajectory(
        backend,
        task_prompt="t",
        criteria="c",
        transcript_events=_EVENTS,
        deterministic_status="pass",
    )
    assert verdict.status == "pass"
    assert verdict.confidence == 0.9
    assert backend.calls == 1


def test_contributes_findings() -> None:
    backend = FakeBackend(
        {
            "pass": False,
            "confidence": 0.6,
            "reasoning": "wasteful",
            "findings": [
                {"kind": "inefficiency", "description": "re-read file 5x", "severity": "medium"},
                {"kind": "wrong_but_passed", "description": "hardcoded", "severity": "high"},
            ],
        }
    )
    verdict = review_trajectory(
        backend,
        task_prompt="t",
        criteria="c",
        transcript_events=_EVENTS,
        deterministic_status="pass",
    )
    assert verdict.status == "fail"
    kinds = {f.kind for f in verdict.findings}
    assert kinds == {"inefficiency", "wrong_but_passed"}


def test_malformed_backend_response_skips() -> None:
    backend = FakeBackend({})
    # Force a non-JSON response.
    backend.complete = lambda prompt, system=None: "not json"  # type: ignore[assignment]
    verdict = review_trajectory(
        backend,
        task_prompt="t",
        criteria="c",
        transcript_events=_EVENTS,
        deterministic_status="pass",
    )
    assert verdict.status == "skip"
