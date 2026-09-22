"""Contract tests for the non-blocking SessionEnd hook."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATHS = (
    REPO_ROOT / "agent-coordinator" / "scripts" / "deregister_agent.py",
    REPO_ROOT
    / "skills"
    / "session-bootstrap"
    / "scripts"
    / "hooks"
    / "deregister_agent.py",
)


def _load_hook(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"deregister_agent_{path.parent.parent.name}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("hook_path", HOOK_PATHS)
def test_session_end_releases_authenticated_agent_locks_before_status(
    hook_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = _load_hook(hook_path)
    calls: list[tuple[str, dict]] = []

    def fake_post(_base_url: str, path: str, payload: dict) -> dict:
        calls.append((path, payload))
        if path == "/handoffs/write":
            return {"success": True, "handoff_id": "handoff-1"}
        if path == "/locks/release-by-agent":
            return {"released_count": 2, "attempted_paths": ["a.py", "b.py"]}
        return {"success": True}

    monkeypatch.setenv("COORDINATION_API_URL", "https://coordinator.test")
    monkeypatch.setenv("AGENT_ID", "legacy-agent")
    monkeypatch.setenv("AGENT_TYPE", "codex")
    monkeypatch.delenv("SESSION_ID", raising=False)
    monkeypatch.setattr(hook, "_post", fake_post)

    hook.main()

    assert calls == [
        (
            "/handoffs/write",
            {
                "agent_id": "",
                "agent_type": "",
                "session_id": None,
                "summary": "Session ended.",
            },
        ),
        ("/locks/release-by-agent", {"agent_id": ""}),
        (
            "/status/report",
            {
                "agent_id": "legacy-agent",
                "change_id": "",
                "phase": "SESSION_END",
                "message": "Session ended",
                "needs_human": False,
                "event_type": "status.phase_transition",
                "metadata": {
                    "agent_type": "codex",
                    "session_id": "",
                    "event": "session.ended",
                },
            },
        ),
    ]
