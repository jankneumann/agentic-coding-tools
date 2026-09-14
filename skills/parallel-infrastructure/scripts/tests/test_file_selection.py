"""Tests for deterministic file selection (file_selection.py)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import file_selection as fs  # noqa: E402

MODIFIED_DIFF = """diff --git a/src/foo.py b/src/foo.py
index e69de29..a1b2c3d 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,3 @@
 def foo():
+    return 1
     pass
"""

ADDED_DIFF = """diff --git a/src/new_file.py b/src/new_file.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/src/new_file.py
@@ -0,0 +1,2 @@
+def new():
+    pass
"""

DELETED_DIFF = """diff --git a/src/old_file.py b/src/old_file.py
deleted file mode 100644
index e69de29..0000000
--- a/src/old_file.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    pass
"""

RENAMED_DIFF = """diff --git a/src/old_name.py b/src/new_name.py
similarity index 100%
rename from src/old_name.py
rename to src/new_name.py
"""

BINARY_DIFF = """diff --git a/assets/logo.png b/assets/logo.png
index e69de29..a1b2c3d 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
"""


def _lockfile_diff(name: str = "package-lock.json") -> str:
    return (
        f"diff --git a/{name} b/{name}\n"
        f"index e69de29..a1b2c3d 100644\n"
        f"--- a/{name}\n"
        f"+++ b/{name}\n"
        f"@@ -1,1 +1,1 @@\n"
        f"-old\n"
        f"+new\n"
    )


class TestParseDiffFiles:
    def test_empty_diff_yields_no_files(self) -> None:
        assert fs.parse_diff_files("") == []
        assert fs.parse_diff_files("   \n") == []

    def test_modified_file(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        assert len(files) == 1
        assert files[0].path == "src/foo.py"
        assert files[0].status == "modified"
        assert files[0].is_binary is False

    def test_added_file(self) -> None:
        files = fs.parse_diff_files(ADDED_DIFF)
        assert files[0].status == "added"
        assert files[0].path == "src/new_file.py"

    def test_deleted_file_uses_old_path(self) -> None:
        files = fs.parse_diff_files(DELETED_DIFF)
        assert files[0].status == "deleted"
        assert files[0].path == "src/old_file.py"

    def test_renamed_file(self) -> None:
        files = fs.parse_diff_files(RENAMED_DIFF)
        assert files[0].status == "renamed"
        assert files[0].path == "src/new_name.py"
        assert files[0].old_path == "src/old_name.py"

    def test_binary_file_detected(self) -> None:
        files = fs.parse_diff_files(BINARY_DIFF)
        assert files[0].is_binary is True

    def test_multiple_files_in_one_diff(self) -> None:
        combined = MODIFIED_DIFF + ADDED_DIFF + DELETED_DIFF
        files = fs.parse_diff_files(combined)
        assert [f.path for f in files] == [
            "src/foo.py", "src/new_file.py", "src/old_file.py",
        ]


class TestSelectFiles:
    def test_no_file_dropped_without_a_reason(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF + ADDED_DIFF + DELETED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=10_000)
        assert len(decisions) == len(files)
        for d in decisions:
            assert d.reason  # never empty/None

    def test_selected_and_excluded_partition_the_input(self) -> None:
        files = fs.parse_diff_files(
            MODIFIED_DIFF + _lockfile_diff("apps/demo/package-lock.json")
        )
        decisions = fs.select_files(
            files, generated_paths=["**/*.lock", "**/package-lock.json"],
            per_file_token_ceiling=10_000,
        )
        selected = [d for d in decisions if d.selected]
        excluded = [d for d in decisions if not d.selected]
        assert len(selected) == 1
        assert len(excluded) == 1
        assert selected[0].path == "src/foo.py"
        assert excluded[0].path == "apps/demo/package-lock.json"
        assert excluded[0].reason == fs.REASON_GENERATED_PATH

    def test_leading_double_star_also_matches_the_repository_root(self) -> None:
        """`**/package-lock.json` must exclude a root-level lockfile too."""
        files = fs.parse_diff_files(MODIFIED_DIFF + _lockfile_diff("package-lock.json"))
        decisions = fs.select_files(
            files, generated_paths=["**/package-lock.json"],
            per_file_token_ceiling=10_000,
        )
        by_path = {d.path: d for d in decisions}
        assert by_path["package-lock.json"].reason == fs.REASON_GENERATED_PATH
        assert by_path["src/foo.py"].reason == fs.REASON_NONE

    def test_binary_excluded(self) -> None:
        files = fs.parse_diff_files(BINARY_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=10_000)
        assert decisions[0].reason == fs.REASON_BINARY
        assert decisions[0].gate == fs.GATE_BINARY

    def test_user_exclude_wins_over_user_include(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        decisions = fs.select_files(
            files, include=["src/**"], exclude=["src/foo.py"],
            per_file_token_ceiling=10_000,
        )
        assert decisions[0].reason == fs.REASON_USER_EXCLUDE

    def test_user_include_bypasses_generated_path_gate(self) -> None:
        files = fs.parse_diff_files(_lockfile_diff("skills/tests/fixture.lock"))
        decisions = fs.select_files(
            files, include=["skills/tests/**"],
            generated_paths=["**/*.lock"],
            per_file_token_ceiling=10_000,
        )
        assert decisions[0].reason == fs.REASON_NONE
        assert decisions[0].gate == fs.GATE_USER_INCLUDE

    def test_deleted_file_excluded_when_not_included(self) -> None:
        files = fs.parse_diff_files(DELETED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=10_000)
        assert decisions[0].reason == fs.REASON_DELETED
        assert decisions[0].selected is False

    def test_oversized_file_is_too_large(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=1)
        assert decisions[0].reason == fs.REASON_TOO_LARGE

    def test_zero_ceiling_disables_the_too_large_gate(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=0)
        assert decisions[0].reason == fs.REASON_NONE

    def test_gate_order_binary_beats_everything(self) -> None:
        files = fs.parse_diff_files(BINARY_DIFF)
        decisions = fs.select_files(
            files, include=["**/*.png"], per_file_token_ceiling=10_000,
        )
        # Binary is checked first, before user_include could keep it.
        assert decisions[0].reason == fs.REASON_BINARY

    def test_passed_file_carries_gate_passed(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=10_000)
        assert decisions[0].gate == fs.GATE_PASSED
        assert decisions[0].selected is True

    def test_to_dict_shape(self) -> None:
        files = fs.parse_diff_files(MODIFIED_DIFF)
        decisions = fs.select_files(files, per_file_token_ceiling=10_000)
        d = decisions[0].to_dict()
        assert set(d.keys()) == {"path", "status", "reason", "gate", "est_tokens"}


class TestEstimateTokens:
    def test_empty_text_is_zero(self) -> None:
        assert fs.estimate_tokens("") == 0

    def test_rounds_up(self) -> None:
        assert fs.estimate_tokens("abcde") == 2  # ceil(5/4)
        assert fs.estimate_tokens("abcd") == 1
