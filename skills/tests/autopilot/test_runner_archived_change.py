"""The runner drives a change archived before its loop reached DONE.

A change archived inside its own PR (before SUBMIT_PR -> DONE) must still be
reachable by transition, record-degradation and emit-result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import autopilot
import runner


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _archived(root: Path, change_id: str = "demo", date: str = "2026-10-10") -> Path:
    path = root / "openspec" / "changes" / "archive" / f"{date}-{change_id}" / "loop-state.json"
    autopilot.save_state(autopilot.LoopState(change_id=change_id, current_phase="SUBMIT_PR"), path)
    return path.parent


def test_an_active_change_resolves_to_its_directory(workspace: Path) -> None:
    active = workspace / "openspec" / "changes" / "demo"
    autopilot.save_state(autopilot.LoopState(change_id="demo"), active / "loop-state.json")
    _archived(workspace)

    assert runner._change_dir("demo") == Path("openspec/changes/demo")


def test_an_archived_change_resolves_to_its_latest_archive(workspace: Path) -> None:
    _archived(workspace, date="2026-09-01")
    latest = _archived(workspace, date="2026-10-10")

    assert runner._change_dir("demo") == latest.relative_to(workspace)


def test_a_result_only_active_directory_does_not_hide_the_archived_loop(workspace: Path) -> None:
    archived = _archived(workspace)
    (workspace / "openspec" / "changes" / "demo" / "dispatch-results").mkdir(parents=True)

    assert runner._change_dir("demo") == archived.relative_to(workspace)


def test_a_followup_archive_does_not_shadow_its_parent(workspace: Path) -> None:
    _archived(workspace, change_id="followup-demo", date="2026-11-01")

    assert runner._change_dir("demo") == Path("openspec/changes/demo")


def test_record_degradation_writes_the_archived_loop_state(workspace: Path) -> None:
    archived = _archived(workspace)

    rc = runner.main(
        ["record-degradation", "demo", "--code", "single_vendor_review", "--phase", "VAL_REVIEW",
         "--detail", "claude_code lane only"]
    )

    assert rc == 0
    state = json.loads((archived / "loop-state.json").read_text())
    assert "single_vendor_review" in json.dumps(state)
    assert not (workspace / "openspec" / "changes" / "demo").exists()
