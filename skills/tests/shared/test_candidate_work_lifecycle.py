"""Lifecycle-aware dependency resolution shared by ranking and intake."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED = REPO_ROOT / "skills" / "shared"
sys.path.insert(0, str(SHARED))

from candidate_work import (  # noqa: E402
    DependencyResolution,
    LifecycleRecord,
    group_lifecycle_records,
    resolve_dependency,
)


def _record(
    source: str,
    status: str,
    *,
    change_id: str = "update-retry-policy",
    roadmap_id: str | None = None,
    item_id: str | None = None,
) -> LifecycleRecord:
    return LifecycleRecord(
        change_id=change_id,
        source=source,
        status=status,
        roadmap_id=roadmap_id,
        item_id=item_id,
    )


def test_grouping_uses_exact_change_ids_and_deterministic_record_order() -> None:
    records = [
        _record("candidate", "candidate", change_id="update-retry-policy-v2"),
        _record("archive", "completed"),
        _record("roadmap", "completed", roadmap_id="runtime", item_id="ri-02"),
    ]

    grouped = group_lifecycle_records(reversed(records))

    assert list(grouped) == ["update-retry-policy", "update-retry-policy-v2"]
    assert [record.source for record in grouped["update-retry-policy"]] == [
        "archive",
        "roadmap",
    ]


@pytest.mark.parametrize("source", ["roadmap", "archive"])
def test_completed_roadmap_or_archive_records_satisfy(source: str) -> None:
    resolution = resolve_dependency(
        "update-retry-policy", [_record(source, "completed")]
    )

    assert resolution == DependencyResolution(
        change_id="update-retry-policy",
        outcome="satisfied",
        live_record=None,
        matches=(_record(source, "completed"),),
        reason="all matching lifecycle records are completed",
    )


@pytest.mark.parametrize("status", ["failed", "skipped", "superseded"])
def test_non_completed_terminal_records_are_unresolved(status: str) -> None:
    resolution = resolve_dependency(
        "update-retry-policy", [_record("roadmap", status)]
    )

    assert resolution.outcome == "unresolved"
    assert "not completed" in resolution.reason


def test_completed_and_failed_terminal_records_are_not_treated_as_satisfied() -> None:
    resolution = resolve_dependency(
        "update-retry-policy",
        [_record("archive", "completed"), _record("roadmap", "failed")],
    )

    assert resolution.outcome == "unresolved"


def test_active_change_and_its_single_roadmap_item_collapse_to_one_live_lineage() -> None:
    roadmap = _record(
        "roadmap", "in_progress", roadmap_id="runtime", item_id="ri-07"
    )

    resolution = resolve_dependency(
        "update-retry-policy", [_record("active_change", "active"), roadmap]
    )

    assert resolution.outcome == "live"
    assert resolution.live_record == roadmap
    assert resolution.reason == "active change is represented by one live roadmap item"


def test_active_change_without_a_roadmap_item_is_unresolved() -> None:
    resolution = resolve_dependency(
        "update-retry-policy", [_record("active_change", "active")]
    )

    assert resolution.outcome == "unresolved"
    assert "without a live roadmap item" in resolution.reason


def test_multiple_live_roadmap_owners_are_ambiguous() -> None:
    resolution = resolve_dependency(
        "update-retry-policy",
        [
            _record("roadmap", "approved", roadmap_id="one", item_id="ri-01"),
            _record("roadmap", "blocked", roadmap_id="two", item_id="ri-03"),
        ],
    )

    assert resolution.outcome == "ambiguous"
    assert resolution.live_record is None


def test_live_candidate_and_roadmap_owners_are_ambiguous() -> None:
    resolution = resolve_dependency(
        "update-retry-policy",
        [
            _record("candidate", "candidate"),
            _record("roadmap", "approved", roadmap_id="one", item_id="ri-01"),
        ],
    )

    assert resolution.outcome == "ambiguous"


def test_completed_history_does_not_hide_one_live_owner() -> None:
    live = _record("candidate", "candidate")

    resolution = resolve_dependency(
        "update-retry-policy", [_record("archive", "completed"), live]
    )

    assert resolution.outcome == "live"
    assert resolution.live_record == live


def test_unknown_exact_change_id_is_unresolved() -> None:
    resolution = resolve_dependency(
        "update-retry-policy",
        [_record("roadmap", "completed", change_id="update-retry-policy-v2")],
    )

    assert resolution.outcome == "unresolved"
    assert resolution.matches == ()


def test_shared_collector_reads_legacy_archived_roadmap_lifecycle(
    tmp_path: Path,
) -> None:
    import candidate_work as runtime

    archived = tmp_path / "openspec/roadmaps/archive/legacy/roadmap.yaml"
    archived.parent.mkdir(parents=True)
    archived.write_text(
        "roadmap_id: legacy\n"
        "items:\n"
        "  - item_id: ri-07\n"
        "    change_id: add-legacy\n"
        "    status: completed\n",
        encoding="utf-8",
    )
    (tmp_path / "openspec/changes/add-live").mkdir(parents=True)
    (tmp_path / "openspec/changes/archive/2026-09-13-add-done").mkdir(
        parents=True
    )

    records = runtime.collect_lifecycle_records(tmp_path)

    assert LifecycleRecord(
        "add-legacy", "roadmap", "completed", "legacy", "ri-07"
    ) in records
    assert LifecycleRecord("add-live", "active_change", "active") in records
    assert LifecycleRecord("add-done", "archive", "completed") in records


def test_shared_collector_rejects_unknown_roadmap_item_status(
    tmp_path: Path,
) -> None:
    import candidate_work as runtime

    roadmap = tmp_path / "openspec/roadmaps/runtime/roadmap.yaml"
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "roadmap_id: runtime\n"
        "items:\n"
        "  - item_id: ri-01\n"
        "    change_id: add-runtime\n"
        "    status: awaiting_oracle\n",
        encoding="utf-8",
    )

    with pytest.raises(
        runtime.LifecycleCollectionError,
        match=r"unknown roadmap item status 'awaiting_oracle'",
    ):
        runtime.collect_lifecycle_records(tmp_path)
