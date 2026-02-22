"""Tests for the deferred-issue signal collector.

Covers:
  1. impl-findings.md parsing for "out of scope" / "deferred" markers
  2. deferred-tasks.md table parsing
  3. tasks.md checkbox parsing (unchecked ``- [ ]`` items)
  4. Archived vs active severity mapping (active -> medium, archived -> low)
  5. Malformed artifact handling (skip with warning, don't fail)
  6. FindingOrigin metadata population (change_id, artifact_path, etc.)
  7. Empty directories (no changes found)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from collect_deferred import (
    _change_id_from_path,
    _is_archived,
    _parse_table_rows,
    _severity_for,
    collect,
)
from models import Finding, FindingOrigin


# ---------------------------------------------------------------------------
# Helpers — create the openspec/changes/ directory tree inside tmp_path
# ---------------------------------------------------------------------------


def _make_active_change(tmp_path: Path, change_id: str) -> Path:
    """Create ``openspec/changes/<change_id>/`` and return the directory."""
    d = tmp_path / "openspec" / "changes" / change_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_archived_change(tmp_path: Path, change_id: str) -> Path:
    """Create ``openspec/changes/archive/<change_id>/`` and return it."""
    d = tmp_path / "openspec" / "changes" / "archive" / change_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===================================================================
# 1. impl-findings.md — "out of scope" / "deferred" markers
# ===================================================================


class TestImplFindingsParsing:
    """Parse impl-findings.md tables and extract deferred/out-of-scope rows."""

    IMPL_FINDINGS_WITH_DEFERRED = """\
# Implementation Findings

| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Missing error handling | medium | Fixed in commit abc123 |
| 2 | API rate limiting out of scope | high | Deferred to next sprint |
| 3 | CSS alignment issue | low | Fixed |
| 4 | Database migration deferred | medium | Out of scope for this change |
"""

    def test_deferred_rows_are_detected(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "add-auth")
        (change_dir / "impl-findings.md").write_text(self.IMPL_FINDINGS_WITH_DEFERRED)

        result = collect(str(tmp_path))

        assert result.status == "ok"
        # Rows 2 and 4 contain "out of scope" or "deferred"
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 2

    def test_deferred_keyword_case_insensitive(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Uppercase test | low | DEFERRED |
| 2 | Mixed test | low | Out-Of-Scope |
"""
        change_dir = _make_active_change(tmp_path, "case-test")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 2

    def test_out_of_scope_hyphenated(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Perf work | low | out-of-scope for MVP |
"""
        change_dir = _make_active_change(tmp_path, "hyphen-test")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 1

    def test_no_deferred_rows_produces_no_findings(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Fixed the bug | low | Fixed in PR #42 |
"""
        change_dir = _make_active_change(tmp_path, "no-defer")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 0


# ===================================================================
# 2. deferred-tasks.md — table parsing
# ===================================================================


class TestDeferredTasksParsing:
    """Parse deferred-tasks.md tables with migrated task rows."""

    DEFERRED_TASKS = """\
# Deferred Tasks

| # | Original Task | Reason | Migration Target | Files |
|---|--------------|--------|------------------|-------|
| 1 | Add retry logic | Low priority | next-sprint | src/api.py |
| 2 | Refactor auth module | Time constraint | backlog | src/auth.py |
"""

    def test_all_rows_become_findings(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "deferred-work")
        (change_dir / "deferred-tasks.md").write_text(self.DEFERRED_TASKS)

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        assert len(deferred) == 2

    def test_detail_includes_reason_and_migration_target(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "detail-check")
        (change_dir / "deferred-tasks.md").write_text(self.DEFERRED_TASKS)

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        # First row should have reason, migration target, and files
        first = deferred[0]
        assert "Reason: Low priority" in first.detail
        assert "Migration target: next-sprint" in first.detail
        assert "Files: src/api.py" in first.detail

    def test_title_from_original_task_column(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "title-test")
        (change_dir / "deferred-tasks.md").write_text(self.DEFERRED_TASKS)

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        assert deferred[0].title == "Add retry logic"
        assert deferred[1].title == "Refactor auth module"

    def test_empty_table_produces_no_findings(self, tmp_path: Path) -> None:
        content = """\
# Deferred Tasks

| # | Original Task | Reason | Migration Target | Files |
|---|--------------|--------|------------------|-------|
"""
        change_dir = _make_active_change(tmp_path, "empty-table")
        (change_dir / "deferred-tasks.md").write_text(content)

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        assert len(deferred) == 0


# ===================================================================
# 3. tasks.md — unchecked checkbox parsing
# ===================================================================


class TestTasksCheckboxParsing:
    """Parse unchecked ``- [ ]`` items from tasks.md."""

    TASKS_MD = """\
# Tasks

## Phase 1
- [x] 1.1 Set up project structure
- [ ] 1.2 Implement core API
- [x] 1.3 Write initial tests

## Phase 2
- [ ] 2.1 Add caching layer
- [ ] 2.2 Performance benchmarks
- [x] 2.3 Deploy to staging
"""

    def test_unchecked_items_detected(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "task-check")
        (change_dir / "tasks.md").write_text(self.TASKS_MD)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        # Unchecked: 1.2, 2.1, 2.2
        assert len(open_tasks) == 3

    def test_checked_items_ignored(self, tmp_path: Path) -> None:
        content = """\
- [x] Done task 1
- [x] Done task 2
"""
        change_dir = _make_active_change(tmp_path, "all-done")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 0

    def test_task_number_extraction(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "num-extract")
        (change_dir / "tasks.md").write_text(self.TASKS_MD)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]

        # Sort by id to get deterministic order
        open_tasks.sort(key=lambda f: f.id)

        assert open_tasks[0].origin is not None
        assert open_tasks[0].origin.task_number == "1.2"
        assert open_tasks[1].origin is not None
        assert open_tasks[1].origin.task_number == "2.1"
        assert open_tasks[2].origin is not None
        assert open_tasks[2].origin.task_number == "2.2"

    def test_task_without_number(self, tmp_path: Path) -> None:
        content = """\
- [ ] Some task without a number prefix
"""
        change_dir = _make_active_change(tmp_path, "no-num")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 1
        assert open_tasks[0].origin is not None
        assert open_tasks[0].origin.task_number is None
        assert open_tasks[0].title == "Some task without a number prefix"

    def test_line_numbers_tracked(self, tmp_path: Path) -> None:
        content = """\
# Tasks
- [x] Done
- [ ] Open item
"""
        change_dir = _make_active_change(tmp_path, "line-num")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 1
        assert open_tasks[0].origin is not None
        # "# Tasks" is line 1, "- [x] Done" is line 2, "- [ ] Open item" is line 3
        assert open_tasks[0].origin.line_in_artifact == 3


