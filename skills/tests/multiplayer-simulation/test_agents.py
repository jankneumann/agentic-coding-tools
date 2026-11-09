"""ScriptedAgent and Clock tests (P.1; design D5, D7, operator decision A1)."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from mpsim.agents import Agent, ScriptedAgent
from mpsim.clock import Clock
from mpsim.model import PrincipalSpec, StatusTransition, Step, Transition
from mpsim.world import World

HARNESS = Path(__file__).resolve().parent
SEED = {"roadmap.yaml": "items: []\n", "openspec/specs/sim-notes/spec.md": "# sim-notes\n"}


def _spec(tmp_path: Path) -> tuple[PrincipalSpec, Path]:
    fixture = tmp_path / "fixture"
    payload = fixture / "principals" / "alice" / "plan" / "openspec" / "changes" / "sim-alice-notes"
    (payload / "specs" / "sim-notes").mkdir(parents=True)
    (payload / "proposal.md").write_text("# sim-alice-notes\n")
    (payload / "specs" / "sim-notes" / "spec.md").write_text(
        "## MODIFIED Requirements\n### Requirement: Alpha\n"
    )
    spec = PrincipalSpec(
        name="alice",
        change_id="sim-alice-notes",
        roadmap_item="ri-alice",
        steps=(
            Step("plan", 1, files_from="principals/alice/plan"),
            Step("implement", 4, on_start=Transition("in_progress"),
                 on_finish=Transition("completed")),
        ),
    )
    return spec, fixture


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
    ).stdout.strip()


@pytest.fixture
def setup(tmp_path):
    world = World.create(tmp_path / "world", ("alice", "bob"), seed_files=SEED)
    spec, fixture = _spec(tmp_path)
    agent = ScriptedAgent(spec, fixture)
    return world, agent, spec


def test_scripted_agent_satisfies_the_agent_protocol(setup):
    _, agent, _ = setup
    assert isinstance(agent, Agent)
    assert agent.principal == "alice"
    assert agent.agent_id == "alice-agent-1"


def test_plan_step_writes_openspec_files_commits_and_pushes_to_the_change_branch(setup):
    world, agent, spec = setup
    agent.act(world, spec.step("plan"), tick=1)

    wt = world.worktree_path("alice", "sim-alice-notes")
    assert (wt / "openspec/changes/sim-alice-notes/specs/sim-notes/spec.md").is_file()
    clone = world.principal("alice").clone
    assert _git(clone, "log", "-1", "--format=%an <%ae>", "sim/alice/sim-alice-notes") == (
        "alice <alice@sim.invalid>"
    )
    remote_refs = _git(world.principal("alice").clone, "ls-remote", "--heads", "origin")
    assert "refs/heads/sim/alice/sim-alice-notes" in remote_refs
    # main is untouched
    assert _git(clone, "rev-parse", "origin/main") == _git(clone, "rev-parse", "main")


def test_act_returns_the_declared_transitions_and_does_not_apply_them(setup):
    world, agent, spec = setup
    agent.act(world, spec.step("plan"), tick=1)
    result = agent.act(world, spec.step("implement"), tick=5)

    assert result == [StatusTransition("alice", "ri-alice", "completed", "finish", "implement")]
    assert agent.declared_transitions(spec.step("implement"), "start") == [
        StatusTransition("alice", "ri-alice", "in_progress", "start", "implement")
    ]
    assert agent.act(world, spec.step("plan"), tick=6) == []  # plan declares nothing

    changed = _git(world.principal("alice").clone, "diff", "--name-only",
                   "origin/main", "sim/alice/sim-alice-notes").splitlines()
    assert "roadmap.yaml" not in changed


def test_agent_never_modifies_roadmap_or_pushes_main(setup):
    world, agent, spec = setup
    agent.act(world, spec.step("plan"), tick=1)
    agent.act(world, spec.step("implement"), tick=5)
    clone = world.principal("alice").clone
    world.fetch("alice")
    assert _git(clone, "rev-list", "--count", "origin/main") == "1"  # only the seed commit
    touched = _git(clone, "log", "--name-only", "--format=", "origin/main..sim/alice/sim-alice-notes")
    assert "roadmap.yaml" not in touched.splitlines()


def test_a_step_without_files_still_produces_a_commit(setup):
    world, agent, spec = setup
    agent.act(world, spec.step("plan"), tick=1)
    before = _git(world.principal("alice").clone, "rev-list", "--count", "sim/alice/sim-alice-notes")
    agent.act(world, spec.step("implement"), tick=5)
    after = _git(world.principal("alice").clone, "rev-list", "--count", "sim/alice/sim-alice-notes")
    assert int(after) == int(before) + 1


def test_clock_advances_only_when_told_to():
    clock = Clock()
    assert clock.tick == 0
    assert clock.tick == 0
    assert clock.advance() == 1
    assert clock.advance(3) == 4
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_clock_module_never_reads_wall_clock_time():
    tree = ast.parse((HARNESS / "mpsim" / "clock.py").read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }
    assert not imported & {"time", "datetime", "calendar"}
