from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

import check_coordinator
import coordination_bridge
import review_dispatcher


def _agents_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(textwrap.dedent("""\
        agents:
          codex-local:
            type: codex
            profile: codex_local
            trust_level: 3
            transport: mcp
            isolation: worktree
            capabilities: [lock, queue]
            archetypes: [architect, implementer, reviewer]
            description: Local Codex
            cli:
              command: codex
              dispatch_modes:
                review:
                  args: ["exec", "-s", "read-only"]
              model_flag: "-m"
              model: gpt-5.5
          gemini-local:
            type: gemini
            profile: gemini_local
            trust_level: 3
            transport: mcp
            isolation: worktree
            capabilities: [lock, queue]
            archetypes: [implementer, reviewer]
            description: Local Gemini
            cli:
              command: gemini
              dispatch_modes:
                review:
                  args: ["-p", ""]
              model_flag: "-m"
              model: gemini-3-flash-preview
    """))
    return path


def test_http_coordinator_detection_does_not_require_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_coordinator, "check_health", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(check_coordinator, "probe_route", lambda *_args, **_kwargs: True)

    def fail_if_called() -> bool:
        raise AssertionError("MCP detection should not run when HTTP succeeds")

    monkeypatch.setattr(check_coordinator, "detect_mcp_server", fail_if_called)

    result = check_coordinator.detect("http://coordinator.test")

    assert result["COORDINATOR_AVAILABLE"] is True
    assert result["COORDINATION_TRANSPORT"] == "http"
    assert result["CAN_LOCK"] is True


def test_explicit_agents_yaml_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _agents_yaml(tmp_path)
    monkeypatch.setenv("AGENTS_YAML", str(path))
    monkeypatch.setattr(review_dispatcher.ReviewOrchestrator, "_load_from_http", classmethod(lambda cls: None))

    orch = review_dispatcher.ReviewOrchestrator.from_coordinator()

    assert set(orch.adapters) == {"codex-local", "gemini-local"}


def test_local_agents_yaml_fallback_without_claude_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "agent-coordinator").mkdir(parents=True)
    path = _agents_yaml(repo / "agent-coordinator")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("AGENTS_YAML", raising=False)
    monkeypatch.setattr(review_dispatcher.ReviewOrchestrator, "_load_from_http", classmethod(lambda cls: None))
    monkeypatch.setattr(review_dispatcher.ReviewOrchestrator, "_find_coordinator_dir", classmethod(lambda cls: None))

    orch = review_dispatcher.ReviewOrchestrator.from_coordinator()

    assert path.exists()
    assert set(orch.adapters) == {"codex-local", "gemini-local"}


def test_bridge_warning_includes_provider_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("COORDINATION_API_URL", "http://coordinator.test")
    monkeypatch.setattr(
        review_dispatcher,
        "__name__",
        review_dispatcher.__name__,
    )
    monkeypatch.setattr(
        coordination_bridge,
        "_http_request",
        lambda **_kwargs: {"status_code": 503, "data": None, "error": "down"},
    )

    with caplog.at_level(logging.WARNING, logger="coordination_bridge"):
        result = coordination_bridge.try_resolve_archetype_for_phase(
            "IMPLEMENT",
            {},
            provider="codex",
        )

    assert result is None
    messages = "\n".join(record.message for record in caplog.records)
    assert "IMPLEMENT" in messages
    assert "codex" in messages
    assert "provider model mapping" in messages
