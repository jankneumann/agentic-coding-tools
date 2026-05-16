"""Unit tests for seed_tasks_from_md.py.

Covers tasks 2.8, 2.9, 2.9a, 2.9b, 2.10.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import seed_tasks_from_md as s


# ---------- helpers --------------------------------------------------------


def _make_repo(tmp_path: Path, change_id: str, md_body: str) -> Path:
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text(md_body, encoding="utf-8")
    return tmp_path


class FakeBridge:
    """Records calls to try_issue_create / try_issue_list."""

    def __init__(
        self,
        existing: list[dict[str, Any]] | None = None,
        list_status: str = "ok",
        create_status: str = "ok",
    ):
        self.existing = list(existing or [])
        self.list_status = list_status
        self.create_status = create_status
        self.list_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self._next_id = 1

    def try_issue_list(self, **kwargs):
        self.list_calls.append(dict(kwargs))
        return {
            "status": self.list_status,
            "data": {"issues": list(self.existing)},
        }

    def try_issue_create(self, **kwargs):
        self.create_calls.append(dict(kwargs))
        if self.create_status != "ok":
            return {"status": self.create_status}
        uid = f"u-{self._next_id}"
        self._next_id += 1
        return {"status": "ok", "data": {"id": uid}}


@pytest.fixture()
def fake_bridge(monkeypatch):
    def make(**kwargs) -> FakeBridge:
        fb = FakeBridge(**kwargs)
        monkeypatch.setattr(s.coordination_bridge, "try_issue_list", fb.try_issue_list)
        monkeypatch.setattr(
            s.coordination_bridge, "try_issue_create", fb.try_issue_create
        )
        return fb

    return make


# ---------- 2.8 seeder POSTs correct payload and no metadata --------------


def test_seeder_posts_correct_labels_and_no_metadata(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] 1.1 First task\n"
        "  **Dependencies**: None\n"
        "- [ ] 1.2 Second task\n"
        "  **Dependencies**: 1.1\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo) == 0
    assert len(fb.create_calls) == 2
    for call in fb.create_calls:
        assert "metadata" not in call, "metadata field MUST NOT be passed"
        assert "change:demo" in call["labels"]
        assert any(lbl.startswith("task:") for lbl in call["labels"])
        assert call["issue_type"] == "task"
    # task:1.1 should be POSTed first (depends_on=None) then task:1.2 with deps.
    first, second = fb.create_calls
    assert "task:1.1" in first["labels"]
    assert "task:1.2" in second["labels"]
    assert second["depends_on"] == ["u-1"]


# ---------- 2.9 idempotency via change:<id> + task:<key> ------------------


def test_seeder_idempotent_via_label_pair(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] 1.1 First\n"
        "  **Dependencies**: None\n"
        "- [ ] 1.2 Second\n"
        "  **Dependencies**: None\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    existing = [
        {
            "id": "existing-uuid",
            "labels": ["change:demo", "task:1.1"],
            "title": "First",
            "status": "pending",
        }
    ]
    fb = fake_bridge(existing=existing)
    assert s.seed("demo", repo) == 0
    # Only 1.2 should be created; 1.1 already exists.
    assert len(fb.create_calls) == 1
    assert "task:1.2" in fb.create_calls[0]["labels"]


# ---------- 2.9a cycle detection precedes any POST ------------------------


def test_seeder_exits_1_on_cycle_with_no_posts(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] 1.1 First\n"
        "  **Dependencies**: 1.2\n"
        "- [ ] 1.2 Second\n"
        "  **Dependencies**: 1.1\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo) == 1
    assert fb.create_calls == [], "no POSTs allowed when cycle detected"
    assert fb.list_calls == [], "no list calls either — cycle preflight first"


# ---------- 2.9b managed block ignored when parsing ----------------------


def test_seeder_ignores_managed_block_content(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] T1 First hand-authored\n"
        "  **Dependencies**: None\n"
        "- [ ] T2 Second hand-authored\n"
        "  **Dependencies**: T1\n"
        "\n"
        "<!-- GENERATED: begin coordinator:tasks-status -->\n"
        "- [ ] T1: First — pending\n"
        "- [ ] T3: Phantom — pending\n"
        "<!-- GENERATED: end coordinator:tasks-status -->\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo) == 0
    posted_keys: list[str] = []
    for call in fb.create_calls:
        for lbl in call["labels"]:
            if lbl.startswith("task:"):
                posted_keys.append(lbl[len("task:") :])
    assert sorted(posted_keys) == ["T1", "T2"]
    assert "T3" not in posted_keys


# ---------- 2.10 coordinator unreachable -> exit 0, warning --------------


def test_seeder_exits_0_when_coordinator_unreachable(tmp_path, fake_bridge):
    md = "# Tasks\n\n- [ ] 1.1 First\n  **Dependencies**: None\n"
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge(list_status="skipped")
    assert s.seed("demo", repo) == 0
    assert fb.create_calls == []


def test_dry_run_makes_no_calls(tmp_path, fake_bridge):
    md = "# Tasks\n\n- [ ] 1.1 First\n  **Dependencies**: None\n"
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo, dry_run=True) == 0
    assert fb.list_calls == []
    assert fb.create_calls == []


def test_seeder_topologically_orders_three_node_chain(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] 1.3 Third\n"
        "  **Dependencies**: 1.2\n"
        "- [ ] 1.1 First\n"
        "  **Dependencies**: None\n"
        "- [ ] 1.2 Second\n"
        "  **Dependencies**: 1.1\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo) == 0
    posted = [
        next(lbl for lbl in call["labels"] if lbl.startswith("task:"))
        for call in fb.create_calls
    ]
    assert posted == ["task:1.1", "task:1.2", "task:1.3"]


def test_seeder_rejects_path_traversal_change_id(tmp_path, fake_bridge):
    """change-ids that could escape openspec/changes/<id>/ MUST be rejected."""
    fb = fake_bridge()
    for bad in ["../../etc/passwd", "../escape", "abc/def", ".hidden", ""]:
        assert s.seed(bad, tmp_path) == 1, f"must reject {bad!r}"
    assert fb.list_calls == []
    assert fb.create_calls == []


def test_forward_ref_to_unknown_key_is_warned_not_fatal(tmp_path, fake_bridge):
    md = (
        "# Tasks\n\n"
        "- [ ] 1.1 First\n"
        "  **Dependencies**: 9.9\n"
    )
    repo = _make_repo(tmp_path, "demo", md)
    fb = fake_bridge()
    assert s.seed("demo", repo) == 0
    assert len(fb.create_calls) == 1
    # Unknown forward ref dropped from depends_on
    assert "depends_on" not in fb.create_calls[0]
