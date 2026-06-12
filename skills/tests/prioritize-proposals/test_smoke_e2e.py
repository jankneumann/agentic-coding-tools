"""End-to-end smoke tests composing all helpers exactly as SKILL.md does.

Covers tasks 3.1 (markdown-only path), 3.2 (--format json with mandatory header),
and 3.3 (retention rollover at 31 entries).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "prioritize-proposals" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from artifact_header import make_header, wrap_report  # noqa: E402
from priorities_paths import build_paths, build_run_id  # noqa: E402
from retention import apply_retention, list_active_runs  # noqa: E402


@pytest.fixture
def priorities_dir(tmp_path: Path) -> Path:
    p = tmp_path / "priorities"
    p.mkdir()
    return p


def _smoke_run(priorities_dir: Path, *, with_json: bool, body: dict | None = None) -> Path:
    """Execute the SKILL.md persistence flow against a tmp priorities dir."""
    now = datetime.now(timezone.utc)
    head_sha = "a" * 40
    run_id = build_run_id(now, head_sha)
    paths = build_paths(priorities_dir, run_id)

    paths.dated_dir.mkdir(parents=True)
    paths.report_md.write_text(f"# Prioritization Report\nRun: {run_id}\n")
    shutil.copy(paths.report_md, paths.latest_md)

    if with_json:
        body = body or {"top_recommendation": "execute-foo", "items": []}
        header = make_header(now=now, git_sha=head_sha, run_id=run_id)
        wrapped = wrap_report(header, body)
        paths.report_json.write_text(json.dumps(wrapped, indent=2))
        shutil.copy(paths.report_json, paths.latest_json)

    return paths.dated_dir


class TestE2EMarkdownOnly:
    """Task 3.1 — md-only run produces dated dir + latest.md, no latest.json, no legacy path."""

    def test_markdown_only_flow(self, priorities_dir: Path):
        dated_dir = _smoke_run(priorities_dir, with_json=False)
        assert (dated_dir / "report.md").exists()
        assert not (dated_dir / "report.json").exists()
        assert (priorities_dir / "latest.md").exists()
        assert not (priorities_dir / "latest.json").exists()
        # latest.md mirrors the dated report.md byte-for-byte
        assert (priorities_dir / "latest.md").read_bytes() == (dated_dir / "report.md").read_bytes()


class TestE2EFormatJson:
    """Task 3.2 — --format json run produces report.json with the mandatory _header."""

    def test_json_carries_header_block(self, priorities_dir: Path):
        dated_dir = _smoke_run(priorities_dir, with_json=True)
        wrapped = json.loads((dated_dir / "report.json").read_text())
        # Two top-level keys: _header and report
        assert set(wrapped.keys()) == {"_header", "report"}
        header = wrapped["_header"]
        for field in (
            "schema_version",
            "generated_at",
            "git_sha",
            "generator",
            "run_id",
            "event_kind",
        ):
            assert field in header
        assert header["event_kind"] == "priorities-report"
        assert header["schema_version"] == 1
        assert len(header["git_sha"]) == 40

    def test_latest_json_byte_identical_to_dated(self, priorities_dir: Path):
        dated_dir = _smoke_run(priorities_dir, with_json=True)
        assert (priorities_dir / "latest.json").read_bytes() == (dated_dir / "report.json").read_bytes()

    def test_artifact_header_cli_produces_same_shape(self, priorities_dir: Path, tmp_path: Path):
        # Independent verification: invoke the CLI exactly as SKILL.md does.
        body_file = tmp_path / "body.json"
        out_file = tmp_path / "wrapped.json"
        body_file.write_text(json.dumps({"items": ["x"]}))
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "artifact_header.py"),
                "--run-id",
                "2026-06-10-143052-aaaaaaa",
                "--git-sha",
                "a" * 40,
                "--in",
                str(body_file),
                "--out",
                str(out_file),
            ],
            check=True,
        )
        wrapped = json.loads(out_file.read_text())
        assert "_header" in wrapped
        assert wrapped["_header"]["run_id"] == "2026-06-10-143052-aaaaaaa"
        assert wrapped["report"] == {"items": ["x"]}


class TestE2ERetentionRollover:
    """Task 3.3 — 31 dated dirs roll one into archive on retention default."""

    def test_rollover_at_31(self, priorities_dir: Path):
        # Make 31 entries spanning a few timestamps; oldest must be the one archived.
        for i in range(31):
            d = priorities_dir / f"2026-06-{i+1:02d}-100000-{i:07x}"
            d.mkdir()
            (d / "report.md").write_text(f"run {i}")
        result = apply_retention(priorities_dir, retain=30)
        assert result.archived_count == 1
        assert result.active_count == 30
        active = list_active_runs(priorities_dir)
        assert len(active) == 30
        # The oldest (day 01) was archived
        archived = list((priorities_dir / "archive").iterdir())
        assert len(archived) == 1
        assert archived[0].name.startswith("2026-06-01")

    def test_full_flow_with_retention(self, priorities_dir: Path):
        # Pre-populate to one under threshold, run a real smoke, retention should NOT trigger.
        for i in range(29):
            d = priorities_dir / f"2026-06-{i+1:02d}-100000-{i:07x}"
            d.mkdir()
            (d / "report.md").write_text(f"prior {i}")
        # Smoke writes #30 — still under retention
        _smoke_run(priorities_dir, with_json=False)
        result = apply_retention(priorities_dir, retain=30)
        assert result.archived_count == 0
        assert result.active_count == 30
        # The latest.md is present at the top level — not in any dated dir
        assert (priorities_dir / "latest.md").exists()
