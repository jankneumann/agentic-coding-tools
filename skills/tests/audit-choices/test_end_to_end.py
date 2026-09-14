"""End-to-end pins for the audit-choices driver against archived-change
fixture data (task 3.6, design F5/F6).

Builds a synthetic git repo seeded from the archived parent change's own
artifacts (`proposal.md`, `design.md`, `session-log.md` — "archived-change
fixture" means archived artifacts as fixture data, per F5) under a
**synthetic** change id, `fixture-decision-choices-ledger` — never the real
`add-decision-choices-ledger` id, which would re-encode the archival
coupling `openspec_paths.change_dir` exists to remove. One base commit and
one implementing commit; a canned candidate set with one `sound`, one
`unsound`, one `needs-user`, and one whose `choice` headline matches a
session-log `Decisions` bullet verbatim (so `self_reported` resolves both
ways).

Covers scenarios: skill-workflow.1 (schema-valid pair, six-field header),
.3 (auditor writes only the ledger pair), .4 (adverse verdicts never
block), .5 (unreported decision is flagged / self_reported both ways), .6
(re-audit is idempotent), .7 (rendering enforces the ranking invariant),
and the reader half of .11 (needs_user.py). Also drives the driver
standalone against `change_id=f"range:{base}..{head}"`, the executable
half of .12 — this does **not** show that a `<base>..<head>` argument
resolves to that form (that is an agent instruction in
`audit-choices/SKILL.md` Step 1, pinned as a content assertion by 3.7).

Deliberately not covered here: skill-workflow.2 ("Missing ledger does not
block archive") is validation/archive behavior, not driver behavior, and
stays with the parent's own coverage. skill-workflow.8 is
`iterate-on-implementation` behavior and belongs to 3.1 + 3.7.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from openspec_paths import change_dir, repo_root_from

REAL_REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS_DIR = REAL_REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import choices_ledger  # noqa: E402
import choices_paths  # noqa: E402
import needs_user  # noqa: E402
import run_audit  # noqa: E402

FIXTURE_CHANGE_ID = "fixture-decision-choices-ledger"
# Verbatim title of a Decisions bullet in the archived parent's
# session-log.md (Cleanup phase) — copied into the fixture repo below, so a
# candidate reusing this exact headline is guaranteed to resolve
# self_reported=True via collect_evidence.resolve_self_reported's keyword
# overlap.
SELF_REPORTED_CHOICE = "Rebase-merge rather than squash"


# ─────────────────────────────────────────────────────────────────────────
# Git helpers (pattern of test_readonly_posture.fixture_repo)
# ─────────────────────────────────────────────────────────────────────────


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), *args], check=True, capture_output=True, text=True)


def _rev_parse(repo_root: Path, rev: str = "HEAD") -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", rev], capture_output=True, text=True, check=True
    ).stdout.strip()


def _snapshot(repo_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in repo_root.rglob("*"):
        if path.is_dir() or ".git" in path.parts:
            continue
        out[str(path.relative_to(repo_root))] = path.read_bytes().hex()
    return out


# ─────────────────────────────────────────────────────────────────────────
# Fixture repo: seeded from the archived parent change's own artifacts
# ─────────────────────────────────────────────────────────────────────────


def _build_fixture_repo(tmp_path: Path) -> dict[str, object]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "a@b.c")
    _git(repo_root, "config", "user.name", "Test")

    # F5: archived artifacts as fixture data, copied under a synthetic
    # change id — resolved via change_dir so this test survives a future
    # re-archival of the source change.
    archived_dir = change_dir(REAL_REPO_ROOT, "add-decision-choices-ledger")
    fixture_change_dir = repo_root / "openspec" / "changes" / FIXTURE_CHANGE_ID
    fixture_change_dir.mkdir(parents=True)
    for name in ("proposal.md", "design.md", "session-log.md"):
        src = archived_dir / name
        assert src.exists(), f"expected archived fixture source at {src}"
        (fixture_change_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-q", "-m", "base")
    base_sha = _rev_parse(repo_root)

    target_file = repo_root / "skills" / "example" / "client.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("x = 1\n")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-q", "-m", "implement the thing")
    head_sha = _rev_parse(repo_root)

    return {"repo_root": repo_root, "base_sha": base_sha, "head_sha": head_sha}


def _candidate(
    choice: str, verdict: str, confidence: str, head_sha: str
) -> dict[str, object]:
    return {
        "choice": choice,
        "scenario": f"WHEN the implementation ran THEN {choice[0].lower()}{choice[1:]} happened.",
        "gap": f"The design left {choice[0].lower()}{choice[1:]} unspecified.",
        "reach": "Future implementers inherit this choice.",
        "verdict": verdict,
        "verdict_rationale": "The diff and evidence bundle support this verdict.",
        "confidence": confidence,
        "provenance": {"commits": [head_sha], "files": ["skills/example/client.py"]},
    }


def _candidate_set(head_sha: str) -> list[dict[str, object]]:
    return [
        _candidate(
            "Chose to surface unresolved retry semantics for human review",
            "needs-user",
            "low",
            head_sha,
        ),
        _candidate(
            "Chose a blocking synchronous call on the hot path",
            "unsound",
            "medium",
            head_sha,
        ),
        # Verdict/confidence chosen so its rank-tie with the unsound entry
        # above exercises the verdict tie-break (needs-user < unsound <
        # sound) at equal confidence — see test_choices_md_rendering_order.
        _candidate(SELF_REPORTED_CHOICE, "sound", "medium", head_sha),
        _candidate(
            "Chose to leave the range ledger location as a documented follow-up",
            "sound",
            "high",
            head_sha,
        ),
    ]


@pytest.fixture()
def audited_fixture(tmp_path):
    built = _build_fixture_repo(tmp_path)
    candidates = _candidate_set(built["head_sha"])
    before_snapshot = _snapshot(built["repo_root"])

    result = run_audit.run_audit(
        repo_root=built["repo_root"],
        change_id=FIXTURE_CHANGE_ID,
        base_sha=built["base_sha"],
        head_sha=built["head_sha"],
        candidates=candidates,
        run_id="run-001",
        now=datetime(2026, 9, 11, tzinfo=timezone.utc),
        git_sha=built["head_sha"],
    )
    return {
        **built,
        "candidates": candidates,
        "before_snapshot": before_snapshot,
        "result": result,
        "change_dir": built["repo_root"] / "openspec" / "changes" / FIXTURE_CHANGE_ID,
    }


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.1 — schema-valid pair, six-field header
# ─────────────────────────────────────────────────────────────────────────


class TestSchemaValidPair:
    def test_ledger_json_is_schema_valid_with_six_field_header(self, audited_fixture):
        doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        choices_ledger.validate_document(doc)
        assert set(doc["header"].keys()) == {
            "schema_version",
            "generated_at",
            "git_sha",
            "generator",
            "run_id",
            "event_kind",
        }

    def test_ledger_md_exists_and_nonempty(self, audited_fixture):
        md_path = audited_fixture["change_dir"] / "choices.md"
        assert md_path.exists()
        assert md_path.read_text().strip() != ""


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.3 — auditor writes only the ledger pair
# ─────────────────────────────────────────────────────────────────────────


class TestWritesConfinedToLedgerPair:
    def test_working_tree_diff_is_exactly_the_pair(self, audited_fixture):
        after = _snapshot(audited_fixture["repo_root"])
        before = audited_fixture["before_snapshot"]
        changed_or_new = {k for k in after if k not in before or after[k] != before[k]}
        prefix = f"openspec/changes/{FIXTURE_CHANGE_ID}/"
        allowed = {prefix + "choices.json", prefix + "choices.md"}
        assert changed_or_new == allowed, f"unexpected writes: {changed_or_new - allowed}"
        assert set(before.keys()) <= set(after.keys())


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.4 — adverse verdicts never block
# ─────────────────────────────────────────────────────────────────────────


class TestAdverseVerdictsNeverBlock:
    def test_ok_true_with_unsound_and_needs_user_present(self, audited_fixture):
        result = audited_fixture["result"]
        assert result.ok is True
        doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        verdicts = {e["verdict"] for e in doc["entries"]}
        assert {"unsound", "needs-user"} <= verdicts
        assert len(doc["entries"]) == 4


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.5 — unreported decision is flagged; self_reported both ways
# ─────────────────────────────────────────────────────────────────────────


class TestSelfReportedResolvesBothWays:
    def test_matching_candidate_is_self_reported_true(self, audited_fixture):
        doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        by_choice = {e["choice"]: e for e in doc["entries"]}
        assert by_choice[SELF_REPORTED_CHOICE]["self_reported"] is True
        assert "session_log_ref" in by_choice[SELF_REPORTED_CHOICE]
        assert by_choice[SELF_REPORTED_CHOICE]["session_log_ref"].startswith(
            FIXTURE_CHANGE_ID + "#"
        )

    def test_unmatched_candidates_are_self_reported_false(self, audited_fixture):
        doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        by_choice = {e["choice"]: e for e in doc["entries"]}
        unreported = by_choice["Chose a blocking synchronous call on the hot path"]
        assert unreported["self_reported"] is False
        assert "session_log_ref" not in unreported


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.6 — re-audit is idempotent
# ─────────────────────────────────────────────────────────────────────────


class TestReAuditIsIdempotent:
    def test_second_run_keeps_stable_ids_and_count(self, audited_fixture):
        first_doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        first_ids = {e["stable_id"] for e in first_doc["entries"]}
        assert len(first_ids) == 4

        second_result = run_audit.run_audit(
            repo_root=audited_fixture["repo_root"],
            change_id=FIXTURE_CHANGE_ID,
            base_sha=audited_fixture["base_sha"],
            head_sha=audited_fixture["head_sha"],
            candidates=audited_fixture["candidates"],
            run_id="run-002",
            now=datetime(2026, 9, 12, tzinfo=timezone.utc),
            git_sha=audited_fixture["head_sha"],
        )
        assert second_result.ok is True

        second_doc = json.loads((audited_fixture["change_dir"] / "choices.json").read_text())
        second_ids = {e["stable_id"] for e in second_doc["entries"]}
        assert second_ids == first_ids
        assert len(second_doc["entries"]) == 4


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.7 — rendering enforces the ranking invariant
# ─────────────────────────────────────────────────────────────────────────


class TestChoicesMdRenderingOrder:
    def test_entries_render_least_confident_first(self, audited_fixture):
        text = (audited_fixture["change_dir"] / "choices.md").read_text()
        headings = [line[len("### ") :] for line in text.splitlines() if line.startswith("### ")]
        # low, then medium (needs-user < unsound < sound tie-break), then high.
        expected = [
            "Chose to surface unresolved retry semantics for human review",
            "Chose a blocking synchronous call on the hot path",
            SELF_REPORTED_CHOICE,
            "Chose to leave the range ledger location as a documented follow-up",
        ]
        assert headings == expected


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.11 — reader half: needs_user.py
# ─────────────────────────────────────────────────────────────────────────


class TestNeedsUserReaderIntegration:
    def test_lists_exactly_the_needs_user_entry(self, audited_fixture, capsys):
        exit_code = needs_user.main(
            [
                "--change-id",
                FIXTURE_CHANGE_ID,
                "--repo-root",
                str(audited_fixture["repo_root"]),
                "--format",
                "text",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        lines = out.splitlines()
        assert len(lines) == 1
        assert "Chose to surface unresolved retry semantics for human review" in lines[0]

    def test_no_ledger_is_silent_text_and_empty_array_json(self, audited_fixture, capsys):
        exit_code = needs_user.main(
            [
                "--change-id",
                "fixture-no-such-change",
                "--repo-root",
                str(audited_fixture["repo_root"]),
                "--format",
                "text",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert out == ""

        exit_code = needs_user.main(
            [
                "--change-id",
                "fixture-no-such-change",
                "--repo-root",
                str(audited_fixture["repo_root"]),
                "--format",
                "json",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert json.loads(out) == []

    def test_ledger_with_nothing_open_is_silent_text_and_empty_array_json(
        self, audited_fixture, capsys
    ):
        # A second, independent audit against the same commit range, seeded
        # with only sound/unsound candidates — a ledger that exists but has
        # no needs-user entries, the second of F3's two empty cases.
        clean_change_id = "fixture-decision-choices-ledger-clean"
        candidates = [
            _candidate("Chose a documented default timeout", "sound", "high", audited_fixture["head_sha"]),
            _candidate("Chose to log instead of retry", "unsound", "high", audited_fixture["head_sha"]),
        ]
        clean_result = run_audit.run_audit(
            repo_root=audited_fixture["repo_root"],
            change_id=clean_change_id,
            base_sha=audited_fixture["base_sha"],
            head_sha=audited_fixture["head_sha"],
            candidates=candidates,
            run_id="run-clean-001",
            now=datetime(2026, 9, 11, tzinfo=timezone.utc),
            git_sha=audited_fixture["head_sha"],
        )
        assert clean_result.ok is True

        exit_code = needs_user.main(
            [
                "--change-id",
                clean_change_id,
                "--repo-root",
                str(audited_fixture["repo_root"]),
                "--format",
                "text",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert out == ""

        exit_code = needs_user.main(
            [
                "--change-id",
                clean_change_id,
                "--repo-root",
                str(audited_fixture["repo_root"]),
                "--format",
                "json",
            ]
        )
        out = capsys.readouterr().out
        assert exit_code == 0
        assert json.loads(out) == []


# ─────────────────────────────────────────────────────────────────────────
# skill-workflow.12 — executable half: standalone range invocation
# ─────────────────────────────────────────────────────────────────────────


class TestStandaloneRangeInvocation:
    def test_cli_exit_code_and_no_range_directory_under_changes(
        self, audited_fixture, monkeypatch
    ):
        """One case kept on `_cli()` for the exit-code contract. `_cli()`
        passes neither `now` nor `git_sha`, so it can't know the run id it
        produced (task 4.3) -- the location/content assertions below use
        `run_audit.run_audit()` directly with explicit `now`/`git_sha`
        instead, the pattern `test_readonly_posture.py` already uses."""
        repo_root = audited_fixture["repo_root"]
        base_sha = audited_fixture["base_sha"]
        head_sha = audited_fixture["head_sha"]
        range_change_id = f"range:{base_sha}..{head_sha}"

        candidates_path = repo_root / "range-candidates-cli.json"
        candidates_path.write_text(
            json.dumps([_candidate("Chose a range default via CLI", "sound", "high", head_sha)])
        )

        argv = [
            "run_audit.py",
            "--change-id",
            range_change_id,
            "--base-sha",
            base_sha,
            "--head-sha",
            head_sha,
            "--run-id",
            "run-range-cli-001",
            "--candidates",
            str(candidates_path),
            "--repo-root",
            str(repo_root),
        ]
        monkeypatch.setattr(sys, "argv", argv)
        exit_code = run_audit._cli()
        assert exit_code == 0

        # Both assertions above and below hold vacuously for a run that did
        # nothing at all — `_cli()` returns 0 whatever happens (the
        # never-blocks contract) and a failed run writes no directory. So
        # assert the positive first: the run actually produced its pair.
        # impl-round-3 and VAL_REVIEW both flagged this case as nominal
        # without it.
        choices_root = repo_root / "openspec" / "choices"
        runs = [d for d in choices_root.iterdir() if d.is_dir() and d.name != "archive"]
        assert len(runs) == 1, f"expected exactly one run directory, got {runs}"
        assert (runs[0] / "choices.json").is_file()
        assert (runs[0] / "choices.md").is_file()

        # This change's whole purpose: no directory named after the commit
        # range exists anywhere under openspec/changes/.
        changes_dir = repo_root / "openspec" / "changes"
        for entry in changes_dir.iterdir():
            assert "range:" not in entry.name
            assert ".." not in entry.name

    def test_range_run_writes_under_choices_root_with_latest_copies(self, audited_fixture):
        repo_root = audited_fixture["repo_root"]
        base_sha = audited_fixture["base_sha"]
        head_sha = audited_fixture["head_sha"]
        range_change_id = f"range:{base_sha}..{head_sha}"
        now = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id=range_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[_candidate("Chose a range default", "sound", "high", head_sha)],
            run_id="run-range-002",
            now=now,
            git_sha=head_sha,
        )
        assert result.ok is True

        # Locate by globbing <run-id>* rather than by exact name: a
        # collision would place the run at a -2 sibling whose suffix no
        # header field records (D7/D8).
        expected_base_run_id = choices_paths.build_run_id(now, head_sha)
        choices_root = repo_root / "openspec" / "choices"
        matches = sorted(choices_root.glob(f"{expected_base_run_id}*"))
        assert len(matches) == 1, f"expected exactly one run directory, got {matches}"
        run_dir = matches[0]

        assert result.json_path == run_dir / "choices.json"
        assert result.md_path == run_dir / "choices.md"

        doc = json.loads((run_dir / "choices.json").read_text())
        assert doc["change_id"] == range_change_id
        assert doc["audited_range"] == {"base_sha": base_sha, "head_sha": head_sha}
        # audited_range carries both full 40-character shas.
        assert len(doc["audited_range"]["base_sha"]) == 40
        assert len(doc["audited_range"]["head_sha"]) == 40

        # latest.json / latest.md are byte-equal copies of this run's pair (D6).
        assert (choices_root / "latest.json").read_bytes() == (run_dir / "choices.json").read_bytes()
        assert (choices_root / "latest.md").read_bytes() == (run_dir / "choices.md").read_bytes()

        # No directory whose name contains "range:" or ".." exists anywhere
        # under openspec/changes/.
        changes_dir = repo_root / "openspec" / "changes"
        for entry in changes_dir.iterdir():
            assert "range:" not in entry.name
            assert ".." not in entry.name

    def test_second_range_run_creates_new_directory_and_preserves_first(self, audited_fixture):
        """D8: a range ledger is a per-run snapshot. Through `_cli()` the
        caller cannot choose `now`, and back-to-back runs land in the same
        UTC second, which would exercise the collision guard rather than
        this distinct-snapshot case -- so this drives `run_audit()` directly
        with two distinct `now` values, same as the pattern above."""
        repo_root = audited_fixture["repo_root"]
        base_sha = audited_fixture["base_sha"]
        head_sha = audited_fixture["head_sha"]
        range_change_id = f"range:{base_sha}..{head_sha}"
        candidate = _candidate("Chose a range default for the snapshot test", "sound", "high", head_sha)

        now1 = datetime(2026, 9, 12, 5, 0, 0, tzinfo=timezone.utc)
        now2 = datetime(2026, 9, 12, 6, 0, 0, tzinfo=timezone.utc)

        result1 = run_audit.run_audit(
            repo_root=repo_root,
            change_id=range_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[candidate],
            run_id="run-range-003a",
            now=now1,
            git_sha=head_sha,
        )
        assert result1.ok is True
        run_dir1 = result1.json_path.parent
        doc1_before_second_run = (run_dir1 / "choices.json").read_bytes()

        result2 = run_audit.run_audit(
            repo_root=repo_root,
            change_id=range_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[candidate],
            run_id="run-range-003b",
            now=now2,
            git_sha=head_sha,
        )
        assert result2.ok is True
        run_dir2 = result2.json_path.parent

        # A second directory, distinct from the first.
        assert run_dir1 != run_dir2
        # The first run is byte-unchanged after the second.
        assert (run_dir1 / "choices.json").read_bytes() == doc1_before_second_run

        # Same decision content -> the same stable_id in both snapshots.
        doc1 = json.loads((run_dir1 / "choices.json").read_text())
        doc2 = json.loads((run_dir2 / "choices.json").read_text())
        ids1 = {e["stable_id"] for e in doc1["entries"]}
        ids2 = {e["stable_id"] for e in doc2["entries"]}
        assert ids1 == ids2

        # latest.* now mirrors the second run, not the first.
        choices_root = repo_root / "openspec" / "choices"
        assert (choices_root / "latest.json").read_bytes() == (run_dir2 / "choices.json").read_bytes()
        assert (choices_root / "latest.md").read_bytes() == (run_dir2 / "choices.md").read_bytes()

    def test_change_id_run_in_same_fixture_still_writes_to_changes_tree(self, audited_fixture):
        repo_root = audited_fixture["repo_root"]
        base_sha = audited_fixture["base_sha"]
        head_sha = audited_fixture["head_sha"]
        other_change_id = "another-change-in-the-same-repo"

        result = run_audit.run_audit(
            repo_root=repo_root,
            change_id=other_change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=[_candidate("Chose an ordinary change-id destination", "sound", "high", head_sha)],
            run_id="run-other-001",
            now=datetime(2026, 9, 12, 7, 0, 0, tzinfo=timezone.utc),
            git_sha=head_sha,
        )
        assert result.ok is True
        assert (repo_root / "openspec" / "changes" / other_change_id / "choices.json").exists()
        assert not (repo_root / "openspec" / "choices").exists()
