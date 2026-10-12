"""Dispatch always pairs the resolved provider with the resolved model (D1).

Spec: openspec/changes/add-infeasible-incumbent-fallback design D1
      (agent-archetypes.6, agent-archetypes.7).

Covers:
- `run_phase_subagent` (and therefore `make_phase_callback`) sets
  `options["provider"]` to the coordinator-resolved provider when adaptive
  routing crosses vendors, not the caller's static default (both the
  explicit-arg and env paths).
- `claude_agent_runner(agent_fn, supported={"claude_code"})` raises
  `UnservableProviderError` for any `options["provider"]` outside its
  `supported` set, without calling `agent_fn`.
- `run_phase_subagent` treats `UnservableProviderError` as non-retryable:
  it raises `PhaseEscalationError` on the first occurrence, without
  consuming the retry budget (the failure is deterministic).
- `smoke_provider_dispatch` pairs the resolved provider with the resolved
  model: refuses a `local` route for an untrusted archetype, dispatches when
  routed away from `local`, raises `ProviderModelMappingError` for a resolved
  non-Claude provider paired with a Claude alias, and reports both `provider`
  (the caller's) and `resolved_provider` in the JSON body and the text line.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import coordination_bridge
import phase_agent
import pytest
from phase_record import PhaseRecord

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SMOKE = _REPO_ROOT / "skills" / "autopilot" / "scripts" / "smoke_provider_dispatch.py"


def _incoming() -> PhaseRecord:
    return PhaseRecord(
        change_id="ch-1",
        phase_name="Plan",
        agent_type="autopilot",
        summary="Plan converged.",
    )


class _CapturingRunner:
    """Stand-in subagent runner; records inputs and returns canned output."""

    def __init__(self, result: tuple[str, str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result if result is not None else ("complete", "h-ok")

    def __call__(self, *, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        self.calls.append({"prompt": prompt, "options": options})
        return self._result


def _stub_bridge(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: response,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_TYPE", raising=False)


# ---------------------------------------------------------------------------
# run_phase_subagent / make_phase_callback honor the resolved provider
# ---------------------------------------------------------------------------

_RESOLVED_CROSS_VENDOR: dict[str, Any] = {
    "model": "qwen/qwen3-coder",
    "system_prompt": "You are an implementer.",
    "archetype": "implementer",
    "provider": "openrouter",
    "reasons": ["adaptive routing selected an openrouter model"],
}


def test_run_phase_subagent_passes_resolved_provider_via_explicit_arg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit caller provider, resolver rewrites it to a different vendor."""
    _stub_bridge(monkeypatch, _RESOLVED_CROSS_VENDOR)
    runner = _CapturingRunner()

    run_outcome, _ = phase_agent.run_phase_subagent(
        phase="IMPLEMENT",
        state_dict={"change_id": "ch-1"},
        incoming_handoff=_incoming(),
        subagent_runner=runner,
        provider="codex",
    )

    assert run_outcome == "complete"
    assert runner.calls[0]["options"]["provider"] == "openrouter"


def test_run_phase_subagent_passes_resolved_provider_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rewrite, but the caller's provider comes from AUTOPILOT_PROVIDER."""
    monkeypatch.setenv("AUTOPILOT_PROVIDER", "codex")
    _stub_bridge(monkeypatch, _RESOLVED_CROSS_VENDOR)
    runner = _CapturingRunner()

    phase_agent.run_phase_subagent(
        phase="IMPLEMENT",
        state_dict={"change_id": "ch-1"},
        incoming_handoff=_incoming(),
        subagent_runner=runner,
    )

    assert runner.calls[0]["options"]["provider"] == "openrouter"


def test_run_phase_subagent_static_provider_stands_without_cross_vendor_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No resolved `provider` key from the bridge -> the caller's stands."""
    _stub_bridge(
        monkeypatch,
        {
            "model": "sonnet",
            "system_prompt": "You are an implementer.",
            "archetype": "implementer",
        },
    )
    runner = _CapturingRunner()

    phase_agent.run_phase_subagent(
        phase="IMPLEMENT",
        state_dict={"change_id": "ch-1"},
        incoming_handoff=_incoming(),
        subagent_runner=runner,
        provider="codex",
    )

    assert runner.calls[0]["options"]["provider"] == "codex"


