"""The memory-store blocked-dependency scenarios (design D5).

A logical tick scheduler. It holds *no* readiness logic: on every tick each waiting
principal fetches the shared remote's ``main``, loads ``roadmap.yaml`` from
``origin/main`` through roadmap-runtime's ``load_roadmap`` (validated against the real
repository's schema) and asks ``Roadmap.ready_items()`` whether its item is admitted.
That call below is the one ``ri-11`` changes the meaning of.

Intra-tick order, fixed because the pinned baseline depends on it:

1. every step finishing at tick t pushes its work, in fixture declaration order;
2. the applier commits the ``on_finish`` transitions reported at t, then pushes once;
3. each waiting principal fetches ``main`` and evaluates ``ready_items()``;
4. the applier commits the ``on_start`` transitions of the principals admitted at t.

Status transitions come from fixture data only. Nothing here names a status.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from mpsim.agents import ScriptedAgent
from mpsim.applier import ROADMAP_FILE, StatusApplier
from mpsim.errors import ScenarioError
from mpsim.model import PrincipalSpec, RunContext, Scenario, StatusTransition, Step
from mpsim.paths import REPO_ROOT, RUNTIME_SCRIPTS
from mpsim.report import new_report
from mpsim.world import World


def _load_roadmap(path: Path):
    if str(RUNTIME_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(RUNTIME_SCRIPTS))
    from models import load_roadmap  # roadmap-runtime, the real admission rule's home

    return load_roadmap(path, REPO_ROOT)


@dataclass
class _State:
    spec: PrincipalSpec
    agent: ScriptedAgent
    index: int = 0
    phase: str = "running"  # running | waiting | done
    finish_tick: int = 0
    earliest_start: int | None = None
    ready_tick: int | None = None
    pending_finish: list[StatusTransition] = field(default_factory=list)

    @property
    def step(self) -> Step:
        return self.spec.steps[self.index]


def _run(ctx: RunContext) -> dict:
    fixture = ctx.fixture
    world = World.create(
        ctx.work_root / "world", [p.name for p in fixture.principals], fixture.seed_files
    )
    applier = StatusApplier(world, ctx.work_root)
    scratch = ctx.work_root / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    timeline: list[dict] = []
    states: list[_State] = []
    for spec in fixture.principals:
        if not spec.steps:
            raise ScenarioError(f"principal {spec.name!r} declares no steps")
        if spec.roadmap_item is None:
            raise ScenarioError(f"principal {spec.name!r} declares no roadmap_item")
        states.append(_State(spec, ScriptedAgent(spec, fixture.dir)))

    def log(tick: int, state: _State, step: str, event: str) -> None:
        timeline.append({"tick": tick, "principal": state.spec.name, "step": step, "event": event})

    def begin(state: _State, tick: int) -> None:
        """Enter the current step at ``tick``: run it, or wait for admission."""
        step = state.step
        if step.name == "implement":
            state.phase = "waiting"
            state.earliest_start = tick
        else:
            state.phase = "running"
            state.finish_tick = tick + step.duration
            log(tick, state, step.name, "started")

    for state in states:
        begin(state, 0)

    tick = 0
    final_tick = 0
    while True:
        final_tick = tick
        # 1. steps finishing at this tick push their work, in declaration order
        finished: list[StatusTransition] = []
        for state in states:
            if state.phase == "running" and state.finish_tick == tick:
                step = state.step
                transitions = state.agent.act(world, step, tick)
                log(tick, state, step.name, "finished")
                log(tick, state, step.name, "pushed")
                finished.extend(transitions)
                state.index += 1
                if state.index >= len(state.spec.steps):
                    state.phase = "done"
                else:
                    begin(state, tick)
        # 2. the applier commits the reported on_finish transitions to main
        applier.apply(finished, tick)
        for t in finished:
            timeline.append({"tick": tick, "principal": t.principal, "step": t.step,
                             "event": "status_applied"})
        # 3. each waiting principal fetches main and asks the real admission rule
        admitted: list[_State] = []
        for state in states:
            if state.phase != "waiting":
                continue
            world.fetch(state.spec.name)
            roadmap_path = scratch / f"{state.spec.name}-roadmap.yaml"
            roadmap_path.write_text(
                world.read_ref(state.spec.name, "origin/main", ROADMAP_FILE)
            )
            ready = {item.item_id for item in _load_roadmap(roadmap_path).ready_items()}
            if state.spec.roadmap_item in ready:
                admitted.append(state)
            elif state.earliest_start == tick:
                log(tick, state, "implement", "blocked")
        # 4. the applier commits on_start for the principals admitted at this tick
        starts: list[StatusTransition] = []
        for state in admitted:
            state.ready_tick = tick
            log(tick, state, "implement", "admitted")
            starts.extend(state.agent.declared_transitions(state.step, "start"))
        applier.apply(starts, tick)
        for state in admitted:
            state.phase = "running"
            state.finish_tick = tick + state.step.duration
            log(tick, state, "implement", "started")
        for t in starts:
            timeline.append({"tick": tick, "principal": t.principal, "step": t.step,
                             "event": "status_applied"})

        if all(s.phase == "done" for s in states):
            break
        if not any(s.phase == "running" for s in states):
            # Nothing is running and nothing was admitted: main can never change again.
            final_tick = ctx.tick_budget
            break
        if tick >= ctx.tick_budget:
            break
        tick += 1

    blocked: dict[str, int] = {}
    unblocked: dict[str, bool] = {}
    for state in states:
        name = state.spec.name
        if state.ready_tick is not None and state.earliest_start is not None:
            blocked[name] = state.ready_tick - state.earliest_start
            unblocked[name] = True
        elif state.earliest_start is not None:
            blocked[name] = ctx.tick_budget - state.earliest_start
            unblocked[name] = False
        else:  # never reached implement within the budget, so it never began waiting
            blocked[name] = 0
            unblocked[name] = False

    return new_report(
        ctx.scenario_id,
        principals=[
            {"name": s.spec.name, "agent_id": s.agent.agent_id, "change_id": s.spec.change_id}
            for s in states
        ],
        blocked_ticks=dict(sorted(blocked.items())),
        unblocked=dict(sorted(unblocked.items())),
        final_tick=final_tick,
        timeline=timeline,
    )


SCENARIOS = {
    "memory-store-blocked-dependency": Scenario(
        "memory-store-blocked-dependency", "memory-store-blocked-dependency", _run
    ),
    "independent-principals-control": Scenario(
        "independent-principals-control", "independent-principals-control", _run
    ),
}
