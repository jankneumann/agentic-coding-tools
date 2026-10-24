"""Fixture-repository tests for explain-code's read-only why_trace script.

Change ids in the fixture repository are synthetic, so the OpenSpec
path-stability rule does not apply to them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "explain-code"
SCRIPT = SKILL_DIR / "scripts" / "why_trace.py"

PLAN_LOG = """# Session Log: demo-change

---

## Phase: Plan (2026-01-01)

**Agent**: test | **Session**: N/A

### Decisions
1. **Retry three times in app.py** `architectural: demo-cap` — the upstream drops one request in fifty
2. **Keep the default timeout** `architectural: demo-cap` — a shorter one tripped on cold starts
"""

OTHER_LOG = """# Session Log: other-demo-change

---

## Phase: Plan (2026-02-01)

**Agent**: test | **Session**: N/A

### Decisions
1. **Back off exponentially instead** `architectural: demo-cap` `supersedes: demo-change#plan/D1` — fixed retries amplified outages
"""

MERGED_LOG = """# Session Log: merged-change

---

## Phase: Plan (2026-03-01)

**Agent**: test | **Session**: N/A

### Decisions
1. **Log the fifth line** `architectural: demo-cap` — operators asked for it
"""


def _env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    })
    return env


def _git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
           "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args]
    proc = subprocess.run(cmd, cwd=repo, env=_env(repo.parent), capture_output=True,
                          text=True, check=True)
    return proc.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_line(repo: Path, text: str) -> None:
    app = repo / "src" / "app.py"
    app.write_text(app.read_text(encoding="utf-8") + text + "\n", encoding="utf-8")


def _commit(repo: Path, message: str, *paths: str) -> str:
    _git(repo, "add", "--", *paths)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    shas: dict = {"root": root}

    _write(root, "src/app.py", "a = 1\n")
    _write(root, "openspec/specs/demo-cap/spec.md", "# demo-cap\n")
    _write(root, "openspec/changes/merged-change/session-log.md", MERGED_LOG)
    shas["init"] = _commit(root, "chore: init", "src", "openspec")

    _append_line(root, "b = 2")
    shas["noid"] = _commit(root, "refactor: rename b", "src/app.py")

    _append_line(root, "retries = 3")
    _write(root, "openspec/changes/archive/2026-01-01-demo-change/session-log.md", PLAN_LOG)
    shas["traced"] = _commit(root, "feat(demo): add retry (#42)", "src/app.py", "openspec")

    _write(root, "openspec/changes/archive/2026-02-01-other-demo-change/session-log.md", OTHER_LOG)
    shas["other"] = _commit(root, "docs: record the backoff decision", "openspec")

    _append_line(root, "d = 4")
    _write(root, "openspec/changes/bare-change/proposal.md", "# bare\n")
    shas["bare"] = _commit(root, "feat: bare change", "src/app.py", "openspec")

    _git(root, "checkout", "-q", "-b", "feature")
    _append_line(root, "e = 5")
    shas["branch"] = _commit(root, "feat: add line five", "src/app.py")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "-m",
         "Merge pull request #77 from owner/openspec/merged-change", "feature")
    shas["merge"] = _git(root, "rev-parse", "HEAD")
    return shas


def _run(cwd: Path, *args: str, ceiling: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          env=_env(ceiling or cwd.parent), capture_output=True, text=True,
                          check=False)


def _trace(repo: dict, *args: str) -> dict:
    proc = _run(repo["root"], *args)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_full_chain_traced(repo):
    doc = _trace(repo, "src/app.py:3")
    assert doc["schema_version"] == 1
    assert doc["status"] == "traced"
    assert doc["null_result"] is None
    assert doc["target"] == {"path": "src/app.py", "line": 3, "symbol": None}
    assert doc["blame"]["sha"] == repo["traced"]
    assert doc["blame"]["pointer"] == f"git:{repo['traced']}"
    assert doc["commit"]["sha"] == repo["traced"]
    assert doc["commit"]["pointer"] == f"git:{repo['traced']}"
    assert doc["pr"]["number"] == 42
    assert doc["pr"]["source"] == "subject_suffix"
    assert doc["pr"]["pointer"] == f"git:{repo['traced']}"
    assert doc["pr_reason"] is None
    assert doc["change_ids"] == [{
        "change_id": "demo-change",
        "source": "commit_paths",
        "change_dir": "openspec/changes/archive/2026-01-01-demo-change",
    }]
    titles = [d["title"] for d in doc["decisions"]]
    assert titles == ["Retry three times in app.py", "Keep the default timeout"]
    d1 = doc["decisions"][0]
    assert d1["change_id"] == "demo-change"
    assert d1["capability"] == "demo-cap"
    assert d1["phase"] == "Plan"
    assert d1["date"] == "2026-01-01"
    assert d1["rationale"] == "the upstream drops one request in fifty"
    assert d1["pointer"] == (
        "openspec/changes/archive/2026-01-01-demo-change/session-log.md#plan/D1"
    )
    assert d1["index_path"] is None


def test_archive_match_is_exact(repo):
    """`-demo-change` must not resolve to `...-other-demo-change`."""
    doc = _trace(repo, "src/app.py:3")
    assert doc["change_ids"][0]["change_dir"].endswith("/2026-01-01-demo-change")


def test_superseded_decision_reported(repo):
    d1, d2 = _trace(repo, "src/app.py:3")["decisions"]
    assert d1["superseded_by"] == "other-demo-change#plan/D1"
    assert d2["superseded_by"] is None


def test_mentions_target_flag(repo):
    d1, d2 = _trace(repo, "src/app.py:3")["decisions"]
    assert d1["mentions_target"] is True  # names the basename app.py
    assert d2["mentions_target"] is False
    d1, d2 = _trace(repo, "src/app.py:3", "--symbol", "timeout")["decisions"]
    assert d2["mentions_target"] is True


NEAR_MISS_LOG = """# Session Log: near-miss-change

