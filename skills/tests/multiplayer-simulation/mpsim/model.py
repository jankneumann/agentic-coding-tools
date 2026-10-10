"""Plain data shared by the fixture loader, agents and schedulers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass(frozen=True)
class Fixture:
    dir: Path
    principals: tuple[PrincipalSpec, ...]
    seed_files: dict[str, str]


@dataclass(frozen=True)
class RunContext:
    scenario_id: str
    fixture: Fixture
    probes: list  # selected CollisionProbe instances (empty when none is registered)
    tick_budget: int
    work_root: Path


@dataclass(frozen=True)
class Scenario:
    id: str
    fixture_name: str  # directory under fixtures/ used when --fixture-dir is not given
    run: Callable[[RunContext], dict]
