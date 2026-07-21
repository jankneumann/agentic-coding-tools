from __future__ import annotations

import importlib.util
from pathlib import Path


def test_installed_hook_does_not_import_coordinator_src(capsys) -> None:
    path = Path(__file__).resolve().parents[2] / "session-bootstrap" / "scripts" / "hooks" / "print_coordinator_env.py"
    assert "from src." not in path.read_text()
    spec = importlib.util.spec_from_file_location("print_coordinator_env", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    assert "Coordinator Configuration" in capsys.readouterr().out
