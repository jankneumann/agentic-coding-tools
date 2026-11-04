"""Isolation tests for ``test_oracle_audit.isolation`` (tasks 3.2, 3.3).

Derived from the "Read-Only Audit Execution" requirement (spec scenarios
test-oracle-audit.6 and .7) and design D3 ("Read-only by construction").
The module under test does not exist yet; these tests define its public API:

    isolated_copy(repo_root, *, scratch_root=None) -> ContextManager[IsolatedCopy]
    IsolatedCopy(root: Path, env: dict[str, str], basetemp: Path)

Nothing here needs network, uv or mutmut: audited tests run with the current
interpreter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from test_oracle_audit.isolation import IsolatedCopy, isolated_copy

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
}


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**_GIT_ENV, "HOME": str(cwd)},
    )
    return out.stdout


def _make_repo(dest: Path, name: str, *, with_git: bool = True) -> Path:
    shutil.copytree(
        FIXTURES / name,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    if with_git:
        _git(dest, "init", "-q", "-b", "main")
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", "fixture: initial commit")
    return dest


def _snapshot(root: Path) -> dict[str, str]:
    """Relative path -> content digest for every file outside ``.git``."""
    snap: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if ".git" in rel.parts or not path.is_file():
            continue
        snap[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def _is_under(path: Path, ancestor: Path) -> bool:
    return ancestor.resolve() in path.resolve().parents


def _worktree_count(repo: Path) -> int:
    listing = _git(repo, "worktree", "list", "--porcelain")
    return sum(1 for line in listing.splitlines() if line.startswith("worktree "))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path / "repo", "env_probe")


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    root = tmp_path / "scratch"
    root.mkdir()
    return root


# --- copy lifecycle (scenario .7) -------------------------------------------


def test_copy_exists_inside_and_is_removed_after_normal_exit(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7: the isolated copy directory is gone once the stage exits."""
    with isolated_copy(repo, scratch_root=scratch) as copy:
        assert isinstance(copy, IsolatedCopy)
        assert copy.root.is_dir()
        assert (copy.root / "tests" / "test_probe.py").is_file()
        kept = copy.root
    assert not kept.exists()
    assert list(scratch.iterdir()) == []


