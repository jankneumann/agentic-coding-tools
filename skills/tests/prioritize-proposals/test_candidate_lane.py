from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills/prioritize-proposals/scripts"
sys.path.insert(0, str(SCRIPTS))

from candidate_lane import (  # noqa: E402
    CandidateLaneError,
    CandidateRanking,
    LifecycleRecord,
    load_and_rank_candidate_work,
    load_candidate_inputs,
    rank_candidate_work,
    render_candidate_markdown,
)


def _candidate(
    change_id: str,
    *,
    priority: int = 3,
    effort: str = "M",
    generator: str | None = "bug-scrub",
    depends_on: list[str] | None = None,
    title: str | None = None,
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "source_artifact": f"reports/{change_id}.json",
        "finding_ids": [f"finding-{change_id}"],
    }
    if generator is not None:
        provenance["generator"] = generator
    return {
        "schema_version": 1,
        "title": title or change_id,
        "description": f"Implement {change_id}.",
        "rationale": f"Evidence for {change_id}.",
        "provenance": provenance,
        "effort": effort,
        "priority": priority,
        "suggested_change_id": change_id,
        "depends_on": depends_on or [],
        "tags": ["candidate"],
    }


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_repeatable_inputs_validate_and_concatenate_in_file_order(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "one.json",
        [
            _candidate("add-bug", generator="bug-scrub"),
            _candidate("add-hand", generator=None),
        ],
    )
    second = _write(
        tmp_path / "two.json",
        _candidate("add-improve", generator="improve-harness"),
    )
    third = _write(
        tmp_path / "three.json",
        [_candidate("add-explore", generator="explore-feature")],
    )

    loaded = load_candidate_inputs([first, second, third])

    assert [item["suggested_change_id"] for item in loaded] == [
        "add-bug",
        "add-hand",
        "add-improve",
        "add-explore",
    ]


def test_mixed_candidates_rank_once_with_stable_empty_generator_tie() -> None:
    candidates = [
        _candidate("add-improve", priority=2, effort="S", generator="improve-harness"),
        _candidate("add-bug", priority=2, effort="S", generator="bug-scrub"),
        _candidate("add-hand", priority=2, effort="S", generator=None),
        _candidate("add-explore", priority=2, effort="S", generator="explore-feature"),
    ]

    first = rank_candidate_work(candidates)
    second = rank_candidate_work(list(reversed(candidates)))

    expected = ["add-hand", "add-bug", "add-explore", "add-improve"]
    assert isinstance(first, CandidateRanking)
    assert [item.change_id for item in first.items] == expected
    assert [item.change_id for item in second.items] == expected
    assert len({item.change_id for item in first.items}) == len(candidates)
    assert first.items[0].candidate["provenance"]["finding_ids"] == [
        "finding-add-hand"
    ]
    assert all(item.lane == "candidate_work" for item in first.items)


def test_kahn_order_and_blocked_status_propagate_without_breaking_edges() -> None:
    candidates = [
        _candidate("add-dependent", priority=1, effort="XS", depends_on=["add-base"]),
        _candidate("add-base", priority=5, effort="XL"),
        _candidate("add-ready", priority=2, effort="M"),
        _candidate("add-blocked", priority=1, effort="XS", depends_on=["add-unknown"]),
        _candidate("add-blocked-child", priority=1, effort="XS", depends_on=["add-blocked"]),
        _candidate("add-satisfied", priority=3, effort="M", depends_on=["add-done"]),
        _candidate("add-live-blocked", priority=1, effort="XS", depends_on=["add-live"]),
    ]
    lifecycle = [
        LifecycleRecord("add-done", "roadmap", "completed", "history", "ri-01"),
        LifecycleRecord("add-done", "archive", "completed"),
        LifecycleRecord("add-live", "roadmap", "approved", "other", "ri-02"),
        LifecycleRecord("add-live", "active_change", "active"),
    ]

    result = rank_candidate_work(candidates, lifecycle_records=lifecycle)

    ids = [item.change_id for item in result.items]
    assert ids.index("add-base") < ids.index("add-dependent")
    assert ids.index("add-blocked") < ids.index("add-blocked-child")
    ready_positions = [i for i, item in enumerate(result.items) if not item.blocked]
    blocked_positions = [i for i, item in enumerate(result.items) if item.blocked]
    assert max(ready_positions) < min(blocked_positions)
    by_id = {item.change_id: item for item in result.items}
    assert not by_id["add-satisfied"].blocked
    assert by_id["add-blocked"].blocked
    assert by_id["add-blocked-child"].blocked
    assert by_id["add-live-blocked"].blocked
    assert "add-unknown" in " ".join(by_id["add-blocked"].blocked_reasons)
    assert "add-blocked" in " ".join(by_id["add-blocked-child"].blocked_reasons)
    assert "add-live" in " ".join(by_id["add-live-blocked"].blocked_reasons)