---

## Phase: Plan (2026-04-01)

**Agent**: test | **Session**: N/A

### Decisions
1. **Load myapp.py through lib/app.py** `architectural: demo-cap` — keeps app.pyc out of the bundle
"""


def test_mentions_target_ignores_near_miss_names(repo):
    root = repo["root"]
    _append_line(root, "f = 6")
    _write(root, "openspec/changes/near-miss-change/session-log.md", NEAR_MISS_LOG)
    _commit(root, "feat: near miss", "src/app.py", "openspec")
    (d,) = _trace(repo, "src/app.py:6")["decisions"]
    assert d["mentions_target"] is False  # myapp.py, lib/app.py, app.pyc are other files
    (d,) = _trace(repo, "src/app.py:6", "--symbol", "load")["decisions"]
    assert d["mentions_target"] is False  # case differs: Load
    (d,) = _trace(repo, "src/app.py:6", "--symbol", "Load")["decisions"]
    assert d["mentions_target"] is True


def test_mentions_target_symbol_is_whole_word(repo):
    d1, d2 = _trace(repo, "src/app.py:3", "--symbol", "time")["decisions"]
    assert d2["mentions_target"] is False  # "timeout" is not "time"
    d1, d2 = _trace(repo, "src/app.py:3", "--symbol", "default")["decisions"]
    assert d2["mentions_target"] is True


def test_index_path_reported_when_present(repo):
    _write(repo["root"], "docs/decisions/demo-cap.md", "# demo-cap\n")
    d1, _ = _trace(repo, "src/app.py:3")["decisions"]
    assert d1["index_path"] == "docs/decisions/demo-cap.md"


def test_no_change_id(repo):
    doc = _trace(repo, "src/app.py:2")
    assert doc["status"] == "no_change_id"
    assert doc["commit"]["sha"] == repo["noid"]
    assert doc["change_ids"] == []
    assert doc["decisions"] == []
    assert doc["pr"] is None and doc["pr_reason"]
    assert doc["null_result"]["reason"] == "no_change_id"
    assert doc["null_result"]["message"]


def test_no_decision_record(repo):
    doc = _trace(repo, "src/app.py:4")
    assert doc["status"] == "no_decision_record"
    assert doc["change_ids"][0]["change_id"] == "bare-change"
    assert doc["change_ids"][0]["change_dir"] == "openspec/changes/bare-change"
    assert doc["decisions"] == []
    assert doc["null_result"]["reason"] == "no_decision_record"
    assert doc["null_result"]["message"]


def test_no_decision_record_message_names_the_missing_session_log(repo):
    msg = _trace(repo, "src/app.py:4")["null_result"]["message"]
    assert "bare-change" in msg
    assert "no session-log.md" in msg
    assert "architectural:" not in msg  # nothing was parsed, so no bullet was missing


def test_no_decision_record_message_names_a_missing_change_dir(repo):
    root = repo["root"]
    _append_line(root, "f = 6")
    _write(root, "openspec/changes/gone-change/proposal.md", "# gone\n")
    _commit(root, "feat: gone change", "src/app.py", "openspec")
    _git(root, "rm", "-q", "-r", "openspec/changes/gone-change")
    _git(root, "commit", "-q", "-m", "chore: drop gone change")
    doc = _trace(repo, "src/app.py:6")
    assert doc["status"] == "no_decision_record"
    assert doc["change_ids"][0] == {
        "change_id": "gone-change", "source": "commit_paths", "change_dir": None,
    }
    assert "gone-change has no change directory" in doc["null_result"]["message"]


def test_change_id_from_commit_message(repo):
    root = repo["root"]
    _append_line(root, "f = 6")
    _commit(root, "feat: wire the logger for openspec/merged-change", "src/app.py")
    doc = _trace(repo, "src/app.py:6")
    assert doc["change_ids"] == [{
        "change_id": "merged-change",
        "source": "commit_message",
        "change_dir": "openspec/changes/merged-change",
    }]
    assert doc["status"] == "traced"


def test_openspec_file_mention_is_not_a_change_id(repo):
    """`openspec/config.yaml` is a file, not a change named `config`."""
    root = repo["root"]
    _append_line(root, "f = 6")
    _write(root, "openspec/config.yaml", "schema: x\n")
    _commit(root, "chore: tune openspec/config.yaml", "src/app.py", "openspec/config.yaml")
    doc = _trace(repo, "src/app.py:6")
    assert doc["change_ids"] == []
    assert doc["status"] == "no_change_id"


def test_shallow_clone_boundary_is_history_truncated(repo, tmp_path):
    """A depth-1 clone's only commit stands in for all history; never trace it."""
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo['root']}", str(shallow))
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    for target in ("src/app.py:1", "src/app.py:3", "src/app.py:5"):
        proc = _run(shallow, target)
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert doc["status"] == "history_truncated", (target, doc["status"])
        assert doc["blame"]["sha"] == repo["merge"]
        assert doc["commit"] is None
        assert doc["pr"] is None
        assert doc["change_ids"] == []
        assert doc["decisions"] == []
        assert doc["null_result"]["reason"] == "history_truncated"
        assert repo["merge"] in doc["null_result"]["message"]
        assert "shallow" in doc["null_result"]["message"]


