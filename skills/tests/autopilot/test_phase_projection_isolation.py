"""Projection stays isolated to explicit coordinated host boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_autopilot_and_runner_do_not_eagerly_import_projection_module() -> None:
    for relative in (
        "skills/autopilot/scripts/autopilot.py",
        "skills/autopilot/scripts/runner.py",
    ):
        tree = ast.parse((ROOT / relative).read_text())
        top_level = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        assert all(
            getattr(node, "module", None) != "queue_projection"
            and all(alias.name != "queue_projection" for alias in getattr(node, "names", []))
            for node in top_level
        )


def test_skill_protocol_limits_projection_to_coordinated_tier() -> None:
    text = (ROOT / "skills/autopilot/SKILL.md").read_text()
    assert "only** after coordinator detection selected the\ncoordinated tier" in text
    assert "local-parallel and sequential hosts do not import" in text
    assert "exits 0, 3, and 4" in text
    assert "A non-zero mutation exit suppresses projection" in text
    for command in (
        "init",
        "transition",
        "apply-outcome",
        "record-state-only-archetype",
        "gate-answer",
    ):
        assert command in text



def test_coordinator_free_run_cannot_call_projection_transport(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    import autopilot
    import pytest

    bridge_dir = ROOT / "skills/coordination-bridge/scripts"
    sys.path.insert(0, str(bridge_dir))
    import coordination_bridge

    def unexpected_call(**_kwargs):
        pytest.fail("coordinator-free run called projection transport")

    for name in (
        "try_submit_work",
        "try_reconcile_work_projection",
        "try_projection_issue_list",
        "try_projection_issue_update",
    ):
        monkeypatch.setattr(coordination_bridge, name, unexpected_call)

    state_path = tmp_path / "loop-state.json"
    autopilot.save_state(
        autopilot.LoopState(
            change_id="coordinator-free",
            current_phase="IMPLEMENT",
            total_iterations=1,
        ),
        state_path,
    )
    autopilot.run_loop(
        "coordinator-free",
        tmp_path,
        tmp_path,
        state_path=state_path,
        queue_projection_fn=None,
        max_global_iterations=1,
    )
