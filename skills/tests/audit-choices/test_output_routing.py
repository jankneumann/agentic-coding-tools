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

import pytest

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
        # (now, git_sha) are (D7). So the same (now, git_sha) derives the same
        # *base* name regardless of which range is being audited.
        #
        # This asserted `out_a == out_b` until impl-round-1: that is the two
        # distinct audits sharing one directory that D8 exists to prevent, so
        # the test was pinning the very bug codex reported. The base is shared;
        # the directories are not.
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
        base = build_run_id(NOW, GIT_SHA)
        assert out_a.name == base
        assert out_b.name == f"{base}-2"
        assert out_a != out_b, "two distinct audits must not share a run directory"


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


class TestRunIdReservationIsAtomic:
    """impl-round-1 (codex): the guard tested `.exists()` and returned a name,
    but the directory was only really created later inside
    `write_ledger_pair` with `exist_ok=True`. Two range audits started in the
    same UTC second at the same HEAD could both observe the base id free and
    both write to it, which is exactly the snapshot merge D8 exists to
    prevent. The reservation is now the `mkdir(exist_ok=False)` itself."""

    def test_route_creates_the_directory_it_returns(self, tmp_path):
        out = choices_paths.route_output_dir(
            repo_root=tmp_path,
            change_id="range:aaa..bbb",
            now=NOW,
            git_sha=GIT_SHA,
        )
        assert out.is_dir(), "route_output_dir must reserve by creating, not just name"

    def test_a_second_route_in_the_same_second_gets_a_distinct_directory(self, tmp_path):
        first = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id="range:aaa..bbb", now=NOW, git_sha=GIT_SHA
        )
        second = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id="range:ccc..ddd", now=NOW, git_sha=GIT_SHA
        )
        assert first != second
        assert second.name == f"{first.name}-2"
        assert first.is_dir() and second.is_dir()

    def test_a_directory_created_between_check_and_write_does_not_collide(self, tmp_path, monkeypatch):
        """Simulate losing the race: the first candidate appears on disk
        after `_run_id_taken` says it is free. A check-then-write guard
        returns it anyway; an atomic one advances."""
        real_taken = choices_paths._run_id_taken
        root = choices_paths.choices_root_for(tmp_path)

        won = []

        def racing_taken(choices_root, run_id):
            taken = real_taken(choices_root, run_id)
            # The rival wins exactly once. Letting it win every time models a
            # world where no candidate is ever claimable, which is the
            # unbounded-retry case covered separately below.
            if not taken and not won:
                (choices_root / run_id).mkdir(parents=True)
                won.append(run_id)
            return taken

        monkeypatch.setattr(choices_paths, "_run_id_taken", racing_taken)
        out = choices_paths.route_output_dir(
            repo_root=tmp_path, change_id="range:aaa..bbb", now=NOW, git_sha=GIT_SHA
        )
        base = build_run_id(NOW, GIT_SHA)
        assert out.name != base, "took a directory a rival had already created"
        assert out.is_dir()


    def test_unclaimable_root_raises_instead_of_spinning(self, tmp_path, monkeypatch):
        """If every candidate is claimed the instant we look, the loop must
        end. An unbounded `while True` here hangs the audit rather than
        failing it, and the driver's never-raise contract turns a hang into
        a workflow that never finishes."""
        real_taken = choices_paths._run_id_taken

        def always_lose(choices_root, run_id):
            taken = real_taken(choices_root, run_id)
            if not taken:
                (choices_root / run_id).mkdir(parents=True)
            return taken

        monkeypatch.setattr(choices_paths, "_run_id_taken", always_lose)
        monkeypatch.setattr(choices_paths, "_MAX_COLLISION_ATTEMPTS", 5)
        with pytest.raises(RuntimeError, match="could not reserve"):
            choices_paths.route_output_dir(
                repo_root=tmp_path, change_id="range:aaa..bbb", now=NOW, git_sha=GIT_SHA
            )
