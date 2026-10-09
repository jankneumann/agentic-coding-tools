"""Plain data shared by the fixture loader, agents and schedulers."""

from __future__ import annotations

from dataclasses import dataclass, field

STEP_NAMES = ("plan", "contract", "implement")


@dataclass(frozen=True)
class Transition:
    """A status change declared by fixture data for a principal's own roadmap item."""

    set_status: str


@dataclass(frozen=True)
class Step:
    name: str
    duration: int
    files_from: str | None = None  # fixture-relative directory copied into the worktree root
    on_start: Transition | None = None
    on_finish: Transition | None = None


@dataclass(frozen=True)
class StatusTransition:
    """A declared transition bound to the principal that reported it."""

    principal: str
    item_id: str
    status: str
    when: str  # "start" | "finish"
    step: str


@dataclass(frozen=True)
class PrincipalSpec:
    name: str
    change_id: str
    roadmap_item: str | None = None
    steps: tuple[Step, ...] = field(default_factory=tuple)

    def step(self, name: str) -> Step | None:
        return next((s for s in self.steps if s.name == name), None)
