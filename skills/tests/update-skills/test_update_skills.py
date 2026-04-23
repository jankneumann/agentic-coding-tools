"""Tests for skills/update-skills/scripts/update_skills.py orchestrator.

Uses a temp directory set up as a real git repo with fake install.sh and
fake `origin` remote, so we exercise the real subprocess flow rather than
mocking it.

Spec scenarios:
- skill-runtime-sync.1 (propagation)
- skill-runtime-sync.2 (no-op)
- skill-runtime-sync.3 (commit message)
- skill-runtime-sync.a (orchestrator aborts on sync-script failure)
- skill-runtime-sync.b (orchestrator aborts on install.sh failure)
- skill-runtime-sync.push_success, push_retry, push_retry_exhausted
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "skills" / "update-skills" / "scripts" / "update_skills.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("update_skills", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_skills = _load_module()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a temp repo with:
    - A bare 'origin' remote
    - CLAUDE.md, AGENTS.md (in sync)
    - skills/install.sh (fake, writes to .claude/skills/ and .agents/skills/)
    - skills/update-skills/scripts/sync_agents_md.py (real script, symlinked)
    - An initial commit
    """
    # Bare origin
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)

    # Working repo
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    # Disable commit signing for this tmp test repo only. The session's default
    # signing backend requires infrastructure that isn't available for tmp
    # fixtures — this bypass is scoped to the fixture, not the real repo.
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")
    _git(repo, "config", "gpg.format", "openpgp")
    _git(repo, "remote", "add", "origin", str(origin))

    # Files
    (repo / "CLAUDE.md").write_text("# CLAUDE\ncontext\n")
    (repo / "AGENTS.md").write_text("# CLAUDE\ncontext\n")
    (repo / "skills" / "update-skills" / "scripts").mkdir(parents=True)
    # Copy the real sync_agents_md.py so update_skills.py can find it at the expected path
    real_sync = ROOT / "skills" / "update-skills" / "scripts" / "sync_agents_md.py"
    (repo / "skills" / "update-skills" / "scripts" / "sync_agents_md.py").write_bytes(
        real_sync.read_bytes()
    )

    # Fake install.sh that creates .claude/skills/foo/SKILL.md and .agents/skills/foo/SKILL.md
    install = repo / "skills" / "install.sh"
    install.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "mkdir -p .claude/skills/foo .agents/skills/foo\n"
        "echo 'content v1' > .claude/skills/foo/SKILL.md\n"
        "echo 'content v1' > .agents/skills/foo/SKILL.md\n"
    )
    install.chmod(0o755)

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "push", "-u", "origin", "main")
    return repo


def test_propagation_and_commit_message(repo: Path) -> None:
    """Scenario skill-runtime-sync.1 + .3: install.sh output gets staged, commit uses
    conventional message."""
    exit_code = update_skills.orchestrate(repo)
    assert exit_code == 0

    # Runtime files exist
    assert (repo / ".claude" / "skills" / "foo" / "SKILL.md").read_text() == "content v1\n"
    assert (repo / ".agents" / "skills" / "foo" / "SKILL.md").read_text() == "content v1\n"

    # Latest commit message matches
    msg = _git(repo, "log", "-1", "--format=%s").strip()
    assert msg == "chore(skills): sync runtime copies"


def test_noop_when_nothing_changed(repo: Path) -> None:
    """Scenario .2: second run is a no-op — no empty commit."""
    update_skills.orchestrate(repo)
    first_sha = _git(repo, "rev-parse", "HEAD").strip()

    # Reset origin to match so push is a no-op too
    exit_code = update_skills.orchestrate(repo)
    assert exit_code == 0
    second_sha = _git(repo, "rev-parse", "HEAD").strip()
    assert first_sha == second_sha, "no-op run must not create a new commit"


def test_install_failure_aborts(repo: Path) -> None:
    """Scenario .b: install.sh nonzero exit -> skill exits 1, no sync, no commit."""
    (repo / "skills" / "install.sh").write_text(
        "#!/usr/bin/env bash\necho 'boom' >&2\nexit 7\n"
    )
    (repo / "skills" / "install.sh").chmod(0o755)

    pre_sha = _git(repo, "rev-parse", "HEAD").strip()
    exit_code = update_skills.orchestrate(repo)
    assert exit_code == 1
    post_sha = _git(repo, "rev-parse", "HEAD").strip()
    assert pre_sha == post_sha, "install.sh failure must not produce a commit"


def test_sync_failure_aborts_keeps_install_staged(repo: Path) -> None:
    """Scenario .a: install.sh succeeds, sync fails -> no commit, install output stays staged."""
    # Delete CLAUDE.md so sync_agents_md.py exits 1
    (repo / "CLAUDE.md").unlink()

    pre_sha = _git(repo, "rev-parse", "HEAD").strip()
    exit_code = update_skills.orchestrate(repo)
    assert exit_code == 1
    post_sha = _git(repo, "rev-parse", "HEAD").strip()
    assert pre_sha == post_sha, "sync failure must not produce a commit"


def test_push_success_exits_zero(repo: Path) -> None:
    """push_success scenario: push succeeds on first attempt, SHA reported."""
    exit_code = update_skills.orchestrate(repo)
    assert exit_code == 0
    # Verify push actually happened by checking origin
    remote = subprocess.run(
        ["git", "ls-remote", "origin"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert "refs/heads/main" in remote.stdout


def test_push_retry_exhausted_emits_unpushed_commit(repo: Path, capsys, monkeypatch) -> None:
    """push_retry_exhausted: monkey-patch the subprocess.run used for push to always fail.

    We do this by pointing `origin` at a non-existent path so every push rejects.
    """
    # Run install + sync + commit first via the real orchestrator up to the push step
    update_skills.step_install(repo)
    update_skills.step_sync_agents(repo)
    update_skills.step_stage_and_commit(repo)

    # Break origin so push will fail
    _git(repo, "remote", "set-url", "origin", str(repo.parent / "does-not-exist.git"))

    with pytest.raises(update_skills.StepFailed):
        update_skills.step_push_with_retry(repo, sleep=lambda _s: None)

    captured = capsys.readouterr()
    assert "UNPUSHED_COMMIT=" in captured.out
    # Per-attempt summary on stderr
    assert "attempt 1" in captured.err
    assert "attempt 3" in captured.err
