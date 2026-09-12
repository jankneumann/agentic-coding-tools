"""Read-only posture tests for the audit-choices driver
(skills/audit-choices/scripts/run_audit.py). Design D6, D7.

Spec: skill-workflow.2 (Auditor writes only the ledger pair),
skill-workflow.6 (Adverse verdicts never block).
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / "skills"))

import run_audit  # noqa: E402
from shared.artifact_paths import DEFAULT_RETAIN  # noqa: E402


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

    def test_range_form_writes_confined_to_run_directory_and_latest(self, fixture_repo):
        """A standalone range audit's closed write set (D6): with fewer
        than the retained run count present, its working-tree diff is
        exactly the new run directory's pair plus latest.* — nothing
        deleted, nothing moved."""
        repo_root = fixture_repo["repo_root"]
        base_sha = fixture_repo["base_sha"]
        head_sha = fixture_repo["head_sha"]
        range_change_id = f"range:{base_sha}..{head_sha}"
        now = datetime(2026, 8, 21, tzinfo=timezone.utc)
        before = _snapshot(repo_root)

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id=range_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[_good_candidate(head_sha)],
            run_id="run-range-001",
            now=now,
            git_sha=head_sha,
        )
        assert result.ok is True

        after = _snapshot(repo_root)
        changed_or_new = {k for k in after if k not in before or after[k] != before[k]}

        run_dir = result.json_path.parent
        run_prefix = str(run_dir.relative_to(repo_root)) + "/"
        allowed = {
            run_prefix + "choices.json",
            run_prefix + "choices.md",
            "openspec/choices/latest.json",
            "openspec/choices/latest.md",
        }
        assert changed_or_new == allowed, f"unexpected writes: {changed_or_new - allowed}"

        # Nothing deleted or moved.
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


class TestRangeFormRetention:
    """Retention on the standalone-audit tree (design D3, D6, D8).

    This case needs a deletion-aware variant of `_snapshot`'s closure
    assertion: `TestWritesConfinedToLedgerPair` (above) keeps the strict
    `set(before.keys()) <= set(after.keys())` — no deletion — unchanged,
    because a retention archive move is out of scope for that case (fewer
    than the retained count of runs are present there). Here, over the
    limit, the archive `shutil.move` legitimately removes the oldest run's
    two files from their original keys, so this variant asserts an exact
    permitted-deleted set instead of relaxing the guarantee globally.
    """

    def test_over_limit_retention_archives_oldest_alongside_the_new_pair(self, fixture_repo):
        repo_root = fixture_repo["repo_root"]
        base_sha = fixture_repo["base_sha"]
        head_sha = fixture_repo["head_sha"]
        choices_root = repo_root / "openspec" / "choices"

        # DEFAULT_RETAIN pre-existing run directories, all dated well before
        # the new run below, so the new run is guaranteed to be the newest
        # and the very oldest of the pre-existing set is guaranteed to be
        # archived.
        oldest_run_id = "2020-01-01-000000-aaaaaaa"
        pre_existing = [oldest_run_id] + [
            f"2020-01-{i + 2:02d}-000000-{i:07x}" for i in range(DEFAULT_RETAIN - 1)
        ]
        for run_id in pre_existing:
            d = choices_root / run_id
            d.mkdir(parents=True)
            # Distinct per-run sentinels: identical stubs would let a
            # delete-and-recreate implementation satisfy the path-set
            # assertions below while destroying the pair the scenario
            # promises arrives "intact".
            (d / "choices.json").write_text('{"sentinel": "%s"}' % run_id)
            (d / "choices.md").write_text(f"sentinel {run_id}")

        before = _snapshot(repo_root)

        range_change_id = f"range:{base_sha}..{head_sha}"
        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id=range_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[_good_candidate(head_sha)],
            run_id="run-range-retention-001",
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha=head_sha,
        )
        assert result.ok is True

        after = _snapshot(repo_root)
        created_or_modified = {k for k in after if k not in before or after[k] != before[k]}
        deleted = {k for k in before if k not in after}

        run_dir = result.json_path.parent
        run_prefix = str(run_dir.relative_to(repo_root)) + "/"
        old_prefix = f"openspec/choices/{oldest_run_id}/"
        archived_prefix = f"openspec/choices/archive/{oldest_run_id}/"

        permitted_created = {
            run_prefix + "choices.json",
            run_prefix + "choices.md",
            "openspec/choices/latest.json",
            "openspec/choices/latest.md",
            archived_prefix + "choices.json",
            archived_prefix + "choices.md",
        }
        permitted_deleted = {
            old_prefix + "choices.json",
            old_prefix + "choices.md",
        }

        assert created_or_modified == permitted_created, (
            f"unexpected writes: {created_or_modified - permitted_created}"
        )
        assert deleted == permitted_deleted, f"unexpected deletions: {deleted - permitted_deleted}"

        # Scenario 14 says the archived pair arrives intact, and path-set
        # equality does not say that: an implementation that deleted the
        # active pair and wrote empty files at the archive paths would
        # satisfy every assertion above. Read the bytes back.
        archived_dir = choices_root / "archive" / oldest_run_id
        assert (
            archived_dir / "choices.json"
        ).read_text() == '{"sentinel": "%s"}' % oldest_run_id
        assert (
            archived_dir / "choices.md"
        ).read_text() == f"sentinel {oldest_run_id}"

    def test_retention_failure_does_not_fail_a_successful_run(self, fixture_repo, monkeypatch, caplog):
        def _raise(*args, **kwargs):
            raise OSError("boom: retention could not move the archive directory")

        monkeypatch.setattr(run_audit, "apply_retention", _raise)

        repo_root = fixture_repo["repo_root"]
        base_sha = fixture_repo["base_sha"]
        head_sha = fixture_repo["head_sha"]
        range_change_id = f"range:{base_sha}..{head_sha}"

        with caplog.at_level(logging.WARNING):
            result = run_audit.run_audit(
                repo_root=repo_root,
                change_id=range_change_id,
                base_sha=base_sha,
                head_sha=head_sha,
                candidates=[_good_candidate(head_sha)],
                run_id="run-range-retfail-001",
                now=datetime(2026, 8, 21, tzinfo=timezone.utc),
                git_sha=head_sha,
            )

        # The never-raises contract holds even when retention itself blows
        # up: a housekeeping failure must never masquerade as a write
        # failure (D8).
        assert result.ok is True
        assert result.json_path is not None
        assert result.md_path is not None
        assert result.json_path.exists()
        assert result.md_path.exists()

        # Without this assertion, an implementation that swallows the
        # failure silently would pass, and the operator would lose the
        # only signal that the standalone-audit tree has stopped being
        # bounded.
        retention_warnings = [
            r for r in caplog.records if "retention" in r.getMessage().lower()
        ]
        assert len(retention_warnings) == 1


class TestFailedRangeRunLeavesNoOrphanDirectory:
    """impl-round-2 (codex): reserving the run directory by creating it means
    a later failure can leave an empty directory behind — a fourth effect
    outside D6's closed write set, which `list_active_runs` then counts as a
    run that produced no ledger."""

    def test_write_failure_removes_the_reserved_directory(self, fixture_repo, monkeypatch):
        repo_root = fixture_repo["repo_root"]
        choices_root = repo_root / "openspec" / "choices"

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated write failure")

        monkeypatch.setattr(run_audit.choices_ledger, "write_ledger_pair", _boom)

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id=f"range:{fixture_repo['base_sha']}..{fixture_repo['head_sha']}",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[_good_candidate(fixture_repo["head_sha"])],
            run_id="run-orphan-001",
            now=datetime(2026, 8, 22, tzinfo=timezone.utc),
            git_sha=fixture_repo["head_sha"],
        )
        assert result.ok is False, "the driver still reports the failure"

        leftovers = sorted(p.name for p in choices_root.iterdir()) if choices_root.exists() else []
        assert leftovers == [], f"reserved directory left behind after a failed run: {leftovers}"


class TestChangeIdHeaderTimingMatchesMain:
    """impl-round-2 (codex): the range routing needs `now`/`git_sha`, and
    hoisting their resolution above `collect_evidence` changed *when* the
    change-id form captures them too. `main` resolves them immediately before
    building the header, and the change-id form is contracted byte-for-byte
    unchanged, so a slow evidence pass or a moving HEAD must not shift
    `generated_at`."""

    def test_generated_at_is_captured_after_evidence_collection(self, fixture_repo, monkeypatch):
        repo_root = fixture_repo["repo_root"]
        real_collect = run_audit.collect_evidence.collect_evidence
        observed: list[datetime] = []

        def slow_collect(*args, **kwargs):
            observed.append(datetime.now(timezone.utc))
            return real_collect(*args, **kwargs)

        monkeypatch.setattr(run_audit.collect_evidence, "collect_evidence", slow_collect)

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id="my-change",
            base_sha=fixture_repo["base_sha"],
            head_sha=fixture_repo["head_sha"],
            candidates=[_good_candidate(fixture_repo["head_sha"])],
            run_id="run-timing-001",
        )
        assert result.ok is True
        assert observed, "evidence collection did not run"

        doc = json.loads(result.json_path.read_text())
        generated_at = datetime.strptime(
            doc["header"]["generated_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        # Resolved after evidence collection, as on main. If it were hoisted
        # above, generated_at would predate the collection timestamp.
        assert generated_at >= observed[0].replace(microsecond=0), (
            "generated_at was captured before evidence collection; the "
            "change-id form's header timing changed"
        )