def test_root_commit_in_full_history_is_still_traced(repo):
    """git also marks a real root commit `boundary`; that one did introduce the line."""
    doc = _trace(repo, "src/app.py:1")
    assert doc["blame"]["sha"] == repo["init"]
    assert doc["status"] == "traced"
    assert doc["change_ids"][0]["change_id"] == "merged-change"


def test_pr_and_change_id_from_merge_commit(repo):
    doc = _trace(repo, "src/app.py:5")
    assert doc["commit"]["sha"] == repo["branch"]
    assert doc["pr"]["number"] == 77
    assert doc["pr"]["source"] == "merge_commit"
    assert doc["pr"]["sha"] == repo["merge"]
    assert doc["change_ids"] == [{
        "change_id": "merged-change",
        "source": "pr_merge_message",
        "change_dir": "openspec/changes/merged-change",
    }]
    assert doc["status"] == "traced"
    assert doc["decisions"][0]["title"] == "Log the fifth line"


def test_uncommitted_line(repo):
    _append_line(repo["root"], "f = 6")
    doc = _trace(repo, "src/app.py:6")
    assert doc["status"] == "uncommitted"
    assert doc["commit"] is None
    assert doc["decisions"] == []
    assert doc["null_result"]["reason"] == "uncommitted"


def test_uncommitted_line_on_unborn_head(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, "f.py", "x = 1\n")
    _git(root, "add", "f.py")
    proc = _run(root, "f.py:1")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["status"] == "uncommitted"
    assert doc["commit"] is None
    assert doc["null_result"]["reason"] == "uncommitted"


