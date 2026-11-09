"""The plan-time collision scenarios (design D4).

Alice plans, pushes and finishes. Bob fetches, then plans. At Bob's plan step the
scenario asks the ground-truth oracle (``collision_present``) and every selected probe
(``collision_detected``, ``probes``). The fixture decides whether a collision exists;
the scenario only checks that the fixture still means what the scenario name says.
"""

from __future__ import annotations

from pathlib import Path

from mpsim import probes as probe_registry
from mpsim.agents import ScriptedAgent
from mpsim.clock import Clock
from mpsim.errors import ScenarioError
from mpsim.model import PrincipalSpec, RunContext, Scenario
from mpsim.oracle import collision_present
from mpsim.report import new_report
from mpsim.world import World


def _change_dir(ctx: RunContext, spec: PrincipalSpec) -> Path:
    step = spec.step("plan")
    base = ctx.fixture.dir / step.files_from if step and step.files_from else ctx.fixture.dir / "_none"
    return base / "openspec" / "changes" / spec.change_id


def _run(ctx: RunContext, *, requires_collision: bool) -> dict:
    fixture = ctx.fixture
    world = World.create(
        ctx.work_root / "world", [p.name for p in fixture.principals], fixture.seed_files
    )
    clock = Clock()
    timeline: list[dict] = []

    def log(principal: str, event: str) -> None:
        timeline.append({"tick": clock.tick, "principal": principal, "step": "plan", "event": event})

    probe_entries: list[dict] = []
    present = detected = False
    for index, spec in enumerate(fixture.principals):
        step = spec.step("plan")
        if step is None:
            raise ScenarioError(f"principal {spec.name!r} declares no plan step")
        agent = ScriptedAgent(spec, fixture.dir)
        if index > 0:
            world.fetch(spec.name)
        log(spec.name, "started")
        clock.advance(step.duration)
        agent.act(world, step, clock.tick)
        log(spec.name, "finished")
        log(spec.name, "pushed")
        if index != 1:
            continue
        first = fixture.principals[0]
        present = collision_present(_change_dir(ctx, first), _change_dir(ctx, spec))
        results = probe_registry.run_probes(
            ctx.probes, world.view(spec.name, spec.change_id), spec.change_id
        )
        detected = probe_registry.detected(results, first.change_id)
        probe_entries = [probe_registry.as_report_entry(r) for r in results]
        log(spec.name, "probed")

    first, second = fixture.principals[0], fixture.principals[1]
    if requires_collision and not present:
        raise ScenarioError(
            f"scenario {ctx.scenario_id!r} requires a collision between {first.change_id} and "
            f"{second.change_id}, but the required collision is absent from the fixture"
        )
    if not requires_collision and present:
        raise ScenarioError(
            f"scenario {ctx.scenario_id!r} is a control but an unexpected collision is present "
            f"between {first.change_id} and {second.change_id}"
        )
    return new_report(
        ctx.scenario_id,
        principals=[
            {"name": p.name, "agent_id": f"{p.name}-agent-1", "change_id": p.change_id}
            for p in fixture.principals
        ],
        collision_present=present,
        collision_detected=detected,
        probes=probe_entries,
        final_tick=clock.tick,
        timeline=timeline,
    )


SCENARIOS = {
    "same-requirement-collision": Scenario(
        "same-requirement-collision",
        "same-requirement-collision",
        lambda ctx: _run(ctx, requires_collision=True),
    ),
    "different-requirement-control": Scenario(
        "different-requirement-control",
        "different-requirement-control",
        lambda ctx: _run(ctx, requires_collision=False),
    ),
}
