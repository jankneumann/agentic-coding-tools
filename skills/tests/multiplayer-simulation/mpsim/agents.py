"""Scripted agents (design D7).

An agent performs one step's file edits and git operations and reports the status
transitions the fixture declared for that step. It never applies them: it does not
write ``roadmap.yaml`` and never pushes to ``main`` (operator decision A1). Only the
status applier (``mpsim.applier``) writes roadmap state.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

from mpsim.model import PrincipalSpec, StatusTransition, Step
from mpsim.world import World


@runtime_checkable
class Agent(Protocol):
    principal: str
    agent_id: str

    def declared_transitions(self, step: Step, when: str) -> list[StatusTransition]: ...

    def act(self, world: World, step: Step, tick: int) -> list[StatusTransition]: ...


class ScriptedAgent:
    """Replays a principal's fixture script deterministically."""

    def __init__(self, spec: PrincipalSpec, fixture_dir: Path) -> None:
        self.spec = spec
        self.fixture_dir = Path(fixture_dir)
        self.principal = spec.name
        self.agent_id = f"{spec.name}-agent-1"

    def declared_transitions(self, step: Step, when: str) -> list[StatusTransition]:
        transition = step.on_start if when == "start" else step.on_finish
        if transition is None or self.spec.roadmap_item is None:
            return []
        return [
            StatusTransition(
                self.principal, self.spec.roadmap_item, transition.set_status, when, step.name
            )
        ]

    def act(self, world: World, step: Step, tick: int) -> list[StatusTransition]:
        change = self.spec.change_id
        worktree = world.worktree_path(self.principal, change)
        if not worktree.exists():
            world.add_worktree(self.principal, change, tick)
        if step.files_from:
            shutil.copytree(self.fixture_dir / step.files_from, worktree, dirs_exist_ok=True)
        marker = worktree / "openspec" / "changes" / change / "steps" / f"{step.name}.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"# {step.name}\n\nStep `{step.name}` of {change}.\n")
        world.commit(self.principal, change, f"feat({change}): {step.name}", tick)
        world.push(self.principal, change)
        return self.declared_transitions(step, "finish")
