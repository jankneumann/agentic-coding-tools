"""Repo-wide cross-roadmap validation and orchestrator readiness tests.

Covers ``validate_cross_roadmap``: external ref resolution across workspaces,
unresolvable refs failing, a dependency cycle spanning two roadmaps, and a
``change_id`` claimed by two roadmaps. Also asserts the orchestrator's
``_get_ready_items`` auto-readiness on external prerequisite completion.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from decomposer import validate_cross_roadmap, validate_roadmap

# The orchestrator lives in autopilot-roadmap/scripts, which the plan-roadmap
# conftest does not add. Make it importable for the readiness test below.
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_ORCH_DIR = str(_SKILLS_DIR / "autopilot-roadmap" / "scripts")
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)

from orchestrator import _get_ready_items  # type: ignore[import-untyped]  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]


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


# ---------------------------------------------------------------------------
# (a) External refs resolve across workspaces; unresolvable ref fails.
# ---------------------------------------------------------------------------
class TestExternalRefResolution:
    def test_resolvable_refs_pass(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01")])
        _write_roadmap(
            tmp_path,
            "beta",
            [
                _item("ri-01", external_depends_on=["alpha:ri-01"]),
                _item("ri-02", superseded_by=["alpha:ri-01"], status="superseded"),
            ],
        )
        assert validate_cross_roadmap(tmp_path) == []

    def test_unknown_roadmap_ref_fails(self, tmp_path):
        _write_roadmap(
            tmp_path, "beta", [_item("ri-01", external_depends_on=["ghost:ri-01"])]
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("ghost" in e and "unknown roadmap" in e for e in errors)

    def test_unknown_item_ref_fails(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01")])
        _write_roadmap(
            tmp_path, "beta", [_item("ri-01", external_depends_on=["alpha:ri-99"])]
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("alpha:ri-99" in e and "does not resolve" in e for e in errors)

    def test_superseded_by_unresolvable_fails(self, tmp_path):
        _write_roadmap(
            tmp_path,
            "beta",
            [_item("ri-01", superseded_by=["alpha:ri-01"], status="superseded")],
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("alpha" in e and "unknown roadmap" in e for e in errors)


# ---------------------------------------------------------------------------
# (b) A cycle spanning two roadmaps is detected.
# ---------------------------------------------------------------------------
class TestCrossRoadmapCycle:
    def test_two_roadmap_cycle_detected(self, tmp_path):
        # alpha:ri-01 -> beta:ri-01 -> alpha:ri-01 via external_depends_on.
        _write_roadmap(
            tmp_path, "alpha", [_item("ri-01", external_depends_on=["beta:ri-01"])]
        )
        _write_roadmap(
            tmp_path, "beta", [_item("ri-01", external_depends_on=["alpha:ri-01"])]
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("cycle" in e.lower() for e in errors)

    def test_acyclic_cross_edges_pass(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01")])
        _write_roadmap(
            tmp_path, "beta", [_item("ri-01", external_depends_on=["alpha:ri-01"])]
        )
        assert validate_cross_roadmap(tmp_path) == []


# ---------------------------------------------------------------------------
# (c) A change_id used by two roadmaps is detected.
# ---------------------------------------------------------------------------
class TestDuplicateChangeId:
    def test_duplicate_change_id_across_roadmaps_detected(self, tmp_path):
        _write_roadmap(tmp_path, "alpha", [_item("ri-01", change_id="add-foo")])
        _write_roadmap(tmp_path, "beta", [_item("ri-01", change_id="add-foo")])
        errors = validate_cross_roadmap(tmp_path)
        assert any("add-foo" in e and "multiple roadmaps" in e for e in errors)

    def test_same_change_id_within_one_roadmap_not_flagged_cross(self, tmp_path):
        # Reusing a change_id inside a single roadmap is not a *cross*-roadmap
        # duplicate; the repo-wide checker stays silent on it.
        _write_roadmap(
            tmp_path,
            "alpha",
            [_item("ri-01", change_id="add-foo"), _item("ri-02", change_id="add-foo")],
        )
        errors = validate_cross_roadmap(tmp_path)
        assert not any("multiple roadmaps" in e for e in errors)

    @pytest.mark.parametrize("ceded_status", ["skipped", "superseded"])
    def test_ceded_item_does_not_claim_its_change_id(self, tmp_path, ceded_status):
        """Ceding ownership must actually resolve the duplicate.

        Regression: the check counted every item regardless of status, so a
        roadmap that marked its copy `skipped` to hand the change to another
        roadmap still tripped the collision — leaving it unresolvable and
        blocking the check from ever becoming a CI gate. Seen live: the
        repo-improvement roadmap ceded four router changes to
        dispatch-governance and validate-repo stayed red.
        """
        _write_roadmap(tmp_path, "owner", [_item("ri-01", change_id="add-foo")])
        _write_roadmap(
            tmp_path,
            "ceder",
            [_item("ri-01", change_id="add-foo", status=ceded_status)],
        )
        assert validate_cross_roadmap(tmp_path) == []

    def test_two_ceded_claims_still_leave_no_owner_conflict(self, tmp_path):
        """Two roadmaps both ceding the same change is not a collision either."""
        _write_roadmap(
            tmp_path, "a", [_item("ri-01", change_id="add-foo", status="skipped")]
        )
        _write_roadmap(
            tmp_path, "b", [_item("ri-01", change_id="add-foo", status="superseded")]
        )
        assert not any("multiple roadmaps" in e for e in validate_cross_roadmap(tmp_path))

    def test_active_duplicate_still_detected_when_a_third_cedes(self, tmp_path):
        """Ceding one copy must not mask a genuine collision between two others."""
        _write_roadmap(tmp_path, "a", [_item("ri-01", change_id="add-foo")])
        _write_roadmap(tmp_path, "b", [_item("ri-01", change_id="add-foo")])
        _write_roadmap(
            tmp_path, "c", [_item("ri-01", change_id="add-foo", status="skipped")]
        )
        errors = validate_cross_roadmap(tmp_path)
        assert any("add-foo" in e and "multiple roadmaps" in e for e in errors)


# ---------------------------------------------------------------------------
# Grammar checks stay inside single-roadmap validation.
# ---------------------------------------------------------------------------
class TestSingleRoadmapGrammar:
    def test_malformed_external_ref_rejected(self):
        # A ref lacking the '<roadmap-id>:<item-id>' shape is rejected — the
        # schema pattern catches it first (surfaces as a "Schema:" error), and
        # the semantic grammar check in validate_roadmap is the backstop.
        data = {
            "schema_version": 1,
            "roadmap_id": "beta",
            "source_proposal": "p.md",
            "status": "approved",
            "policy": {"default_action": "wait_if_budget_exceeded"},
            "items": [_item("ri-01", external_depends_on=["not-a-ref"])],
        }
        errors = validate_roadmap(data, _REPO_ROOT)
        assert errors
        assert any(
            "malformed external_depends_on" in e or e.startswith("Schema:")
            for e in errors
        )

    def test_backward_compatible_no_external_edges(self):
        data = {
            "schema_version": 1,
            "roadmap_id": "beta",
            "source_proposal": "p.md",
            "status": "approved",
            "policy": {"default_action": "wait_if_budget_exceeded"},
            "items": [_item("ri-01")],
        }
        assert validate_roadmap(data, _REPO_ROOT) == []


# ---------------------------------------------------------------------------
# (d) Orchestrator readiness auto-becomes-ready on external completion.
# ---------------------------------------------------------------------------
class _StubCheckpoint:
    completed_items: list[str] = []
    failed_items: list = []


class TestOrchestratorReadiness:
    def test_get_ready_items_honours_external_completed(self):
        from models import Effort, ItemStatus, Roadmap, RoadmapItem

        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="beta",
            source_proposal="p.md",
            items=[
                RoadmapItem(
                    "ri-01",
                    "Blocked on external",
                    ItemStatus.APPROVED,
                    1,
                    Effort.M,
                    external_depends_on=["alpha:ri-09"],
                ),
            ],
        )
        cp = _StubCheckpoint()

        # External prerequisite unmet -> withheld.
        assert _get_ready_items(roadmap, cp, set()) == []
        # Prerequisite completes -> ready, with no status edit on ri-01.
        ready = _get_ready_items(roadmap, cp, {"alpha:ri-09"})
        assert [i.item_id for i in ready] == ["ri-01"]
