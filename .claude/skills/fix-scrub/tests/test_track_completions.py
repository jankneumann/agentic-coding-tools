"""Tests for track_completions module."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fix_models import ClassifiedFinding, Finding, FindingOrigin  # noqa: E402
from track_completions import (  # noqa: E402
    _update_deferred_tasks_md,
    _update_tasks_md,
    track_completions,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

SAMPLE_TASKS_MD = """\
# Tasks

## REQ-01: Add widget validation

- [ ] Implement input sanitiser
- [ ] Write unit tests for sanitiser
- [x] Create schema definition (completed by fix-scrub 2026-01-01)
"""

SAMPLE_DEFERRED_TASKS_MD = """\
# Deferred Tasks

- Refactor database connection pooling
- Upgrade HTTP client timeout handling
"""

FROZEN_DATE = "2026-02-21"


def _make_finding(
    *,
    finding_id: str = "F-001",
    source: str = "deferred:open-tasks",
    title: str = "Implement input sanitiser",
    artifact_path: str = "tasks.md",
    change_id: str = "add-bug-scrub-skill",
    origin: FindingOrigin | None = None,
) -> Finding:
    if origin is None:
        origin = FindingOrigin(
            change_id=change_id,
            artifact_path=artifact_path,
        )
    return Finding(
        id=finding_id,
        source=source,
        severity="medium",
        category="deferred-issue",
        title=title,
        origin=origin,
    )


def _make_classified(
    *,
    finding_id: str = "F-001",
    source: str = "deferred:open-tasks",
    title: str = "Implement input sanitiser",
    artifact_path: str = "tasks.md",
    change_id: str = "add-bug-scrub-skill",
    tier: str = "auto",
    origin: FindingOrigin | None = None,
) -> ClassifiedFinding:
    return ClassifiedFinding(
        finding=_make_finding(
            finding_id=finding_id,
            source=source,
            title=title,
            artifact_path=artifact_path,
            change_id=change_id,
            origin=origin,
        ),
        tier=tier,
    )


# ---------------------------------------------------------------------------
# 1. Checkbox update in tasks.md: - [ ] -> - [x] with annotation
# ---------------------------------------------------------------------------


class TestCheckboxUpdate:
    def test_unchecked_becomes_checked_with_annotation(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(SAMPLE_TASKS_MD)

        updated = _update_tasks_md(
            str(tasks_file), "Implement input sanitiser", FROZEN_DATE
        )

        assert updated is True
        content = tasks_file.read_text()
        assert "- [x] Implement input sanitiser (completed by fix-scrub 2026-02-21)" in content

    def test_already_checked_task_is_not_modified(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(SAMPLE_TASKS_MD)

        updated = _update_tasks_md(
            str(tasks_file), "Create schema definition", FROZEN_DATE
        )

        assert updated is False

    def test_only_matching_task_is_checked(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(SAMPLE_TASKS_MD)

        _update_tasks_md(str(tasks_file), "Implement input sanitiser", FROZEN_DATE)

        content = tasks_file.read_text()
        # The other unchecked task should remain unchecked
        assert "- [ ] Write unit tests for sanitiser" in content


# ---------------------------------------------------------------------------
# 2. Deferred-tasks.md resolution annotation
# ---------------------------------------------------------------------------


class TestDeferredTasksAnnotation:
    def test_deferred_task_gets_resolution_annotation(self, tmp_path: Path) -> None:
        deferred_file = tmp_path / "deferred-tasks.md"
        deferred_file.write_text(SAMPLE_DEFERRED_TASKS_MD)

        updated = _update_deferred_tasks_md(
            str(deferred_file),
            "Refactor database connection pooling",
            FROZEN_DATE,
        )

        assert updated is True
        content = deferred_file.read_text()
        assert (
            "- Refactor database connection pooling (resolved by fix-scrub 2026-02-21)"
            in content
        )

    def test_non_matching_entry_is_untouched(self, tmp_path: Path) -> None:
        deferred_file = tmp_path / "deferred-tasks.md"
        deferred_file.write_text(SAMPLE_DEFERRED_TASKS_MD)

        _update_deferred_tasks_md(
            str(deferred_file),
            "Refactor database connection pooling",
            FROZEN_DATE,
        )

        content = deferred_file.read_text()
        assert "- Upgrade HTTP client timeout handling" in content
        assert "resolved" not in content.split("Upgrade HTTP client timeout handling")[1]

    def test_already_resolved_entry_is_not_duplicated(self, tmp_path: Path) -> None:
        deferred_file = tmp_path / "deferred-tasks.md"
        deferred_file.write_text(
            "- Fix timeout (resolved by fix-scrub 2026-02-01)\n"
        )

        updated = _update_deferred_tasks_md(
            str(deferred_file), "Fix timeout", FROZEN_DATE
        )

        assert updated is False


# ---------------------------------------------------------------------------
# 3. Partial completion skip
# ---------------------------------------------------------------------------


class TestPartialCompletionSkip:
    def test_task_with_numbered_sub_items_is_skipped(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(
            "- [ ] Implement validation 1. check input 2. check output\n"
        )

        updated = _update_tasks_md(
            str(tasks_file), "Implement validation", FROZEN_DATE
        )

        assert updated is False
        content = tasks_file.read_text()
        assert "- [ ]" in content

    def test_task_with_semicolons_is_skipped(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(
            "- [ ] Fix errors; handle edge cases; add logging\n"
        )

        updated = _update_tasks_md(
            str(tasks_file), "Fix errors", FROZEN_DATE
        )

        assert updated is False

    def test_task_with_lettered_sub_items_is_skipped(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(
            "- [ ] Validate inputs a) strings b) numbers c) dates\n"
        )

        updated = _update_tasks_md(
            str(tasks_file), "Validate inputs", FROZEN_DATE
        )

        assert updated is False


# ---------------------------------------------------------------------------
# 4. Date formatting in annotations
# ---------------------------------------------------------------------------


class TestDateFormatting:
    def test_date_format_matches_iso_yyyy_mm_dd(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text("- [ ] Do something\n")

        _update_tasks_md(str(tasks_file), "Do something", "2026-12-31")

        content = tasks_file.read_text()
        assert "(completed by fix-scrub 2026-12-31)" in content

    def test_track_completions_uses_utc_date(self, tmp_path: Path) -> None:
        """track_completions derives the date via datetime.now(UTC)."""
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text("- [ ] Run linter\n")

        cf = _make_classified(
            title="Run linter",
            artifact_path=str(tasks_file),
            source="deferred:open-tasks",
        )

        fake_now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "track_completions.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            track_completions([cf], project_dir="")

        content = tasks_file.read_text()
        assert "(completed by fix-scrub 2026-07-04)" in content


# ---------------------------------------------------------------------------
# 5. Finding without origin is skipped
# ---------------------------------------------------------------------------


class TestFindingWithoutOrigin:
    def test_finding_without_origin_is_skipped(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text("- [ ] Do work\n")

        finding_no_origin = Finding(
            id="F-NO-ORIGIN",
            source="deferred:open-tasks",
            severity="medium",
            category="deferred-issue",
            title="Do work",
            origin=None,
        )
        cf = ClassifiedFinding(finding=finding_no_origin, tier="auto")

        updated = track_completions([cf], project_dir=str(tmp_path))

        assert updated == []
        content = tasks_file.read_text()
        assert "- [ ] Do work" in content


# ---------------------------------------------------------------------------
# 6. Missing file is handled gracefully
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_missing_tasks_md_returns_false(self, tmp_path: Path) -> None:
        nonexistent = str(tmp_path / "does-not-exist.md")

        updated = _update_tasks_md(nonexistent, "Any task", FROZEN_DATE)

        assert updated is False

    def test_missing_deferred_tasks_md_returns_false(self, tmp_path: Path) -> None:
        nonexistent = str(tmp_path / "does-not-exist.md")

        updated = _update_deferred_tasks_md(nonexistent, "Any task", FROZEN_DATE)

        assert updated is False

    def test_track_completions_skips_missing_files(self, tmp_path: Path) -> None:
        cf = _make_classified(
            artifact_path="nonexistent/tasks.md",
            source="deferred:open-tasks",
        )

        updated = track_completions([cf], project_dir=str(tmp_path))

        assert updated == []


# ---------------------------------------------------------------------------
# 7. Returns list of updated file paths
# ---------------------------------------------------------------------------


class TestReturnUpdatedPaths:
    def test_returns_paths_of_updated_files(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text("- [ ] Fix bug A\n")

        deferred_file = tmp_path / "deferred-tasks.md"
        deferred_file.write_text("- Resolve flaky test\n")

        cf_tasks = _make_classified(
            finding_id="F-100",
            title="Fix bug A",
            artifact_path=str(tasks_file),
            source="deferred:open-tasks",
        )
        cf_deferred = _make_classified(
            finding_id="F-200",
            title="Resolve flaky test",
            artifact_path=str(deferred_file),
            source="deferred:tasks",
        )

        updated = track_completions(
            [cf_tasks, cf_deferred], project_dir=""
        )

        assert str(tasks_file) in updated
        assert str(deferred_file) in updated
        assert len(updated) == 2

    def test_no_duplicates_for_same_file(self, tmp_path: Path) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text(
            "- [ ] Fix bug A\n- [ ] Fix bug B\n"
        )

        cf1 = _make_classified(
            finding_id="F-100",
            title="Fix bug A",
            artifact_path=str(tasks_file),
            source="deferred:open-tasks",
        )
        cf2 = _make_classified(
            finding_id="F-101",
            title="Fix bug B",
            artifact_path=str(tasks_file),
            source="deferred:open-tasks",
        )

        updated = track_completions([cf1, cf2], project_dir="")

        assert updated.count(str(tasks_file)) == 1

    def test_empty_list_when_nothing_resolved(self, tmp_path: Path) -> None:
        updated = track_completions([], project_dir=str(tmp_path))

        assert updated == []

    def test_impl_findings_source_updates_deferred_file(
        self, tmp_path: Path
    ) -> None:
        impl_file = tmp_path / "impl-findings.md"
        impl_file.write_text("- Handle edge case in parser\n")

        cf = _make_classified(
            finding_id="F-300",
            title="Handle edge case in parser",
            artifact_path=str(impl_file),
            source="deferred:impl-findings",
        )

        updated = track_completions([cf], project_dir="")

        assert str(impl_file) in updated
        content = impl_file.read_text()
        assert "(resolved by fix-scrub" in content