def test_copy_is_removed_when_the_body_raises(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7: a stage that raises midway still leaves no copy behind."""
    seen: list[Path] = []
    with (
        pytest.raises(RuntimeError, match="stage blew up"),
        isolated_copy(repo, scratch_root=scratch) as copy,
    ):
        seen.append(copy.root)
        assert copy.root.is_dir()
        raise RuntimeError("stage blew up")
    assert seen and not seen[0].exists()
    assert list(scratch.iterdir()) == []


def test_git_worktree_registration_is_pruned_after_exit(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7 / D3: no stale ``git worktree`` entry survives the stage."""
    with pytest.raises(RuntimeError), isolated_copy(repo, scratch_root=scratch):
        raise RuntimeError("boom")
    assert _worktree_count(repo) == 1
    with isolated_copy(repo, scratch_root=scratch):
        pass
    assert _worktree_count(repo) == 1


def test_default_scratch_location_is_cleaned_up(repo: Path, tmp_path: Path, monkeypatch) -> None:
    """test-oracle-audit.7: without ``scratch_root`` the copy lives in the system temp dir and is removed."""
    system_tmp = tmp_path / "systmp"
    system_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(system_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(system_tmp))
    with isolated_copy(repo) as copy:
        assert copy.root.is_dir()
        kept = copy.root
    assert not kept.exists()
    assert list(system_tmp.iterdir()) == []


def test_copy_works_for_a_directory_that_is_not_a_git_repository(tmp_path: Path, scratch: Path) -> None:
    """test-oracle-audit.7 / D3: the copytree fallback also produces and removes a copy."""
    plain = _make_repo(tmp_path / "plain", "env_probe", with_git=False)
    with isolated_copy(plain, scratch_root=scratch) as copy:
        assert (copy.root / "pytest.ini").is_file()
        kept = copy.root
    assert not kept.exists()
    assert list(scratch.iterdir()) == []


def test_two_live_copies_do_not_share_a_directory(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7: concurrent stages get distinct roots and distinct scratch dirs."""
    with isolated_copy(repo, scratch_root=scratch) as a, isolated_copy(repo, scratch_root=scratch) as b:
        assert a.root != b.root
        assert a.basetemp != b.basetemp
        assert a.env["HOME"] != b.env["HOME"]
    assert list(scratch.iterdir()) == []


# --- original tree untouched (scenario .6 / .7) -------------------------------


def test_edits_inside_the_copy_never_reach_the_original(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.6: the audited tree is byte-identical and git-clean after mutating the copy."""
    before = _snapshot(repo)
    assert _git(repo, "status", "--porcelain") == ""
    with isolated_copy(repo, scratch_root=scratch) as copy:
        probe = copy.root / "tests" / "test_probe.py"
        probe.write_text("raise SystemExit('mutated')\n")
        (copy.root / "new_file.txt").write_text("scratch")
        (copy.root / "pytest.ini").unlink()
    assert _snapshot(repo) == before
    assert _git(repo, "status", "--porcelain") == ""


def test_copy_starts_with_the_same_files_as_the_original(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.6: the copy is a faithful snapshot of the audited tree."""
    expected = _snapshot(repo)
    with isolated_copy(repo, scratch_root=scratch) as copy:
        assert _snapshot(copy.root) == expected


# --- environment redirection (D3) ---------------------------------------------


def test_environment_is_redirected_under_the_scratch_root(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7 / D3: HOME, TMPDIR, XDG_*, and basetemp live under scratch, beside the copy."""
    with isolated_copy(repo, scratch_root=scratch) as copy:
        assert copy.root.resolve() != repo.resolve()
        assert _is_under(copy.root, scratch)
        for key in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
            assert key in copy.env, key
            value = Path(copy.env[key])
            assert _is_under(value, scratch), f"{key}={value} is not under {scratch}"
            assert not _is_under(value, copy.root), f"{key} must sit beside the copy, not inside it"
        assert _is_under(copy.basetemp, scratch)
        assert not _is_under(copy.basetemp, copy.root)
        # The redirected home and temp dirs must be directories the audited tests can use.
        assert Path(copy.env["HOME"]).is_dir()
        assert Path(copy.env["TMPDIR"]).is_dir()


def test_env_values_are_strings(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7: ``env`` can be handed to ``subprocess`` as is."""
    with isolated_copy(repo, scratch_root=scratch) as copy:
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in copy.env.items())


def test_a_pytest_run_inside_the_copy_sees_the_redirected_environment(repo: Path, scratch: Path) -> None:
    """test-oracle-audit.7: HOME, TMPDIR and the pytest basetemp seen by a test are under scratch.

    The audited test writes a marker into ``~``. The marker must land in the redirected
    home, never in the real one, and nothing may be written into the original tree.
    """
    real_home = Path(os.environ.get("HOME", "/nonexistent")).resolve()
    real_marker = real_home / ".probe-marker"
    existed_before = real_marker.exists()
    before = _snapshot(repo)
    with isolated_copy(repo, scratch_root=scratch) as copy:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_probe.py",
                "-q",
                "-s",
                "-p",
                "no:cacheprovider",
                f"--basetemp={copy.basetemp}",
            ],
            check=False,
            cwd=copy.root,
            env={**os.environ, **copy.env},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        match = re.search(r"PROBE(\{.*\})", proc.stdout)
        assert match, proc.stdout
        report = json.loads(match.group(1))
        for label in ("home", "tmpdir", "xdg_cache_home", "tmp_path"):
            assert report[label] is not None, label
            assert _is_under(Path(report[label]), scratch), f"{label}={report[label]} not under {scratch}"
        assert (Path(report["home"]) / ".probe-marker").is_file()
    assert real_marker.exists() == existed_before
    assert _snapshot(repo) == before
    assert _git(repo, "status", "--porcelain") == ""
    assert list(scratch.iterdir()) == []
