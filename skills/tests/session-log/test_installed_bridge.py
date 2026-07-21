from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_bridge_is_found_from_agents_skills_layout(tmp_path: Path) -> None:
    skills = tmp_path / ".agents" / "skills"
    session_script = skills / "session-log" / "scripts" / "phase_record.py"
    bridge_script = skills / "coordination-bridge" / "scripts" / "coordination_bridge.py"
    session_script.parent.mkdir(parents=True)
    bridge_script.parent.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "session-log" / "scripts" / "phase_record.py"
    session_script.write_bytes(source.read_bytes())
    bridge_script.write_text("def try_handoff_write(**kwargs):\n    return {'handoff_id': 'installed'}\n")

    spec = importlib.util.spec_from_file_location("installed_phase_record", session_script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module._installed_bridge_path() == bridge_script