# ===================================================================
# 4. Archived vs active severity mapping
# ===================================================================


class TestSeverityMapping:
    """Active changes -> medium severity; archived changes -> low severity."""

    def test_active_change_gets_medium_severity(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Deferred work | low | deferred |
"""
        change_dir = _make_active_change(tmp_path, "active-sev")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        assert len(result.findings) >= 1
        finding = result.findings[0]
        assert finding.severity == "medium"

    def test_archived_change_gets_low_severity(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Deferred work | low | deferred |
"""
        change_dir = _make_archived_change(tmp_path, "archived-sev")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) >= 1
        assert impl_findings[0].severity == "low"

    def test_mixed_active_and_archived(self, tmp_path: Path) -> None:
        task_content = """\
- [ ] Remaining work item
"""
        active_dir = _make_active_change(tmp_path, "active-mix")
        (active_dir / "tasks.md").write_text(task_content)

        archived_dir = _make_archived_change(tmp_path, "archived-mix")
        (archived_dir / "tasks.md").write_text(task_content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 2

        severities = {f.origin.change_id: f.severity for f in open_tasks if f.origin}
        assert severities["active-mix"] == "medium"
        assert severities["archived-mix"] == "low"

    def test_severity_for_helper(self) -> None:
        assert _severity_for("openspec/changes/foo/tasks.md") == "medium"
        assert _severity_for("openspec/changes/archive/foo/tasks.md") == "low"

    def test_is_archived_helper(self) -> None:
        assert _is_archived("openspec/changes/archive/foo/tasks.md") is True
        assert _is_archived("openspec/changes/foo/tasks.md") is False


# ===================================================================
# 5. Malformed artifact handling
# ===================================================================


class TestMalformedArtifacts:
    """Malformed files should be skipped with a warning, not cause a crash."""

    def test_binary_garbage_in_impl_findings(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "garbage")
        # Write binary-like content that is still valid UTF-8 but not a table
        (change_dir / "impl-findings.md").write_text("not a table\x00\x01\x02\n")

        result = collect(str(tmp_path))
        # Should not raise; no findings from a non-table file
        assert result.status == "ok"
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 0

    def test_unreadable_file_produces_warning(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "unreadable")
        fpath = change_dir / "impl-findings.md"
        fpath.write_text("some content")
        # Make the file unreadable
        fpath.chmod(0o000)

        try:
            result = collect(str(tmp_path))
            assert result.status == "ok"
            # Should have a warning message about being unable to read
            assert any("cannot read" in m for m in result.messages)
        finally:
            # Restore permissions for cleanup
            fpath.chmod(0o644)

    def test_deferred_tasks_with_no_table(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "no-table")
        (change_dir / "deferred-tasks.md").write_text(
            "# Deferred Tasks\n\nNothing here yet.\n"
        )

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        assert len(deferred) == 0
        assert result.status == "ok"

    def test_tasks_md_empty_file(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "empty-file")
        (change_dir / "tasks.md").write_text("")

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 0
        assert result.status == "ok"

    def test_table_with_mismatched_columns(self, tmp_path: Path) -> None:
        """Extra or missing columns should not crash the parser."""
        content = """\
| # | Description |
|---|-------------|
| 1 | Deferred item | extra-col | more-extra |
"""
        change_dir = _make_active_change(tmp_path, "extra-cols")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        # Should not raise — extra columns mapped with col<N> keys
        assert result.status == "ok"


# ===================================================================
# 6. FindingOrigin metadata population
# ===================================================================


class TestFindingOriginMetadata:
    """Each finding must carry correct FindingOrigin metadata."""

    def test_impl_findings_origin(self, tmp_path: Path) -> None:
        content = """\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 42 | Logging deferred | low | Deferred to next cycle |
"""
        change_dir = _make_active_change(tmp_path, "origin-test")
        (change_dir / "impl-findings.md").write_text(content)

        result = collect(str(tmp_path))
        impl_findings = [
            f for f in result.findings if f.source == "deferred:impl-findings"
        ]
        assert len(impl_findings) == 1

        origin = impl_findings[0].origin
        assert origin is not None
        assert origin.change_id == "origin-test"
        assert "openspec/changes/origin-test/impl-findings.md" in origin.artifact_path
        assert origin.task_number == "42"
        assert origin.line_in_artifact is not None

    def test_deferred_tasks_origin(self, tmp_path: Path) -> None:
        content = """\
| # | Original Task | Reason | Migration Target | Files |
|---|--------------|--------|------------------|-------|
| 7 | Add monitoring | Out of time | backlog | src/monitor.py |
"""
        change_dir = _make_active_change(tmp_path, "dt-origin")
        (change_dir / "deferred-tasks.md").write_text(content)

        result = collect(str(tmp_path))
        deferred = [f for f in result.findings if f.source == "deferred:tasks"]
        assert len(deferred) == 1

        origin = deferred[0].origin
        assert origin is not None
        assert origin.change_id == "dt-origin"
        assert "deferred-tasks.md" in origin.artifact_path
        assert origin.task_number == "7"
        assert origin.line_in_artifact is not None

    def test_open_tasks_origin(self, tmp_path: Path) -> None:
        content = """\
# Tasks
- [x] 1.0 Done
- [ ] 1.1 Implement cache invalidation
"""
        change_dir = _make_active_change(tmp_path, "ot-origin")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 1

        origin = open_tasks[0].origin
        assert origin is not None
        assert origin.change_id == "ot-origin"
        assert "tasks.md" in origin.artifact_path
        assert origin.task_number == "1.1"
        assert origin.line_in_artifact == 3

    def test_archived_origin_has_correct_change_id(self, tmp_path: Path) -> None:
        content = """\
- [ ] Ship final docs
"""
        change_dir = _make_archived_change(tmp_path, "2026-01-15-docs-update")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 1

        origin = open_tasks[0].origin
        assert origin is not None
        assert origin.change_id == "2026-01-15-docs-update"
        assert "archive" in origin.artifact_path

    def test_finding_id_format(self, tmp_path: Path) -> None:
        content = """\
- [ ] First open task
- [ ] Second open task
"""
        change_dir = _make_active_change(tmp_path, "id-fmt")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 2
        assert open_tasks[0].id == "deferred-open-tasks-id-fmt-0"
        assert open_tasks[1].id == "deferred-open-tasks-id-fmt-1"

    def test_finding_category_is_deferred_issue(self, tmp_path: Path) -> None:
        content = """\
- [ ] Some unchecked work
"""
        change_dir = _make_active_change(tmp_path, "cat-test")
        (change_dir / "tasks.md").write_text(content)

        result = collect(str(tmp_path))
        for finding in result.findings:
            assert finding.category == "deferred-issue"


# ===================================================================
# 7. Empty directories — no changes found
# ===================================================================


class TestEmptyDirectories:
    """When openspec/changes/ exists but has no artifacts, return ok with no findings."""

    def test_empty_changes_dir(self, tmp_path: Path) -> None:
        (tmp_path / "openspec" / "changes").mkdir(parents=True)

        result = collect(str(tmp_path))
        assert result.status == "ok"
        assert result.source == "deferred"
        assert len(result.findings) == 0

    def test_missing_changes_dir(self, tmp_path: Path) -> None:
        # No openspec/changes/ at all
        result = collect(str(tmp_path))
        assert result.status == "skipped"
        assert any("not found" in m for m in result.messages)

    def test_change_dir_without_artifacts(self, tmp_path: Path) -> None:
        _make_active_change(tmp_path, "empty-change")
        # Directory exists but no .md files inside

        result = collect(str(tmp_path))
        assert result.status == "ok"
        assert len(result.findings) == 0

    def test_archive_dir_without_artifacts(self, tmp_path: Path) -> None:
        _make_archived_change(tmp_path, "empty-archived")

        result = collect(str(tmp_path))
        assert result.status == "ok"
        assert len(result.findings) == 0

    def test_duration_ms_is_populated(self, tmp_path: Path) -> None:
        (tmp_path / "openspec" / "changes").mkdir(parents=True)

        result = collect(str(tmp_path))
        assert result.duration_ms >= 0


# ===================================================================
# Unit tests for internal helpers
# ===================================================================


class TestHelpers:
    """Direct tests for private helper functions."""

    def test_change_id_from_path_active(self) -> None:
        assert _change_id_from_path("openspec/changes/my-change/tasks.md") == "my-change"

    def test_change_id_from_path_archived(self) -> None:
        assert (
            _change_id_from_path("openspec/changes/archive/old-change/tasks.md")
            == "old-change"
        )

    def test_parse_table_rows_basic(self) -> None:
        table = """\
| # | Name | Value |
|---|------|-------|
| 1 | foo  | bar   |
| 2 | baz  | qux   |
"""
        rows = _parse_table_rows(table)
        assert len(rows) == 2
        assert rows[0]["#"] == "1"
        assert rows[0]["name"] == "foo"
        assert rows[0]["value"] == "bar"
        assert rows[1]["#"] == "2"

    def test_parse_table_rows_empty(self) -> None:
        rows = _parse_table_rows("No table here\nJust text\n")
        assert rows == []

    def test_parse_table_rows_skips_separator(self) -> None:
        table = """\
| A | B |
|:---:|:---:|
| 1 | 2 |
"""
        rows = _parse_table_rows(table)
        assert len(rows) == 1
        assert rows[0]["a"] == "1"

    def test_parse_table_rows_skips_blank_rows(self) -> None:
        table = """\
| A | B |
|---|---|
|   |   |
| 1 | 2 |
"""
        rows = _parse_table_rows(table)
        assert len(rows) == 1
        assert rows[0]["a"] == "1"


# ===================================================================
# Integration-style: multiple artifact types in one change
# ===================================================================


class TestMultipleArtifactTypes:
    """A single change can have all three artifact types."""

    def test_all_three_artifact_types_collected(self, tmp_path: Path) -> None:
        change_dir = _make_active_change(tmp_path, "full-change")

        (change_dir / "impl-findings.md").write_text("""\
| # | Description | Severity | Resolution |
|---|-------------|----------|------------|
| 1 | Auth deferred | medium | Deferred |
""")

        (change_dir / "deferred-tasks.md").write_text("""\
| # | Original Task | Reason | Migration Target | Files |
|---|--------------|--------|------------------|-------|
| 1 | Add logging | Time | backlog | log.py |
""")

        (change_dir / "tasks.md").write_text("""\
- [ ] Remaining work
- [x] Completed work
""")

        result = collect(str(tmp_path))
        assert result.status == "ok"

        by_source = {}
        for f in result.findings:
            by_source.setdefault(f.source, []).append(f)

        assert len(by_source["deferred:impl-findings"]) == 1
        assert len(by_source["deferred:tasks"]) == 1
        assert len(by_source["deferred:open-tasks"]) == 1
        assert len(result.findings) == 3

    def test_multiple_changes_aggregated(self, tmp_path: Path) -> None:
        for cid in ("change-a", "change-b", "change-c"):
            d = _make_active_change(tmp_path, cid)
            (d / "tasks.md").write_text("- [ ] Open item\n")

        result = collect(str(tmp_path))
        open_tasks = [f for f in result.findings if f.source == "deferred:open-tasks"]
        assert len(open_tasks) == 3

        change_ids = {f.origin.change_id for f in open_tasks if f.origin}
        assert change_ids == {"change-a", "change-b", "change-c"}
