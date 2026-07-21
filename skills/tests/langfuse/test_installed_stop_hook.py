from __future__ import annotations

import importlib.util
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


def test_installer_records_the_actual_mirror_path(tmp_path: Path) -> None:
    repo = tmp_path / "consumer"
    scripts = repo / ".claude" / "skills" / "langfuse" / "scripts"
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "langfuse" / "scripts"
    for name in ("install_stop_hook.py", "run_stop_hook.sh", "langfuse_hook.py"):
        (scripts / name).write_bytes((source / name).read_bytes())
    (repo / ".git").mkdir()

    spec = importlib.util.spec_from_file_location("installed_langfuse_hook", scripts / "install_stop_hook.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    settings: dict = {}
    assert module.upsert(settings) is True
    command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert ".claude/skills/langfuse/scripts/run_stop_hook.sh" in command
    assert (scripts / "langfuse_hook.py").is_file()
    assert "agent-coordinator" not in (scripts / "run_stop_hook.sh").read_text()
    assert "langfuse>=4.14,<5.0" in (scripts / "run_stop_hook.sh").read_text()


def test_stop_hook_docs_match_runtime_sdk_constraint() -> None:
    skill = Path(__file__).resolve().parents[2] / "langfuse"
    assert "langfuse>=4.14,<5.0" in (skill / "references" / "stop-hook.md").read_text()


def test_shipped_hook_uses_langfuse_v4_observations(monkeypatch) -> None:
    hook_path = Path(__file__).resolve().parents[2] / "langfuse" / "scripts" / "langfuse_hook.py"
    spec = importlib.util.spec_from_file_location("portable_langfuse_hook", hook_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls: list[tuple[str, dict]] = []

    class Observation:
        def start_observation(self, **kwargs):
            calls.append(("child", kwargs))
            return Observation()

        def update(self, **kwargs):
            calls.append(("update", kwargs))

        def end(self):
            calls.append(("end", {}))

    class Client:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def start_observation(self, **kwargs):
            calls.append(("root", kwargs))
            return Observation()

        def flush(self):
            calls.append(("flush", {}))

        def shutdown(self):
            calls.append(("shutdown", {}))

    fake = SimpleNamespace(
        Langfuse=Client,
        propagate_attributes=lambda **kwargs: nullcontext(),
    )
    monkeypatch.setitem(sys.modules, "langfuse", fake)
    count = module.send_turns_to_langfuse(
        [{"user_message": "hi", "assistant_messages": ["hello"], "model": "m", "tool_calls": []}],
        "session",
        "project",
    )

    assert count == 1
    assert any(name == "root" and data["as_type"] == "agent" for name, data in calls)
    assert not hasattr(Client, "trace")
