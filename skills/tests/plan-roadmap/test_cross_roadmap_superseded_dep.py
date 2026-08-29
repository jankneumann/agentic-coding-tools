"""An ``external_depends_on`` edge into a superseded item must fail validation.

``superseded`` is terminal (ri-17): the work moved to the item named in the
``superseded_by`` edge, and the superseded item will never reach ``completed``.
``completed_external_refs`` only admits ``completed``, so a dependent whose
prerequisite was superseded is withheld from ``ready_items()`` on every run —
permanently, and with no diagnostic, because a non-ready item is simply absent
from the returned list rather than reported.

Blocking is the correct semantics. Blocking *silently* is the defect (issue
#388). These tests pin two things:

* the stall is real — ``ready_items`` genuinely withholds the dependent
  (``test_stall_is_real``), so the validation error is describing a live
  failure rather than a hypothetical one;
* ``validate_cross_roadmap`` reports it, naming the successor to repoint at.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from decomposer import validate_cross_roadmap

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_RUNTIME_DIR = str(_SKILLS_DIR / "roadmap-runtime" / "scripts")
if _RUNTIME_DIR not in sys.path:
    sys.path.insert(0, _RUNTIME_DIR)

from models import (  # type: ignore[import-untyped]  # noqa: E402
    completed_external_refs,
    load_all_roadmaps,
)


def _item(item_id: str, **kwargs) -> dict:
    d: dict = {
        "item_id": item_id,
        "title": "Item",
        "status": "approved",
        "priority": 1,
        "effort": "M",
        "depends_on": kwargs.pop("depends_on", []),
        "acceptance_outcomes": ["done"],
    }
    d.update(kwargs)
    return d


def _write_roadmap(repo_root: Path, roadmap_id: str, items: list[dict]) -> None:
    data = {
        "schema_version": 1,
        "roadmap_id": roadmap_id,
        "source_proposal": f"openspec/roadmaps/{roadmap_id}/proposal.md",
        "status": "approved",
        "policy": {"default_action": "wait_if_budget_exceeded"},
        "items": items,
    }
    path = repo_root / "openspec" / "roadmaps" / roadmap_id / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, sort_keys=False))


def _supersession_scenario(repo_root: Path) -> None:
    """The failure scenario from issue #388.

    ``beta:ri-04`` externally depends on ``alpha:ri-09``; ``alpha:ri-09`` is
    later superseded by ``gamma:ri-02``.
    """
    _write_roadmap(
        repo_root,
        "alpha",
        [_item("ri-09", status="superseded", superseded_by=["gamma:ri-02"])],
    )
    _write_roadmap(repo_root, "gamma", [_item("ri-02")])
    _write_roadmap(
        repo_root, "beta", [_item("ri-04", external_depends_on=["alpha:ri-09"])]
    )


class TestSupersededPrerequisite:
    def test_stall_is_real(self, tmp_path):
        """Readiness withholds the dependent, and nothing says why.

        This is the behaviour the validation error exists to explain. If this
        assertion ever flips — if a superseded prerequisite starts satisfying
        readiness — the validation check below is describing a stall that no
        longer happens and should be revisited, not merely relaxed.
        """
        _supersession_scenario(tmp_path)

        external_completed = completed_external_refs(tmp_path)
        assert "alpha:ri-09" not in external_completed

        beta = load_all_roadmaps(tmp_path)["beta"]
        ready_ids = [
            i.item_id for i in beta.ready_items(external_completed=external_completed)
        ]
        assert ready_ids == [], (
            "beta:ri-04 should be withheld — this test pins the silent stall "
            "that #388's validation error surfaces"
        )

    def test_external_dependency_on_superseded_item_fails(self, tmp_path):
        _supersession_scenario(tmp_path)

        errors = validate_cross_roadmap(tmp_path)
        matches = [
            e
            for e in errors
            if "beta:ri-04" in e and "alpha:ri-09" in e and "superseded" in e
        ]
        assert matches, f"expected a superseded-prerequisite error, got: {errors}"

    def test_error_names_the_successor(self, tmp_path):
        """Remediation must be actionable: name the item to repoint at."""
        _supersession_scenario(tmp_path)

        errors = validate_cross_roadmap(tmp_path)
        assert any("gamma:ri-02" in e for e in errors), (
            f"error must name the successor from superseded_by, got: {errors}"
        )

    def test_successorless_supersession_still_reports(self, tmp_path):
        """A superseded item with no ``superseded_by`` edge still stalls.

        The remedy text cannot name a successor, so it asks for one instead of
        going quiet — the stall is identical either way.
        """
        _write_roadmap(tmp_path, "alpha", [_item("ri-09", status="superseded")])
        _write_roadmap(
            tmp_path, "beta", [_item("ri-04", external_depends_on=["alpha:ri-09"])]
        )

        errors = validate_cross_roadmap(tmp_path)
        matches = [e for e in errors if "beta:ri-04" in e and "superseded" in e]
        assert matches, f"expected a superseded-prerequisite error, got: {errors}"
        assert any("superseded_by" in e for e in matches), (
            f"remedy should ask for the successor edge, got: {matches}"
        )


class TestNoFalsePositives:
    def test_completed_prerequisite_passes(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-09", status="completed")])
        _write_roadmap(
            tmp_path, "beta", [_item("ri-04", external_depends_on=["alpha:ri-09"])]
        )
        assert validate_cross_roadmap(tmp_path) == []

    def test_approved_prerequisite_passes(self, tmp_path):
        """Not-yet-done is a normal wait, not a stall — must stay silent.

        Every ``external_depends_on`` target in this repo today is ``approved``
        or ``candidate``; flagging those would make the check unusable.
        """
        _write_roadmap(tmp_path, "alpha", [_item("ri-09", status="approved")])
        _write_roadmap(
            tmp_path, "beta", [_item("ri-04", external_depends_on=["alpha:ri-09"])]
        )
        assert validate_cross_roadmap(tmp_path) == []

    def test_superseded_by_edge_into_superseded_item_is_not_flagged(self, tmp_path):
        """Only ``external_depends_on`` gates readiness.

        A ``superseded_by`` chain (A superseded by B, B itself superseded by C)
        is a historical record, not a prerequisite, and blocks nothing.
        """
        _write_roadmap(
            tmp_path,
            "alpha",
            [
                _item("ri-09", status="superseded", superseded_by=["alpha:ri-10"]),
                _item("ri-10", status="superseded", superseded_by=["alpha:ri-11"]),
                _item("ri-11"),
            ],
        )
        assert validate_cross_roadmap(tmp_path) == []


def test_live_roadmaps_have_no_superseded_prerequisites():
    """The repo's own roadmaps must not carry this edge.

    #388 was filed as latent — no live edge hit it. This asserts that stays
    true, so the defect cannot reappear un-noticed in committed roadmap data.
    """
    repo_root = Path(__file__).resolve().parents[3]
    errors = [e for e in validate_cross_roadmap(repo_root) if "superseded" in e]
    assert errors == [], f"live roadmaps carry a superseded prerequisite: {errors}"


def test_closed_loop_scheduler_owns_repo_improvement_handoff():
    """The successor edge releases ri-13 without scheduling ri-12 twice."""
    repo_root = Path(__file__).resolve().parents[3]
    roadmaps = load_all_roadmaps(repo_root)

    scheduler = roadmaps["repo-improvement"].get_item("ri-12")
    consumer = roadmaps["repo-improvement"].get_item("ri-13")

    assert scheduler is not None
    assert scheduler.status.value == "superseded"
    assert scheduler.superseded_by == ["closed-loop-learning:ri-01"]

    assert consumer is not None
    assert "ri-12" not in consumer.depends_on
