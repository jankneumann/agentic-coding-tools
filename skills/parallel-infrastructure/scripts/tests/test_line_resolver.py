"""Tests for the ingest-time line resolver (line_resolver.py)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import line_resolver as lr  # noqa: E402

DIFF = """diff --git a/src/foo.py b/src/foo.py
index e69de29..a1b2c3d 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,4 +1,5 @@
 def foo():
-    old_line = 1
+    new_line_one = 1
+    new_line_two = 2
     return None

"""

# A hunk whose target snippet exists only in deleted (old-side) lines.
OLD_SIDE_ONLY_DIFF = """diff --git a/src/bar.py b/src/bar.py
index e69de29..a1b2c3d 100644
--- a/src/bar.py
+++ b/src/bar.py
@@ -1,3 +1,2 @@
 def bar():
-    removed_only_here = True
     return None
"""


def _finding(**overrides) -> dict:
    doc = {
        "id": 1,
        "type": "correctness",
        "criticality": "high",
        "description": "test finding",
        "disposition": "fix",
        "axis": "correctness",
        "severity": "critical",
        "file_path": "src/foo.py",
    }
    doc.update(overrides)
    return doc


class TestParseHunks:
    def test_single_hunk_parsed(self) -> None:
        hunks = lr.parse_hunks(DIFF)
        assert len(hunks) == 1
        h = hunks[0]
        assert h.old_start == 1 and h.new_start == 1
        assert h.old_count == 4 and h.new_count == 5

    def test_lines_have_correct_types(self) -> None:
        hunks = lr.parse_hunks(DIFF)
        types = [line.type for line in hunks[0].lines]
        assert types == [lr.CONTEXT, lr.DELETED, lr.ADDED, lr.ADDED, lr.CONTEXT, lr.CONTEXT, lr.CONTEXT]

    def test_no_hunks_in_headers_only(self) -> None:
        assert lr.parse_hunks("diff --git a/x b/x\n--- a/x\n+++ b/x\n") == []

    def test_stops_at_next_file_header(self) -> None:
        combined = DIFF + "diff --git a/other.py b/other.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"
        hunks = lr.parse_hunks(combined)
        # parse_hunks is meant to receive one file's body; feeding a second
        # file's header stops parsing (mirrors OCR's ParseHunks behavior).
        assert len(hunks) == 1


class TestResolveNewSide:
    def test_snippet_resolves_to_new_side_lines(self) -> None:
        finding = _finding(existing_code="new_line_one = 1\nnew_line_two = 2")
        result = lr.resolve(finding, DIFF)
        assert result["line_range"] == {"start": 2, "end": 3}
        assert result["line_resolution"] == lr.RESOLUTION_HUNK_NEW

    def test_single_line_snippet(self) -> None:
        finding = _finding(existing_code="new_line_one = 1")
        result = lr.resolve(finding, DIFF)
        assert result["line_range"] == {"start": 2, "end": 2}
        assert result["line_resolution"] == lr.RESOLUTION_HUNK_NEW

    def test_snippet_with_diff_markers_stripped(self) -> None:
        finding = _finding(existing_code="+new_line_one = 1\n+new_line_two = 2")
        result = lr.resolve(finding, DIFF)
        assert result["line_range"] == {"start": 2, "end": 3}


class TestResolveOldSide:
    def test_snippet_matches_only_old_side(self) -> None:
        finding = _finding(existing_code="removed_only_here = True", file_path="src/bar.py")
        result = lr.resolve(finding, OLD_SIDE_ONLY_DIFF)
        assert result["line_range"] == {"start": 2, "end": 2}
        assert result["line_resolution"] == lr.RESOLUTION_HUNK_OLD


class TestResolveFileContent:
    def test_resolves_from_full_file_when_not_in_diff(self) -> None:
        finding = _finding(existing_code="line three")
        file_text = "line one\nline two\nline three\nline four\n"
        result = lr.resolve(finding, "", file_text=file_text, files=[])
        assert result["line_range"] == {"start": 3, "end": 3}
        assert result["line_resolution"] == lr.RESOLUTION_FILE


class TestUnresolved:
    def test_unmatched_snippet_is_kept_unresolved(self) -> None:
        finding = _finding(existing_code="this text appears nowhere")
        result = lr.resolve(finding, DIFF)
        assert "line_range" not in result
        assert result["line_resolution"] == lr.RESOLUTION_UNRESOLVED
        # The finding itself is preserved, not dropped.
        assert result["id"] == finding["id"]
        assert result["description"] == finding["description"]

    def test_missing_file_path_is_unresolved(self) -> None:
        finding = _finding(existing_code="new_line_one = 1", file_path="does/not/exist.py")
        result = lr.resolve(finding, DIFF)
        assert result["line_resolution"] == lr.RESOLUTION_UNRESOLVED

    def test_no_existing_code_returns_finding_unchanged(self) -> None:
        finding = _finding()
        finding.pop("existing_code", None)
        result = lr.resolve(finding, DIFF)
        assert "line_resolution" not in result
        assert "line_range" not in result


class TestVendorRangePrecedence:
    def test_vendor_supplied_range_is_kept(self) -> None:
        finding = _finding(
            existing_code="new_line_one = 1",
            line_range={"start": 99, "end": 99},
        )
        result = lr.resolve(finding, DIFF)
        assert result["line_range"] == {"start": 99, "end": 99}
        assert result["line_resolution"] == lr.RESOLUTION_VENDOR

    def test_zero_line_range_is_not_treated_as_vendor_supplied(self) -> None:
        finding = _finding(
            existing_code="new_line_one = 1",
            line_range={"start": 0, "end": 0},
        )
        result = lr.resolve(finding, DIFF)
        # 0/0 means "no position", same convention as OCR's positioning
        # failure signal — resolution proceeds as if unresolved.
        assert result["line_range"] == {"start": 2, "end": 2}
        assert result["line_resolution"] == lr.RESOLUTION_HUNK_NEW

    def test_existing_resolution_marker_is_not_overwritten(self) -> None:
        finding = _finding(
            line_range={"start": 5, "end": 5}, line_resolution="hunk_new",
        )
        result = lr.resolve(finding, DIFF)
        assert result["line_resolution"] == "hunk_new"


class TestResolveAll:
    def test_resolves_every_finding_and_counts_unanchored(self) -> None:
        findings = [
            _finding(id=1, existing_code="new_line_one = 1"),
            _finding(id=2, existing_code="nowhere to be found"),
        ]
        resolved, unanchored = lr.resolve_all(findings, DIFF)
        assert len(resolved) == 2
        assert unanchored == 1
        assert resolved[0]["line_resolution"] == lr.RESOLUTION_HUNK_NEW
        assert resolved[1]["line_resolution"] == lr.RESOLUTION_UNRESOLVED

    def test_findings_without_existing_code_do_not_count_as_unanchored(self) -> None:
        findings = [_finding(id=1)]
        findings[0].pop("existing_code", None)
        _resolved, unanchored = lr.resolve_all(findings, DIFF)
        assert unanchored == 0


class TestFindFileDiff:
    def test_matches_by_new_path(self) -> None:
        from file_selection import parse_diff_files

        files = parse_diff_files(DIFF)
        found = lr.find_file_diff(files, "src/foo.py")
        assert found is not None
        assert found.path == "src/foo.py"

    def test_returns_none_when_absent(self) -> None:
        from file_selection import parse_diff_files

        files = parse_diff_files(DIFF)
        assert lr.find_file_diff(files, "src/missing.py") is None