def test_unreadable_target_is_an_input_error(repo, monkeypatch, capsys):
    import importlib.util

    # Importing the script flips process-wide flags; undo them after the test.
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location("why_trace_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _deny(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(module.Path, "read_bytes", _deny)
    monkeypatch.chdir(repo["root"])
    for key, value in _env(repo["root"].parent).items():
        monkeypatch.setenv(key, value)
    assert module.main(["src/app.py:1"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "cannot read src/app.py" in captured.err


@pytest.mark.parametrize("target", ["src/app.py", "src/app.py:0", "src/app.py:x", ":3"])
def test_malformed_target_rejected(repo, target):
    proc = _run(repo["root"], target)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert len(proc.stderr.strip().splitlines()) == 1


def test_untracked_path_rejected(repo):
    _write(repo["root"], "src/untracked.py", "x = 1\n")
    proc = _run(repo["root"], "src/untracked.py:1")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert len(proc.stderr.strip().splitlines()) == 1


def test_line_out_of_range_rejected(repo):
    proc = _run(repo["root"], "src/app.py:99")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert len(proc.stderr.strip().splitlines()) == 1


def test_outside_a_repository_is_a_git_failure(tmp_path):
    outside = tmp_path / "plain"
    outside.mkdir()
    (outside / "f.py").write_text("x = 1\n", encoding="utf-8")
    proc = _run(outside, "f.py:1")
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_relative_to_cwd(repo):
    proc = _run(repo["root"] / "src", "app.py:3", ceiling=repo["root"].parent)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["target"]["path"] == "src/app.py"


def _snapshot(root: Path) -> tuple:
    files = sorted(
        str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.parts
    )
    git_files = sorted(
        str(p.relative_to(root / ".git")) for p in (root / ".git").rglob("*") if p.is_file()
    )
    return (
        _git(root, "status", "--porcelain"),
        _git(root, "for-each-ref"),
        (root / ".git" / "index").read_bytes(),
        files,
        git_files,
    )


def _sibling_bytecode() -> list:
    cache = SKILL_DIR.parent / "explore-feature" / "scripts" / "__pycache__"
    return sorted((p.name, p.stat().st_mtime_ns) for p in cache.glob("*")) if cache.is_dir() else []


def test_no_side_effects(repo):
    root = repo["root"]
    before = _snapshot(root)
    bytecode_before = _sibling_bytecode()
    for target in ("src/app.py:1", "src/app.py:2", "src/app.py:3", "src/app.py:4",
                   "src/app.py:5", "src/app.py:99"):
        _run(root, target)
    assert _snapshot(root) == before
    assert _sibling_bytecode() == bytecode_before


def test_output_is_deterministic(repo):
    first = _run(repo["root"], "src/app.py:3").stdout
    second = _run(repo["root"], "src/app.py:3").stdout
    assert first == second
    assert first.endswith("}\n")


def test_reuses_decision_index_instead_of_parsing():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "extract_decisions" in source
    assert "_build_supersession_map" in source
    assert "architectural:\\s" not in source  # no second Decision-bullet regex
    assert "## Phase" not in source
    assert "<skill-base-dir>/../explore-feature/scripts" in source
    assert "sys.dont_write_bytecode = True" in source
