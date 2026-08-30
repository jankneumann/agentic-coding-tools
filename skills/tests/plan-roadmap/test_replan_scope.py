"""Tests for ``decomposer.py replan-scope`` / ``replan-finish``.

Covers roadmap-orchestration scenarios *Replan scope is the affected subgraph
only*, *Replan without a request file is refused*, and *Replan preserves
completed items and learnings*.

These two subcommands are the deterministic half of
``/plan-roadmap --replan <roadmap-id>``; the re-decomposition itself is
host-executed and is simulated here by editing only the in-scope items.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from decomposer import main

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _item(item_id, status, depends_on=(), **extra):
    d = {
        "item_id": item_id,
        "title": f"Item {item_id}",
        "status": status,
        "priority": int(item_id.split("-")[1]),
        "effort": "S",
        "depends_on": list(depends_on),
        "acceptance_outcomes": [f"{item_id} works"],
    }
    d.update(extra)
    return d


def _write_workspace(tmp_path: Path, *, request: bool = True) -> Path:
    """ri-03 failed with a replan signal.

    ri-04, ri-06 are its parked dependents; ri-07 is a transitive dependent of
    ri-04; ri-05 is completed; ri-08 depends only on ri-05; ri-09 is superseded
    and ri-10 is in_progress — both preserved, so neither may enter the scope.
    """
    workspace = tmp_path / "openspec" / "roadmaps" / "demo"
    workspace.mkdir(parents=True)
    roadmap = {
        "schema_version": 1,
        "roadmap_id": "demo",
        "source_proposal": "proposal.md",
        "status": "in_progress",
        "policy": {"default_action": "wait_if_budget_exceeded",
                   "max_switch_attempts_per_item": 2},
        "items": [
            _item("ri-03", "failed"),
            _item("ri-04", "replan_required", ["ri-03"], blocked_by=["ri-03"]),
            _item("ri-05", "completed"),
            _item("ri-06", "replan_required", ["ri-03"], blocked_by=["ri-03"]),
            _item("ri-07", "approved", ["ri-04"]),
            _item("ri-08", "approved", ["ri-05"]),
            _item("ri-09", "superseded", ["ri-04"], superseded_by=["other:ri-01"]),
            _item("ri-10", "in_progress", ["ri-06"]),
        ],
    }
    (workspace / "roadmap.yaml").write_text(
        yaml.dump(roadmap, default_flow_style=False, sort_keys=False)
    )
    learnings = workspace / "learnings"
    learnings.mkdir()
    (learnings / "ri-03.md").write_text("---\nitem_id: ri-03\n---\n\n# Learning: ri-03\n")
    (learnings / "ri-05.md").write_text("---\nitem_id: ri-05\n---\n\n# Learning: ri-05\n")
    if request:
        (workspace / "replan-request.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "roadmap_id": "demo",
                    "failed_item_id": "ri-03",
                    "failure_reason": "design dead-end",
                    "replan_required_items": ["ri-04", "ri-06"],
                    "learning_entry": "learnings/ri-03.md",
                    "gate_decision": {
                        "gate": "replan_required",
                        "outcome": "proceed",
                        "resolution": "auto",
                        "disposition": "auto",
                        "reason": "posture auto",
                        "posture_present": True,
                        "recorded_at": "2026-01-01T00:00:00+00:00",
                    },
                    "requested_at": "2026-01-01T00:00:00+00:00",
                },
                indent=2,
            )
            + "\n"
        )
    return workspace


class TestReplanScope:
    def test_scope_is_seeds_plus_non_completed_transitive_dependents(self, tmp_path, capsys):
        workspace = _write_workspace(tmp_path)

        rc = main(["replan-scope", str(workspace), "--repo-root", str(_REPO_ROOT)])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["roadmap_id"] == "demo"
        assert payload["failed_item_id"] == "ri-03"
        assert payload["seed_items"] == ["ri-04", "ri-06"]
        assert payload["scope_items"] == ["ri-04", "ri-06", "ri-07"]

    def test_scope_excludes_completed_superseded_in_progress_and_unrelated(
        self, tmp_path, capsys
    ):
        workspace = _write_workspace(tmp_path)

        main(["replan-scope", str(workspace), "--repo-root", str(_REPO_ROOT)])

        payload = json.loads(capsys.readouterr().out)
        scope = set(payload["scope_items"])
        assert "ri-05" not in scope   # completed
        assert "ri-08" not in scope   # unrelated (depends only on ri-05)
        assert "ri-09" not in scope   # superseded
        assert "ri-10" not in scope   # in_progress
        assert "ri-03" not in scope   # the failed item itself is re-planned around
        assert set(payload["preserved_items"]) >= {"ri-05", "ri-09", "ri-10"}

    def test_learning_entry_is_carried_through(self, tmp_path, capsys):
        workspace = _write_workspace(tmp_path)
        main(["replan-scope", str(workspace), "--repo-root", str(_REPO_ROOT)])
        payload = json.loads(capsys.readouterr().out)
        assert payload["learning_entry"] == "learnings/ri-03.md"

    def test_workspace_may_be_named_by_roadmap_id(self, tmp_path, capsys):
        """`--replan <roadmap-id>` plumbing: the positional accepts an id and
        resolves it under <repo-root>/openspec/roadmaps/."""
        _write_workspace(tmp_path)

        rc = main(["replan-scope", "demo", "--repo-root", str(tmp_path)])

        assert rc == 0
        assert json.loads(capsys.readouterr().out)["roadmap_id"] == "demo"

    def test_missing_request_file_is_refused(self, tmp_path, capsys):
        workspace = _write_workspace(tmp_path, request=False)
        before = (workspace / "roadmap.yaml").read_bytes()

        rc = main(["replan-scope", str(workspace), "--repo-root", str(_REPO_ROOT)])

        assert rc == 2
        err = capsys.readouterr().err
        assert "replan-request.json" in err
        assert (workspace / "roadmap.yaml").read_bytes() == before


class TestReplanFinish:
    def _simulate_host_redecomposition(self, workspace: Path) -> None:
        """The host rewrites only the in-scope items; statuses stay
        replan_required until replan-finish flips them."""
        text = (workspace / "roadmap.yaml").read_text()
        text = text.replace("title: Item ri-04", "title: Item ri-04 (re-decomposed)")
        (workspace / "roadmap.yaml").write_text(text)

    def test_preserves_completed_superseded_in_progress_and_learnings(self, tmp_path):
        workspace = _write_workspace(tmp_path)
        before_items = {
            i["item_id"]: i
            for i in yaml.safe_load((workspace / "roadmap.yaml").read_text())["items"]
        }
        before_learnings = {
            p.name: p.read_bytes() for p in (workspace / "learnings").iterdir()
        }

        self._simulate_host_redecomposition(workspace)
        rc = main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])
        assert rc == 0

        after_items = {
            i["item_id"]: i
            for i in yaml.safe_load((workspace / "roadmap.yaml").read_text())["items"]
        }
        for item_id in ("ri-05", "ri-09", "ri-10"):
            assert after_items[item_id] == before_items[item_id]
        assert {
            p.name: p.read_bytes() for p in (workspace / "learnings").iterdir()
        } == before_learnings

    def test_preserved_item_blocks_are_byte_identical(self, tmp_path):
        """Not just semantically equal — the YAML text of a preserved item is
        untouched, because replan-finish edits status lines in place instead of
        re-serializing the whole roadmap."""
        workspace = _write_workspace(tmp_path)
        before = (workspace / "roadmap.yaml").read_text()

        main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])

        after = (workspace / "roadmap.yaml").read_text()
        assert before.replace("status: replan_required", "status: approved") == after

    def test_sets_redecomposed_items_to_approved_and_deletes_request(self, tmp_path):
        workspace = _write_workspace(tmp_path)

        self._simulate_host_redecomposition(workspace)
        rc = main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])

        assert rc == 0
        items = {
            i["item_id"]: i
            for i in yaml.safe_load((workspace / "roadmap.yaml").read_text())["items"]
        }
        assert items["ri-04"]["status"] == "approved"
        assert items["ri-06"]["status"] == "approved"
        assert not (workspace / "replan-request.json").exists()

    def test_finished_roadmap_passes_validate(self, tmp_path):
        workspace = _write_workspace(tmp_path)
        main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])

        rc = main([
            "validate",
            str(workspace / "roadmap.yaml"),
            "--repo-root",
            str(_REPO_ROOT),
        ])
        assert rc == 0

    def test_missing_request_file_is_refused(self, tmp_path, capsys):
        workspace = _write_workspace(tmp_path, request=False)
        before = (workspace / "roadmap.yaml").read_bytes()

        rc = main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])

        assert rc == 2
        assert "replan-request.json" in capsys.readouterr().err
        assert (workspace / "roadmap.yaml").read_bytes() == before

    def test_invalid_roadmap_leaves_everything_untouched(self, tmp_path, capsys):
        """A host that broke the roadmap must not get its request file deleted:
        the replan has to stay retryable."""
        workspace = _write_workspace(tmp_path)
        text = (workspace / "roadmap.yaml").read_text()
        # Dangle every edge into ri-04 — referential integrity now fails.
        (workspace / "roadmap.yaml").write_text(text.replace("- ri-04", "- ri-99"))
        before = (workspace / "roadmap.yaml").read_bytes()

        rc = main(["replan-finish", str(workspace), "--repo-root", str(_REPO_ROOT)])

        assert rc == 1
        assert (workspace / "replan-request.json").exists()
        assert (workspace / "roadmap.yaml").read_bytes() == before
