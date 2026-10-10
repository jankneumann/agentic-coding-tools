"""World builder tests (P.1-P.4 at the API level, design D6)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mpsim.errors import UsageError
from mpsim.world import World

SEED = {
    "openspec/specs/sim-notes/spec.md": "# sim-notes\n\n### Requirement: Alpha\n",
    "roadmap.yaml": "schema_version: 1\n",
}


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)},
    )
    return out.stdout.strip()


def _build(tmp_path: Path, names=("alice", "bob")) -> World:
    return World.create(tmp_path / "world", names, seed_files=SEED)


def _commit_change(world: World, who: str, change: str, tick: int = 1, push: bool = True):
    world.add_worktree(who, change, tick)
    wt = world.worktree_path(who, change)
    (wt / "openspec" / "changes" / change).mkdir(parents=True)
    (wt / "openspec" / "changes" / change / "proposal.md").write_text(f"# {change}\n")
    world.commit(who, change, f"feat: {change}", tick)
    if push:
        world.push(who, change)


def test_two_principals_have_distinct_identities_clones_worktrees_and_agents(tmp_path):
    world = _build(tmp_path)
    _commit_change(world, "alice", "sim-alice-notes")
    _commit_change(world, "bob", "sim-bob-notes")
    world.fetch("alice")

    alice, bob = world.principal("alice"), world.principal("bob")
    assert alice.email == "alice@sim.invalid"
    assert bob.email == "bob@sim.invalid"
    assert alice.agent_id != bob.agent_id
    assert alice.agent_id == "alice-agent-1"
    assert alice.clone != bob.clone
    assert world.worktree_path("alice", "sim-alice-notes") != world.worktree_path(
        "bob", "sim-bob-notes"
    )
    # Identity of every commit reachable from the change branch but not from main.
    a_authors = _git(
        alice.clone, "log", "--format=%an <%ae>|%cn <%ce>", "origin/main..sim/alice/sim-alice-notes"
    ).splitlines()
    assert a_authors == ["alice <alice@sim.invalid>|alice <alice@sim.invalid>"]
    b_authors = _git(
        bob.clone, "log", "--format=%an <%ae>", "origin/main..sim/bob/sim-bob-notes"
    ).splitlines()
    assert b_authors == ["bob <bob@sim.invalid>"]


def test_seed_commit_is_authored_by_sim_seed(tmp_path):
    world = _build(tmp_path)
    author = _git(world.principal("alice").clone, "log", "-1", "--format=%an <%ae>", "origin/main")
    assert author == "sim-seed <sim-seed@sim.invalid>"
    assert world.remote_url.startswith("file://")


def test_unpushed_commit_is_invisible_to_the_other_principal(tmp_path):
    world = _build(tmp_path)
    _commit_change(world, "alice", "sim-alice-notes", push=False)
    sha = _git(world.principal("alice").clone, "rev-parse", "sim/alice/sim-alice-notes")
    world.fetch("bob")
    bob_clone = world.principal("bob").clone
    assert "alice" not in _git(bob_clone, "for-each-ref", "--format=%(refname)")
    probe = subprocess.run(["git", "cat-file", "-e", sha], cwd=bob_clone, capture_output=True)
    assert probe.returncode != 0


def test_pushed_commit_becomes_visible_after_fetch(tmp_path):
    world = _build(tmp_path)
    _commit_change(world, "alice", "sim-alice-notes")
    world.fetch("bob")
    refs = _git(world.principal("bob").clone, "for-each-ref", "--format=%(refname)")
    assert "refs/remotes/origin/sim/alice/sim-alice-notes" in refs


def test_three_principals_build(tmp_path):
    world = _build(tmp_path, names=("alice", "bob", "carol"))
    principals = [world.principal(n) for n in ("alice", "bob", "carol")]
    assert len({p.email for p in principals}) == 3
    assert len({p.clone for p in principals}) == 3
    assert len({p.agent_id for p in principals}) == 3


def test_one_principal_is_a_usage_error_naming_the_minimum(tmp_path):
    with pytest.raises(UsageError, match="at least 2 principals"):
        World.create(tmp_path / "world", ("alice",), seed_files=SEED)


def test_duplicate_principal_names_are_rejected(tmp_path):
    with pytest.raises(UsageError):
        World.create(tmp_path / "world", ("alice", "alice"), seed_files=SEED)


def test_commit_dates_derive_from_the_tick_and_ignore_global_config(tmp_path, monkeypatch):
    gitconfig = tmp_path / "evil.gitconfig"
    gitconfig.write_text("[user]\n\tname = Mallory\n\temail = m@example.com\n"
                         "[commit]\n\tgpgsign = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("HOME", str(tmp_path))
    world = _build(tmp_path)
    _commit_change(world, "alice", "sim-alice-notes", tick=3)
    clone = world.principal("alice").clone
    # Raw dates (`<epoch> <tz>`), not %aI: git changed how strict ISO renders UTC
    # (`+00:00` before 2.5x, `Z` after), and the assertion is about the date, not
    # git's formatting. 1767225780 is 2026-01-01T00:03:00Z, i.e. tick 3.
    date = _git(
        clone, "log", "-1", "--date=raw", "--format=%ad|%cd|%an", "sim/alice/sim-alice-notes"
    )
    assert date == "1767225780 +0000|1767225780 +0000|alice"


def test_identical_inputs_in_different_roots_give_identical_commit_ids(tmp_path):
    w1 = World.create(tmp_path / "one", ("alice", "bob"), seed_files=SEED)
    w2 = World.create(tmp_path / "two" / "deeper", ("alice", "bob"), seed_files=SEED)
    for w in (w1, w2):
        _commit_change(w, "alice", "sim-alice-notes", tick=2)
    refs = [
        _git(w.principal("alice").clone, "rev-parse", "sim/alice/sim-alice-notes") for w in (w1, w2)
    ]
    assert refs[0] == refs[1]


def test_principal_view_is_read_only_and_exposes_worktree_and_remote(tmp_path):
    world = _build(tmp_path)
    _commit_change(world, "alice", "sim-alice-notes")
    view = world.view("alice", "sim-alice-notes")
    assert view.worktree == world.worktree_path("alice", "sim-alice-notes")
    assert view.remote_url == world.remote_url
    assert view.principal == "alice"
    assert view.read_text("openspec/changes/sim-alice-notes/proposal.md") == "# sim-alice-notes\n"
    assert not hasattr(view, "push") and not hasattr(view, "commit")
    with pytest.raises(AttributeError):
        view.worktree = Path("/elsewhere")  # frozen


def test_read_ref_returns_file_content_from_the_fetched_remote_main(tmp_path):
    world = _build(tmp_path)
    world.fetch("bob")
    assert world.read_ref("bob", "origin/main", "roadmap.yaml") == SEED["roadmap.yaml"]