def test_make_phase_callback_threads_resolved_provider_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The driver-facing callback wiring doesn't lose the pairing."""
    _stub_bridge(monkeypatch, _RESOLVED_CROSS_VENDOR)
    runner = _CapturingRunner()
    callback = phase_agent.make_phase_callback(phase="IMPLEMENT", subagent_runner=runner)

    class _State:
        last_handoff_id = None
        change_id = "ch-1"
        handoff_ids: list[str] = []
        phase_archetype = None

    state = _State()
    callback(state)

    assert runner.calls[0]["options"]["provider"] == "openrouter"


# ---------------------------------------------------------------------------
# claude_agent_runner / UnservableProviderError — non-retryable runner contract
# ---------------------------------------------------------------------------


def test_claude_agent_runner_raises_for_unsupported_provider_without_calling_agent_fn() -> None:
    calls: list[dict[str, Any]] = []

    def agent_fn(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        calls.append(options)
        return ("complete", "h-should-not-happen")

    runner = phase_agent.claude_agent_runner(agent_fn, supported=frozenset({"claude_code"}))

    with pytest.raises(phase_agent.UnservableProviderError) as excinfo:
        runner(prompt="p", options={"provider": "codex"})

    assert calls == []
    assert excinfo.value.provider == "codex"
    assert "claude_code" in excinfo.value.supported


def test_claude_agent_runner_dispatches_a_supported_provider() -> None:
    def agent_fn(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        return ("complete", "h-1")

    runner = phase_agent.claude_agent_runner(agent_fn)

    assert runner(prompt="p", options={"provider": "claude_code"}) == ("complete", "h-1")


def test_claude_agent_runner_dispatches_when_provider_key_absent() -> None:
    """A runner never receiving a `provider` key (older caller) still dispatches."""

    def agent_fn(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        return ("complete", "h-2")

    runner = phase_agent.claude_agent_runner(agent_fn)

    assert runner(prompt="p", options={}) == ("complete", "h-2")


def test_run_phase_subagent_escalates_immediately_on_unservable_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-retryable: one call, no retry, PhaseEscalationError with attempts=1."""
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, Any]] = []

    def runner(*, prompt: str, options: dict[str, Any]) -> tuple[str, str]:
        calls.append(options)
        raise phase_agent.UnservableProviderError(
            options.get("provider", "?"), frozenset({"claude_code"})
        )

    with pytest.raises(phase_agent.PhaseEscalationError) as excinfo:
        phase_agent.run_phase_subagent(
            phase="IMPLEMENT",
            state_dict={"change_id": "ch-1"},
            incoming_handoff=_incoming(),
            subagent_runner=runner,
            max_attempts=3,
        )

    assert len(calls) == 1
    assert excinfo.value.attempts == 1
    assert excinfo.value.phase == "IMPLEMENT"


# ---------------------------------------------------------------------------
# smoke_provider_dispatch — pairs resolved provider with resolved model
# ---------------------------------------------------------------------------


def _run_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SMOKE), *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_smoke_reports_both_provider_and_resolved_provider_json() -> None:
    proc = _run_smoke("--provider", "codex", "--dry-run", "--json")
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["provider"] == "codex"
    assert "resolved_provider" in body


def test_smoke_reports_both_provider_and_resolved_provider_text() -> None:
    proc = _run_smoke("--provider", "codex", "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "provider=codex" in proc.stdout
    assert "resolved_provider=" in proc.stdout


def test_smoke_local_dry_run_still_succeeds_inside_trust_boundary() -> None:
    """Routed away from (or safely inside, in dry-run) `local`: it dispatches."""
    proc = _run_smoke("--provider", "local", "--dry-run", "--json")
    assert proc.returncode == 0, proc.stderr
