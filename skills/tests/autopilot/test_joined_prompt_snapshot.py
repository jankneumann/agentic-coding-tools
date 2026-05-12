"""Snapshot test for the joined `system_prompt + SEPARATOR + phase_prompt`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Scenario: "Joined prompt preserves phase task instructions even when
      phase prompt contains '---'"
Design decisions: D2 (folding semantics + separator clash mitigation).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import coordination_bridge
import phase_agent
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed_loop_state(repo_root: Path, change_id: str) -> Path:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 3,
        "change_id": change_id,
        "current_phase": "IMPLEMENT",
        "iteration": 0,
        "total_iterations": 0,
        "max_phase_iterations": 3,
        "findings_trend": [],
        "blocking_findings": [],
        "vendor_availability": {},
        "packages_status": {},
        "package_authors": {},
        "implementation_strategy": {},
        "memory_ids": [],
        "handoff_ids": [],
        "last_handoff_id": None,
        "started_at": "2026-05-05T00:00:00+00:00",
        "phase_started_at": "2026-05-05T00:00:00+00:00",
        "previous_phase": None,
        "escalation_reason": None,
        "val_review_enabled": False,
        "cli_review_enabled": True,
        "error": None,
        "phase_archetype": None,
    }
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return state_path


def test_joined_prompt_preserves_phase_instructions_with_embedded_rules(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase prompt may contain `\\n---\\n` rules; the fold must not be ambiguous.

    Asserts:
      a) the literal SEPARATOR `\\n\\n---\\n\\n` appears exactly once between
         the system prompt and the phase prompt (not zero, not two);
      b) all key task-instruction tokens (`change_id`, `submit`, `complete`)
         from the phase prompt survive the fold unchanged.
    """
    # System prompt explicitly does NOT contain the separator string itself —
    # the test focuses on phase prompts that contain `\n---\n` (a markdown
    # rule), which differs from `\n\n---\n\n` (the SEPARATOR) by one newline.
    resolved: dict[str, Any] = {
        "model": "sonnet",
        "system_prompt": "You are the implementer. Follow contracts.",
        "archetype": "implementer",
        "reasons": [],
    }
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **_: resolved,
    )

    # Inject a phase task-instruction string that itself contains `\n---\n`.
    # This is realistic: phase prompts are markdown-flavoured and may
    # include horizontal rules between sections.
    embedded_rule_instructions = (
        "Implement the next slice of work per tasks.md. Commit per task.\n"
        "Push commits to the feature branch. Return outcome 'continue' on\n"
        "success, 'escalate' on unrecoverable error.\n"
        "\n---\n"
        "Reminder: change_id is in state.change_id; submit each task as a\n"
        "separate commit; mark each task complete in tasks.md."
    )
    monkeypatch.setitem(phase_agent._PHASE_TASKS, "IMPLEMENT", embedded_rule_instructions)
    _seed_loop_state(chdir_tmp, "demo")

    result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo")
    folded: str = result["prompt"]

    # (a) Exactly one occurrence of the literal SEPARATOR between system and phase.
    assert folded.count("\n\n---\n\n") == 1, (
        f"expected exactly one SEPARATOR between system prompt and phase prompt; "
        f"found {folded.count(chr(10) + chr(10) + '---' + chr(10) + chr(10))} occurrences"
    )

    # The SEPARATOR must come right after the system prompt — verify via regex
    # anchored at the start.
    assert re.match(
        r"^You are the implementer\. Follow contracts\.\n\n---\n\n",
        folded,
    ), "SEPARATOR did not directly follow the system prompt"

    # (b) Key task-instruction tokens survive the fold unchanged.
    for token in ("change_id", "submit", "complete"):
        assert token in folded, f"task token {token!r} disappeared after fold"

    # The embedded `\n---\n` rule (NOT a SEPARATOR) appears in the phase-prompt
    # half — confirm it survives, because we want to detect double-fold bugs
    # where the `\n---\n` got rewritten or normalized.
    assert "\n---\n" in folded
    # And there is exactly one boundary that is the literal SEPARATOR (4-newline
    # variant), even though `\n---\n` rules show up too.
    assert folded.count("\n\n---\n\n") == 1
