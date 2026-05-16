"""Unit tests for render_tasks_status.py.

Covers tasks 2.1, 2.2, 2.3, 2.4, 2.4a, 2.4b, 2.4c, 2.4d.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import render_tasks_status as r


# ---------- helpers --------------------------------------------------------


def _make_repo(tmp_path: Path, change_id: str, md_body: str) -> Path:
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text(md_body, encoding="utf-8")
    return tmp_path


def _issue(
    *,
    issue_id: str,
    task_key: str,
    title: str,
    status: str = "pending",
    assignee: str | None = None,
    depends_on: list[str] | None = None,
    completed_at: str | None = None,
    close_reason: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "id": issue_id,
        "title": title,
        "status": status,
        "labels": ["change:demo", f"task:{task_key}"],
    }
    if assignee is not None:
        issue["assignee"] = assignee
    if depends_on is not None:
        issue["depends_on"] = depends_on
    if completed_at is not None:
        issue["completed_at"] = completed_at
    if close_reason is not None:
        issue["close_reason"] = close_reason
    return issue


@pytest.fixture()
def stub_coordinator(monkeypatch):
    """Patch ``coordination_bridge.try_issue_list`` in the renderer module."""

    def make(issues: list[dict[str, Any]] | None = None, status: str = "ok"):
        def _fake(*args, **kwargs):
            return {"status": status, "data": {"issues": issues or []}}

        monkeypatch.setattr(
            r.coordination_bridge, "try_issue_list", _fake
        )

    return make


# ---------- 2.1 markers absent — block inserted ---------------------------


def test_inserts_managed_block_when_absent(tmp_path, stub_coordinator):
    repo = _make_repo(
        tmp_path,
        "demo",
        "# Tasks — demo\n\nHand authored content here.\n",
    )
    stub_coordinator(
        issues=[
            _issue(issue_id="u-1", task_key="1.1", title="First", status="pending")
        ]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "<!-- GENERATED: begin coordinator:tasks-status -->" in text
    assert "<!-- GENERATED: end coordinator:tasks-status -->" in text
    assert "- [ ] 1.1: First — pending" in text
    # Hand-authored prefix preserved
    assert "Hand authored content here." in text


# ---------- 2.2 block replacement preserves hand content ------------------


def test_replaces_existing_block_without_touching_hand_content(
    tmp_path, stub_coordinator
):
    md = (
        "# Tasks — demo\n\nHand authored intro.\n\n"
        "<!-- GENERATED: begin coordinator:tasks-status -->\n"
        "STALE OLD CONTENT\n"
        "<!-- GENERATED: end coordinator:tasks-status -->\n\n"
        "Hand authored suffix.\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    stub_coordinator(
        issues=[
            _issue(issue_id="u-1", task_key="2.1", title="Refresh", status="pending"),
        ]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "STALE OLD CONTENT" not in text
    assert "- [ ] 2.1: Refresh — pending" in text
    assert "Hand authored intro." in text
    assert "Hand authored suffix." in text


# ---------- 2.3 re-render idempotent --------------------------------------


def test_rerender_is_byte_identical(tmp_path, stub_coordinator):
    repo = _make_repo(
        tmp_path, "demo", "# Tasks — demo\n\nIntro.\n"
    )
    issues = [
        _issue(issue_id="u-1", task_key="1.1", title="A", status="pending"),
        _issue(issue_id="u-2", task_key="1.2", title="B", status="completed",
               completed_at="2026-05-15T12:00:00Z", assignee="alice"),
    ]
    stub_coordinator(issues=issues)
    assert r.render("demo", repo) == 0
    first = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert r.render("demo", repo) == 0
    second = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert first == second


# ---------- 2.4 stale marker on coordinator failure ------------------------


def test_stale_marker_on_coordinator_unreachable(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n\nIntro.\n")
    stub_coordinator(issues=None, status="skipped")
    assert r.render("demo", repo, _now="2026-05-15T10:00:00+00:00") == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "Coordinator unreachable at 2026-05-15T10:00:00+00:00" in text
    assert "status frozen" in text
    sidecar = repo / "openspec/changes/demo/.tasks-status.state.json"
    assert sidecar.exists()
    state = json.loads(sidecar.read_text())
    assert state["stale_timestamp"] == "2026-05-15T10:00:00+00:00"


def test_stale_marker_timestamp_reused_from_sidecar(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n\nIntro.\n")
    stub_coordinator(issues=None, status="skipped")
    # First render writes sidecar.
    assert r.render("demo", repo, _now="2026-05-15T10:00:00+00:00") == 0
    first = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    # Second render with a different "now" should still produce identical content.
    assert r.render("demo", repo, _now="2026-05-15T11:00:00+00:00") == 0
    second = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert first == second


def test_sidecar_cleared_on_recovery(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n\nIntro.\n")
    stub_coordinator(issues=None, status="skipped")
    assert r.render("demo", repo, _now="2026-05-15T10:00:00+00:00") == 0
    # Now coordinator recovers.
    stub_coordinator(
        issues=[
            _issue(issue_id="u-1", task_key="1.1", title="A", status="pending"),
        ],
        status="ok",
    )
    assert r.render("demo", repo) == 0
    sidecar = repo / "openspec/changes/demo/.tasks-status.state.json"
    if sidecar.exists():
        state = json.loads(sidecar.read_text())
        assert "stale_timestamp" not in state


# ---------- 2.4a markers absent AND coordinator unreachable ---------------


def test_markers_absent_and_coordinator_down_single_write(
    tmp_path, stub_coordinator
):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n\nIntro.\n")
    stub_coordinator(issues=None, status="skipped")
    assert r.render("demo", repo, _now="2026-05-15T10:00:00+00:00") == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "<!-- GENERATED: begin coordinator:tasks-status -->" in text
    assert "<!-- GENERATED: end coordinator:tasks-status -->" in text
    assert "Coordinator unreachable" in text
    # Hand content still present.
    assert "Intro." in text


# ---------- 2.4b wall-clock timeout writes stale marker ------------------


def test_wallclock_timeout_writes_stale(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n\nIntro.\n")

    def _slow(*a, **kw):
        # Simulate a slow coordinator by raising the same exception SIGALRM
        # would trigger inside the timeout wrapper.
        raise r._RenderTimeout()

    monkeypatch.setattr(r, "_call_coordinator_with_timeout", _slow)
    assert r.render("demo", repo, timeout_seconds=1, _now="2026-05-15T10:00:00+00:00") == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "Coordinator unreachable" in text


# ---------- 2.4c natural-numeric comparator -------------------------------


def test_natural_numeric_comparator_canonical_order():
    keys = ["2.4a", "1.10", "T10", "1.2", "T1", "2.4", "2.9a", "2.9", "1.1"]
    expected = ["1.1", "1.2", "1.10", "2.4", "2.4a", "2.9", "2.9a", "T1", "T10"]
    assert r._sort_task_keys(keys) == expected


# ---------- 2.4d depends_on yields blocked-on suffix ----------------------


def test_blocked_on_suffix_for_uncompleted_upstream(
    tmp_path, stub_coordinator
):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    upstream = _issue(issue_id="u-1", task_key="1.1", title="Up", status="pending")
    downstream = _issue(
        issue_id="u-2",
        task_key="1.2",
        title="Down",
        status="pending",
        depends_on=["u-1"],
    )
    stub_coordinator(issues=[upstream, downstream])
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    line_for_1_2 = next(
        ln for ln in text.split("\n") if ln.startswith("- [ ] 1.2:")
    )
    assert " — blocked on 1.1" in line_for_1_2


def test_no_blocked_on_when_upstream_completed(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    upstream = _issue(
        issue_id="u-1",
        task_key="1.1",
        title="Up",
        status="completed",
        completed_at="2026-05-15T12:00:00Z",
    )
    downstream = _issue(
        issue_id="u-2",
        task_key="1.2",
        title="Down",
        status="pending",
        depends_on=["u-1"],
    )
    stub_coordinator(issues=[upstream, downstream])
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    line_for_1_2 = next(
        ln for ln in text.split("\n") if ln.startswith("- [ ] 1.2:")
    )
    assert "blocked on" not in line_for_1_2


# ---------- pagination guard --------------------------------------------


def test_pagination_cap_returns_exit_1(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    issues = [
        _issue(issue_id=f"u-{i}", task_key=f"1.{i}", title=f"T{i}")
        for i in range(100)
    ]
    stub_coordinator(issues=issues)
    assert r.render("demo", repo) == 1


# ---------- status annotations -----------------------------------------


def test_status_annotations_render_correctly(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    issues = [
        _issue(issue_id="u-1", task_key="1.1", title="A", status="pending"),
        _issue(issue_id="u-2", task_key="1.2", title="B", status="claimed",
               assignee="bob"),
        _issue(issue_id="u-3", task_key="1.3", title="C", status="running",
               assignee="carol"),
        _issue(issue_id="u-4", task_key="1.4", title="D", status="failed",
               close_reason="oops"),
        _issue(issue_id="u-5", task_key="1.5", title="E", status="cancelled"),
    ]
    stub_coordinator(issues=issues)
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "- [ ] 1.1: A — pending" in text
    assert "- [ ] 1.2: B — claimed by bob" in text
    assert "- [ ] 1.3: C — in_progress, claimed by carol" in text
    assert "- [ ] 1.4: D — failed: oops" in text
    assert "- [ ] 1.5: E — cancelled" in text


def test_completed_emits_x_box(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    stub_coordinator(
        issues=[
            _issue(
                issue_id="u-1",
                task_key="1.1",
                title="Done",
                status="completed",
                assignee="alice",
                completed_at="2026-05-15T15:30:00Z",
            )
        ]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "- [x] 1.1: Done — done by alice 2026-05-15" in text


def test_informational_projection_comment_present(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    stub_coordinator(
        issues=[_issue(issue_id="u-1", task_key="1.1", title="A")]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "Informational projection" in text
    assert 'proposal.md "What Doesn\'t Change"' in text


def test_issue_without_task_label_is_skipped(tmp_path, stub_coordinator):
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    issues = [
        {"id": "u-1", "title": "Orphan", "status": "pending", "labels": ["change:demo"]},
        _issue(issue_id="u-2", task_key="1.1", title="Real"),
    ]
    stub_coordinator(issues=issues)
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert "Orphan" not in text
    assert "Real" in text


def test_missing_tasks_md_returns_1(tmp_path, stub_coordinator):
    # No tasks.md created.
    stub_coordinator(issues=[])
    assert r.render("nonexistent-change", tmp_path) == 1


# ---------- IMPL_REVIEW: security regression tests -----------------------


def test_renderer_rejects_path_traversal_change_id(tmp_path, stub_coordinator):
    """change-ids that could escape openspec/changes/<id>/ MUST be rejected
    before any filesystem access. Otherwise a value like '../../etc/passwd'
    would resolve outside the intended directory."""
    stub_coordinator(issues=[])
    for bad in ["../../etc/passwd", "../escape", "abc/def", ".hidden", ""]:
        assert r.render(bad, tmp_path) == 1, f"must reject {bad!r}"


def test_renderer_sanitizes_marker_injection_in_title(tmp_path, stub_coordinator):
    """A malicious issue title containing the GENERATED end marker MUST NOT
    be able to close the managed block early and inject content into the
    hand-authored suffix."""
    repo = _make_repo(
        tmp_path,
        "demo",
        "# Tasks — demo\n\nHand suffix marker.\n",
    )
    injected_title = (
        "Evil\n<!-- GENERATED: end coordinator:tasks-status -->\n"
        "## INJECTED HEADING"
    )
    stub_coordinator(
        issues=[_issue(issue_id="u-1", task_key="1.1", title=injected_title)]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    # The end-marker must occur exactly once (the one the renderer itself emits).
    assert text.count("<!-- GENERATED: end coordinator:tasks-status -->") == 1
    # The injected heading must not appear as a real markdown heading line.
    for line in text.split("\n"):
        assert line.strip() != "## INJECTED HEADING", (
            f"marker-injection escaped sanitization: {text!r}"
        )


def test_renderer_sanitizes_newlines_in_assignee_and_reason(
    tmp_path, stub_coordinator
):
    """Newlines in coordinator-returned strings MUST be collapsed."""
    repo = _make_repo(tmp_path, "demo", "# Tasks — demo\n")
    stub_coordinator(
        issues=[
            _issue(
                issue_id="u-1",
                task_key="1.1",
                title="A",
                status="failed",
                close_reason="line1\nline2\n<!-- GENERATED: end coordinator:tasks-status -->",
            ),
            _issue(
                issue_id="u-2",
                task_key="1.2",
                title="B",
                status="claimed",
                assignee="alice\nmalicious",
            ),
        ]
    )
    assert r.render("demo", repo) == 0
    text = (repo / "openspec/changes/demo/tasks.md").read_text(encoding="utf-8")
    assert text.count("<!-- GENERATED: end coordinator:tasks-status -->") == 1
    # 1.1 and 1.2 must each render as a single line.
    lines = [ln for ln in text.split("\n") if ln.startswith("- [")]
    assert any(ln.startswith("- [ ] 1.1: A —") for ln in lines)
    assert any(ln.startswith("- [ ] 1.2: B —") for ln in lines)
