"""Characterization test for prioritize-proposals output (task 1.1, D4).

Pins the current on-disk output of `priorities_paths.py` / `retention.py`
BEFORE the shared-helper migration (task 3.1) moves `build_run_id`,
`RUN_ID_RE`, `parse_run_id`, `apply_retention`, `list_active_runs`,
`RetentionResult`, and `ARCHIVE_DIRNAME` into `skills/shared/artifact_paths.py`.

This test MUST pass unchanged before and after that migration. If it fails
after, the migration changed behavior and the code must be corrected —
never this test (design.md D4).

Three parts (D4):
  1. Function-level pins on `build_run_id` / `build_paths` / `parse_run_id` /
     `apply_retention` — exact strings, not a regex that would also match a
     changed format.
  2. CLI entry points run as subprocesses from a runtime-shaped layout
     (`<tmp>/prioritize-proposals/scripts/` beside `<tmp>/shared/`, the shape
     `install.sh` produces) — the migration's one new failure mode, an
     import of `skills/shared/` from a module run as a script, only shows up
     on this path. No existing test runs these entry points as subprocesses.
  3. `test_priorities_paths.py`, `test_retention.py`, and `test_smoke_e2e.py`
     stay byte-unchanged — enforced by the Phase 3 checkpoint's
     `git diff --quiet`, not by this file.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"
SHARED_DIR = REPO_ROOT / "skills" / "shared"
sys.path.insert(0, str(SCRIPTS_DIR))

from priorities_paths import build_paths, build_run_id, parse_run_id  # noqa: E402
from retention import apply_retention  # noqa: E402


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), *args], check=True, capture_output=True, text=True)


def _rev_parse(repo_root: Path, rev: str = "HEAD") -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", rev], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """A minimal git repo so the run-id CLI subcommand has a real HEAD."""
    repo_root = tmp_path / "fixture-repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "a@b.c")
    _git(repo_root, "config", "user.name", "Test")
    (repo_root / "README.md").write_text("hello\n")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-q", "-m", "base")
    return repo_root


# ─────────────────────────────────────────────────────────────────────────
# Part 1: function-level pins
# ─────────────────────────────────────────────────────────────────────────


class TestFunctionLevelPins:
    def test_run_id_and_paths_for_known_time_and_sha(self, tmp_path: Path):
        now = datetime(2026, 6, 10, 14, 30, 52, tzinfo=timezone.utc)
        head_sha = "a93fe59a8b1c2d3e4f5"
        run_id = build_run_id(now, head_sha)
        assert run_id == "2026-06-10-143052-a93fe59"

        base = tmp_path / "priorities"
        paths = build_paths(base, run_id)
        assert paths.dated_dir == base / "2026-06-10-143052-a93fe59"
        assert paths.report_md == paths.dated_dir / "report.md"
        assert paths.report_json == paths.dated_dir / "report.json"
        assert paths.latest_md == base / "latest.md"
        assert paths.latest_json == base / "latest.json"
        assert paths.archive_dir == base / "archive"
        assert paths.archive_destination == base / "archive" / run_id

    def test_parse_run_id_extracts_components(self):
        assert parse_run_id("2026-06-10-143052-a93fe59") == (
            "2026-06-10",
            "143052",
            "a93fe59",
        )

    def test_parse_run_id_handles_legacy_suffix(self):
        assert parse_run_id("2026-05-04-legacy") == ("2026-05-04", "", "legacy")

    def test_apply_retention_archives_oldest_rather_than_deleting(self, tmp_path: Path):
        base = tmp_path / "priorities"
        base.mkdir()
        for i in range(31):
            d = base / f"2026-06-{i + 1:02d}-100000-{i:07x}"
            d.mkdir()
            (d / "report.md").write_text(f"run {i}")
        result = apply_retention(base, retain=30)
        assert result.archived_count == 1
        assert result.active_count == 30
        archived = list((base / "archive").iterdir())
        assert len(archived) == 1
        assert archived[0].name == "2026-06-01-100000-0000000"
        assert (archived[0] / "report.md").read_text() == "run 0"
        # Not deleted — moved.
        assert not (base / "2026-06-01-100000-0000000").exists()


# ─────────────────────────────────────────────────────────────────────────
# Part 2: CLI entry points as subprocesses, from a runtime-shaped copy
# ─────────────────────────────────────────────────────────────────────────


def _ignore_tests_and_pycache(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in ("tests", "__pycache__")}


@pytest.fixture()
def runtime_copy(tmp_path: Path) -> Path:
    """Copy scripts/ and shared/ into the shape install.sh produces:
    <tmp>/prioritize-proposals/scripts/ beside <tmp>/shared/."""
    dest_scripts_parent = tmp_path / "prioritize-proposals"
    shutil.copytree(SCRIPTS_DIR, dest_scripts_parent / "scripts", ignore=_ignore_tests_and_pycache)
    if SHARED_DIR.exists():
        shutil.copytree(SHARED_DIR, tmp_path / "shared", ignore=_ignore_tests_and_pycache)
    return tmp_path


class TestCliEntryPointsFromRuntimeLayout:
    def test_run_id_subcommand_matches_fixture_head(self, runtime_copy: Path, fixture_repo: Path):
        head = _rev_parse(fixture_repo)
        out = subprocess.run(
            [
                sys.executable,
                str(runtime_copy / "prioritize-proposals" / "scripts" / "priorities_paths.py"),
                "run-id",
            ],
            cwd=str(fixture_repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-[0-9a-f]{7}$", out)
        assert out.endswith(head[:7])

    def test_run_id_subcommand_uses_utc_not_local_time(
        self, runtime_copy: Path, fixture_repo: Path
    ):
        # TZ=America/New_York is hours off UTC. If the CLI dropped
        # timezone.utc for a naive datetime.now(), the emitted run-id would
        # reflect local wall clock instead — hours outside the [before,
        # after] UTC window below. A shape-only assertion would not catch
        # this; the function-level pins above call build_run_id with an
        # explicit UTC datetime, so they would not see it either.
        env = dict(os.environ)
        env["TZ"] = "America/New_York"
        before = datetime.now(timezone.utc)
        out = subprocess.run(
            [
                sys.executable,
                str(runtime_copy / "prioritize-proposals" / "scripts" / "priorities_paths.py"),
                "run-id",
            ],
            cwd=str(fixture_repo),
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()
        after = datetime.now(timezone.utc)

        date_part, hms_part, _sha = parse_run_id(out)
        emitted = datetime.strptime(f"{date_part}{hms_part}", "%Y-%m-%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        assert before - timedelta(seconds=10) <= emitted <= after + timedelta(seconds=10)

    def test_paths_subcommand_prints_expected_lines(self, runtime_copy: Path):
        run_id = "2026-06-10-143052-a93fe59"
        base = runtime_copy / "priorities-base"
        out = subprocess.run(
            [
                sys.executable,
                str(runtime_copy / "prioritize-proposals" / "scripts" / "priorities_paths.py"),
                "paths",
                run_id,
                "--base",
                str(base),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        lines = {line for line in out.strip().splitlines() if line}
        expected = {
            f"dated_dir={base / run_id}",
            f"report_md={base / run_id / 'report.md'}",
            f"report_json={base / run_id / 'report.json'}",
            f"latest_md={base / 'latest.md'}",
            f"latest_json={base / 'latest.json'}",
            f"archive_dir={base / 'archive'}",
            f"archive_destination={base / 'archive' / run_id}",
        }
        assert lines == expected

    def test_retention_subcommand_archives_and_reports_counts(self, runtime_copy: Path):
        base = runtime_copy / "retention-base"
        base.mkdir()
        for run_id, body in (
            ("2026-06-09-090000-aaaaaaa", "older"),
            ("2026-06-10-100000-bbbbbbb", "newer"),
        ):
            d = base / run_id
            d.mkdir()
            (d / "report.md").write_text(body)

        out = subprocess.run(
            [
                sys.executable,
                str(runtime_copy / "prioritize-proposals" / "scripts" / "retention.py"),
                "--base",
                str(base),
                "--retain",
                "1",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        assert out == "active=1 archived=1"
        archived_dir = base / "archive" / "2026-06-09-090000-aaaaaaa"
        assert archived_dir.is_dir()
        assert (archived_dir / "report.md").read_text() == "older"
        assert (base / "2026-06-10-100000-bbbbbbb").is_dir()
