"""Tests for the audit-choices destination-routing helper
(skills/audit-choices/scripts/choices_paths.py). Design D1, D5, D7, D8.

The routing decision is kept as a single, directly-testable function per
D5: a `range:`-prefixed recorded change_id routes to a dated run directory
under `openspec/choices/`; everything else routes to
`openspec/changes/<change-id>/`, unchanged.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT / "skills"))

import choices_paths  # noqa: E402
from shared.artifact_paths import build_run_id, parse_run_id, run_id_suffix  # noqa: E402

NOW = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)
GIT_SHA = "abc1234" + "0" * 33  # 40 chars, short form starts abc1234


class TestChangeIdFormRoutesToChangesTree:
    def test_ordinary_change_id_routes_unchanged(self, tmp_path: Path):
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id="my-change", now=NOW, git_sha=GIT_SHA
        )
        assert out == tmp_path / "openspec" / "changes" / "my-change"

    def test_id_containing_dotdot_or_colon_but_not_range_prefixed_routes_unchanged(
        self, tmp_path: Path
    ):
        # D5: the test is on the *prefix of the recorded id*, not on the
        # shape of the argument.
        weird_id = "abc1234..def5678:not-a-range-prefix"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=weird_id, now=NOW, git_sha=GIT_SHA
        )
        assert out == tmp_path / "openspec" / "changes" / weird_id


class TestRangeFormRoutesToChoicesRoot:
    def test_range_id_routes_to_dated_run_directory(self, tmp_path: Path):
        base_sha = "0" * 40
        head_sha = "1" * 40
        change_id = f"range:{base_sha}..{head_sha}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        expected_run_id = build_run_id(NOW, GIT_SHA)
        assert out == tmp_path / "openspec" / "choices" / expected_run_id

    def test_directory_name_equals_build_run_id_of_driver_now_and_git_sha(
        self, tmp_path: Path
    ):
        # D7: pinned on the driver's resolved_now/resolved_git_sha — the same
        # two values make_header receives — never a header run_id or the
        # audited head_sha.
        change_id = "range:" + "0" * 40 + ".." + "9" * 40
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        assert out.name == build_run_id(NOW, GIT_SHA)

    def test_header_run_id_and_audited_head_sha_have_no_effect_on_directory_name(
        self, tmp_path: Path
    ):
        # The caller's --run-id (e.g. "iterate-on-implementation-...") and the
        # audited head_sha are not inputs to route_output_dir at all — only
        # (now, git_sha) are. Calling with the same (now, git_sha) but a
        # completely different audited range produces the same directory.
        out_a = choices_paths.route_output_dir(
            repo_root=tmp_path,
            change_id=f"range:{'a' * 40}..{'b' * 40}",
            now=NOW,
            git_sha=GIT_SHA,
        )
        out_b = choices_paths.route_output_dir(
            repo_root=tmp_path,
            change_id=f"range:{'c' * 40}..{'d' * 40}",
            now=NOW,
            git_sha=GIT_SHA,
        )
        assert out_a == out_b


class TestCollisionGuard:
    def test_existing_active_directory_gets_suffixed_sibling(self, tmp_path: Path):
        base_run_id = build_run_id(NOW, GIT_SHA)
        choices_root = tmp_path / "openspec" / "choices"
        (choices_root / base_run_id).mkdir(parents=True)

        change_id = f"range:{'a' * 40}..{'b' * 40}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        assert out.name == f"{base_run_id}-2"

    def test_second_collision_advances_to_dash_3(self, tmp_path: Path):
        base_run_id = build_run_id(NOW, GIT_SHA)
        choices_root = tmp_path / "openspec" / "choices"
        (choices_root / base_run_id).mkdir(parents=True)
        (choices_root / f"{base_run_id}-2").mkdir(parents=True)

        change_id = f"range:{'a' * 40}..{'b' * 40}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        assert out.name == f"{base_run_id}-3"

    def test_suffixed_name_still_satisfies_parse_run_id(self, tmp_path: Path):
        base_run_id = build_run_id(NOW, GIT_SHA)
        choices_root = tmp_path / "openspec" / "choices"
        (choices_root / base_run_id).mkdir(parents=True)

        change_id = f"range:{'a' * 40}..{'b' * 40}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        # Must not raise -- an un-extended RUN_ID_RE would reject this and
        # make list_active_runs skip exactly the directories this guard
        # creates, letting the tree grow unbounded. parse_run_id's 3-tuple
        # is unaffected by the suffix; run_id_suffix reads it separately.
        assert parse_run_id(out.name) == parse_run_id(base_run_id)
        assert run_id_suffix(out.name) == "2"

    def test_rejects_a_name_that_exists_only_under_archive(self, tmp_path: Path):
        # Retention frees the active path while the archived copy persists;
        # a later audit computing that same base would otherwise collide
        # with the archived directory on the next retention pass (D8).
        base_run_id = build_run_id(NOW, GIT_SHA)
        choices_root = tmp_path / "openspec" / "choices"
        (choices_root / "archive" / base_run_id).mkdir(parents=True)

        change_id = f"range:{'a' * 40}..{'b' * 40}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        assert out.name == f"{base_run_id}-2"

    def test_rejects_active_and_archive_together_advances_past_both(self, tmp_path: Path):
        base_run_id = build_run_id(NOW, GIT_SHA)
        choices_root = tmp_path / "openspec" / "choices"
        (choices_root / base_run_id).mkdir(parents=True)
        (choices_root / "archive" / f"{base_run_id}-2").mkdir(parents=True)

        change_id = f"range:{'a' * 40}..{'b' * 40}"
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id=change_id, now=NOW, git_sha=GIT_SHA
        )
        assert out.name == f"{base_run_id}-3"