def test_repository_lifecycle_scan_collapses_lineage_and_completed_duplicates(
    tmp_path: Path,
) -> None:
    roadmap_path = tmp_path / "openspec/roadmaps/work/roadmap.yaml"
    roadmap_path.parent.mkdir(parents=True)
    roadmap_path.write_text(
        json.dumps(
            {
                "roadmap_id": "work",
                "items": [
                    {
                        "item_id": "ri-01",
                        "change_id": "add-live",
                        "status": "approved",
                    },
                    {
                        "item_id": "ri-02",
                        "change_id": "add-done",
                        "status": "completed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "openspec/changes/add-live").mkdir(parents=True)
    (tmp_path / "openspec/changes/archive/2026-09-13-add-done").mkdir(
        parents=True
    )
    candidates = _write(
        tmp_path / "candidates.json",
        [
            _candidate("add-needs-live", depends_on=["add-live"]),
            _candidate("add-needs-done", depends_on=["add-done"]),
        ],
    )

    result = load_and_rank_candidate_work([candidates], repo_root=tmp_path)

    by_id = {item.change_id: item for item in result.items}
    assert by_id["add-needs-live"].blocked
    assert not by_id["add-needs-done"].blocked


def test_effort_is_part_of_the_stable_tie_key() -> None:
    candidates = [
        _candidate("add-large", priority=2, effort="L"),
        _candidate("add-small", priority=2, effort="S"),
        _candidate("add-extra-small", priority=2, effort="XS"),
    ]

    result = rank_candidate_work(candidates)

    assert [item.change_id for item in result.items] == [
        "add-extra-small",
        "add-small",
        "add-large",
    ]


def test_malformed_member_refuses_complete_multi_file_load_with_index(
    tmp_path: Path,
) -> None:
    good = _write(tmp_path / "good.json", [_candidate("add-good")])
    malformed = _candidate("add-bad")
    del malformed["title"]
    bad = _write(tmp_path / "bad.json", [malformed])

    with pytest.raises(ValueError) as exc_info:
        load_candidate_inputs([good, bad])

    assert "item #1" in str(exc_info.value)
    assert "title" in str(exc_info.value)


def test_duplicate_union_cycle_and_multiple_live_dependency_fail_closed(
    tmp_path: Path,
) -> None:
    one = _write(tmp_path / "one.json", [_candidate("add-duplicate")])
    two = _write(tmp_path / "two.json", [_candidate("add-duplicate")])
    with pytest.raises(ValueError, match="duplicate suggested_change_id"):
        load_candidate_inputs([one, two])

    cycle = [
        _candidate("add-a", depends_on=["add-b"]),
        _candidate("add-b", depends_on=["add-a"]),
    ]
    with pytest.raises(CandidateLaneError) as cycle_error:
        rank_candidate_work(cycle)
    assert "add-a" in str(cycle_error.value)
    assert "add-b" in str(cycle_error.value)

    ambiguous = [_candidate("add-owner", depends_on=["add-shared"])]
    lifecycle = [
        LifecycleRecord("add-shared", "roadmap", "approved", "one", "ri-01"),
        LifecycleRecord("add-shared", "roadmap", "in_progress", "two", "ri-02"),
    ]
    with pytest.raises(CandidateLaneError, match="add-shared"):
        rank_candidate_work(ambiguous, lifecycle_records=lifecycle)


def test_duplicate_candidates_fail_even_for_programmatic_call() -> None:
    candidates = [_candidate("add-duplicate"), _candidate("add-duplicate")]

    with pytest.raises(CandidateLaneError, match="add-duplicate"):
        rank_candidate_work(candidates)


def test_markdown_rendering_keeps_candidate_text_inert() -> None:
    candidate = _candidate(
        "add-inert",
        title="[click](javascript:alert(1))\x1b[31m \u009b \u202e \u2028 \u2029 **owned**",
    )
    candidate["rationale"] = "run `touch /tmp/pwned` | <script>alert(1)</script>"
    candidate["provenance"]["source_artifact"] = (
        "https://example.invalid/$(touch-/tmp/provenance)"
    )
    candidate["tags"] = ["**bold**", "[link](file:///etc/passwd)"]

    rendered = render_candidate_markdown(rank_candidate_work([candidate]))

    assert "[click](javascript:" not in rendered
    assert "<script>" not in rendered
    assert "\u009b" not in rendered
    assert "\u202e" not in rendered
    assert "\u2028" not in rendered
    assert "\u2029" not in rendered
    assert "\\u2028" in rendered
    assert "\\u2029" in rendered
    assert "\x1b" not in rendered
    assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in rendered
    assert "\\<script\\>" in rendered
    assert "https://example\\.invalid/" in rendered
    assert "\\*\\*bold\\*\\*" in rendered


def test_markdown_change_id_code_span_has_no_literal_backslash_escapes() -> None:
    candidate = _candidate("update-auth-token-refresh")

    rendered = render_candidate_markdown(rank_candidate_work([candidate]))

    assert "- **Change ID**: `update-auth-token-refresh`" in rendered
    assert "`update\\-auth\\-token\\-refresh`" not in rendered


def test_cli_accepts_repeatable_candidate_work_and_keeps_lane_distinct(
    tmp_path: Path,
) -> None:
    first = _write(tmp_path / "first.json", [_candidate("add-z", priority=4)])
    second = _write(tmp_path / "second.json", _candidate("add-a", priority=1))

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "candidate_lane.py"),
            "--candidate-work",
            str(first),
            "--candidate-work",
            str(second),
            "--repo-root",
            str(tmp_path),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["lane"] == "candidate_work"
    assert payload["count"] == 2
    assert [item["candidate"]["suggested_change_id"] for item in payload["candidates"]] == [
        "add-a",
        "add-z",
    ]
