"""Read-only posture tests for the audit-choices driver
(skills/audit-choices/scripts/run_audit.py). Design D6, D7.

Spec: skill-workflow.2 (Auditor writes only the ledger pair),
skill-workflow.6 (Adverse verdicts never block).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_audit  # noqa: E402


def _git(repo_root, *args):
    subprocess.run(["git", "-C", str(repo_root), *args], check=True, capture_output=True, text=True)


def _rev_parse(repo_root, rev="HEAD"):
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", rev], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def fixture_repo(tmp_path):
    """A minimal git repo with an openspec change directory and one commit
    touching one file, so provenance can reference something real."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "a@b.c")
    _git(repo_root, "config", "user.name", "Test")

    change_dir = repo_root / "openspec" / "changes" / "my-change"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text("# Proposal\n\nDo the thing.\n")
    (repo_root / "README.md").write_text("hello\n")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-q", "-m", "base")
    base_sha = _rev_parse(repo_root)

    target_file = repo_root / "skills" / "example" / "client.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("x = 1\n")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-q", "-m", "implement the thing")
    head_sha = _rev_parse(repo_root)

    return {
        "repo_root": repo_root,
        "change_dir": change_dir,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def _snapshot(repo_root: Path) -> dict[str, str]:
    """Map of every tracked-or-untracked file (excluding .git) to its content."""
    out: dict[str, str] = {}
    for path in repo_root.rglob("*"):
        if path.is_dir() or ".git" in path.parts:
            continue
        out[str(path.relative_to(repo_root))] = path.read_bytes().hex()
    return out


def _good_candidate(head_sha, choice="Chose per-request retry budget of 3"):
    return {
        "choice": choice,
        "scenario": "WHEN a downstream call times out THEN the client retries up to 3 times.",
        "gap": "The design left retry policy unspecified.",
        "reach": "Future callers inherit a 3-retry default.",
        "verdict": "sound",
        "verdict_rationale": "Matches conservative defaults used elsewhere.",
        "confidence": "medium",
        "provenance": {"commits": [head_sha], "files": ["skills/example/client.py"]},
    }


class TestWritesConfinedToLedgerPair:
    def test_writes_confined_to_ledger_pair(self, fixture_repo):
        repo_root = fixture_repo["repo_root"]
        before = _snapshot(repo_root)

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[_good_candidate(fixture_repo["head_sha"])],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is True

        after = _snapshot(repo_root)
        changed_or_new = {
            k for k in after if k not in before or after[k] != before[k]
        }
        change_prefix = "openspec/changes/my-change/"
        allowed = {change_prefix + "choices.json", change_prefix + "choices.md"}
        assert changed_or_new == allowed, f"unexpected writes: {changed_or_new - allowed}"

        # And nothing was deleted either.
        assert set(before.keys()) <= set(after.keys())


class TestNeverBlocks:
    def test_exit_zero_on_adverse_verdicts(self, fixture_repo, capsys):
        adverse = dict(_good_candidate(fixture_repo["head_sha"]))
        adverse["verdict"] = "unsound"
        adverse["choice"] = "Adverse unsound choice"
        needs_user = dict(_good_candidate(fixture_repo["head_sha"]))
        needs_user["verdict"] = "needs-user"
        needs_user["choice"] = "Adverse needs-user choice"

        result = run_audit.run_audit(
            repo_root=fixture_repo["repo_root"],
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[adverse, needs_user],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is True
        assert result.kept_count == 2
        doc = json.loads((fixture_repo["change_dir"] / "choices.json").read_text())
        verdicts = {e["verdict"] for e in doc["entries"]}
        assert verdicts == {"unsound", "needs-user"}

    def test_exit_zero_on_internal_error(self, fixture_repo):
        result = run_audit.run_audit(
            repo_root=Path("/nonexistent/definitely-not-a-repo"),
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[_good_candidate(fixture_repo["head_sha"])],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is False
        assert result.error

    def test_cli_always_returns_0(self, fixture_repo, monkeypatch, capsys):
        candidates_path = fixture_repo["repo_root"] / "candidates.json"
        candidates_path.write_text(json.dumps([_good_candidate(fixture_repo["head_sha"])]))
        argv = [
            "run_audit.py",
            "--change-id", "my-change",
            "--base-sha", fixture_repo["base_sha"],
            "--head-sha", fixture_repo["head_sha"],
            "--run-id", "run-001",
            "--candidates", str(candidates_path),
            "--repo-root", str(fixture_repo["repo_root"]),
        ]
        monkeypatch.setattr(sys, "argv", argv)
        exit_code = run_audit._cli()
        assert exit_code == 0


class TestHallucinationGuard:
    def test_entry_citing_commit_outside_range_is_dropped(self, fixture_repo):
        fake_commit = "f" * 40
        bad = _good_candidate(fixture_repo["head_sha"])
        bad["provenance"] = {"commits": [fake_commit], "files": ["skills/example/client.py"]}
        bad["choice"] = "Choice citing a nonexistent commit"

        result = run_audit.run_audit(
            repo_root=fixture_repo["repo_root"],
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[bad],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is True
        assert result.kept_count == 0
        assert result.dropped_count == 1

    def test_entry_citing_file_outside_range_is_dropped(self, fixture_repo):
        bad = _good_candidate(fixture_repo["head_sha"])
        bad["provenance"] = {
            "commits": [fixture_repo["head_sha"]],
            "files": ["skills/nonexistent/not-touched.py"],
        }
        bad["choice"] = "Choice citing a nonexistent file"

        result = run_audit.run_audit(
            repo_root=fixture_repo["repo_root"],
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[bad],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is True
        assert result.kept_count == 0
        assert result.dropped_count == 1

    def test_valid_entry_is_kept_alongside_dropped_one(self, fixture_repo):
        good = _good_candidate(fixture_repo["head_sha"], choice="A valid choice")
        bad = _good_candidate(fixture_repo["head_sha"])
        bad["provenance"] = {"commits": ["f" * 40], "files": ["skills/example/client.py"]}
        bad["choice"] = "A hallucinated choice"

        result = run_audit.run_audit(
            repo_root=fixture_repo["repo_root"],
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[good, bad],
            run_id="run-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is True
        assert result.kept_count == 1
        assert result.dropped_count == 1
        doc = json.loads((fixture_repo["change_dir"] / "choices.json").read_text())
        assert doc["entries"][0]["choice"] == "A valid choice"
