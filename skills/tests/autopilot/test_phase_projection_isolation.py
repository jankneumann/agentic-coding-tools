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
