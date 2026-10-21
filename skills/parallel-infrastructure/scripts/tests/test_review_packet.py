"""Tool-less review packet for HTTP lanes (openrouter-review-lane, design D6).

HTTP lanes cannot read files, so when the primary packet overflows the budget
(``tools_overflow: true``) ``build_toolless_packet`` builds a second packet
that fits without tools, with its own ``review-packet.toolless.meta.json``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from review_packet import (
    BUDGET_CHARS,
    SPEC_EXCERPT_CHARS,
    TOOLLESS_BODY_NAME,
    TOOLLESS_META_NAME,
    build_review_packet,
    build_toolless_packet,
)
from review_rules import RuleConfig

CHANGE_ID = "demo-change"  # synthetic fixture id, never a real change


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env)


def _blob(tag: str, chars: int) -> str:
    line = f"{tag} " + "x" * 70 + "\n"
    return line * (chars // len(line) + 1)


@pytest.fixture
def overflowing_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A feature branch whose diff is mostly large unrelated files.

    The change's own artifacts are small enough to fit in a tool-less packet;
    the spec delta is longer than ``SPEC_EXCERPT_CHARS`` so a full-text copy
    is distinguishable from an excerpt.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "feature")

    for i in range(3):
        (repo / f"big_{i}.py").write_text(_blob(f"UNRELATED-{i}", 150_000), encoding="utf-8")
    change = repo / "openspec" / "changes" / CHANGE_ID
    (change / "specs" / "widgets").mkdir(parents=True)
    (change / "proposal.md").write_text("# Proposal\n\nPROPOSAL-MARKER\n", encoding="utf-8")
    (change / "design.md").write_text("# Design\n\nDESIGN-MARKER\n", encoding="utf-8")
    (change / "tasks.md").write_text("# Tasks\n\n- [ ] TASKS-MARKER\n", encoding="utf-8")
    spec = "# Spec\n\n" + _blob("SPEC", SPEC_EXCERPT_CHARS + 2_000) + "SPEC-TAIL-MARKER\n"
    (change / "specs" / "widgets" / "spec.md").write_text(spec, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feature")
    return repo, change


def _rules() -> RuleConfig:
    return RuleConfig()


class TestPlanToollessPacket:
    def test_overflowing_branch_yields_fitting_packet_with_full_plan_artifacts(
        self, overflowing_repo, tmp_path: Path,
    ) -> None:
        repo, change = overflowing_repo
        out = tmp_path / "round-1"
        _primary_path, primary = build_review_packet(
            change_id=CHANGE_ID, round_num=1, artifacts_dir=change,
            worktree_path=repo, output_dir=out, rule_config=_rules(),
        )
        assert primary["tools_overflow"] is True

        body_path, meta = build_toolless_packet(
            change_id=CHANGE_ID, review_type="plan", round_num=1,
            artifacts_dir=change, worktree_path=repo, output_dir=out,
            rule_config=_rules(),
        )

        body = body_path.read_text(encoding="utf-8")
        assert body_path.name == TOOLLESS_BODY_NAME
        assert meta["tools_overflow"] is False
        assert len(body) <= BUDGET_CHARS
        for marker in ("PROPOSAL-MARKER", "DESIGN-MARKER", "TASKS-MARKER", "SPEC-TAIL-MARKER"):
            assert marker in body
        assert "UNRELATED-" not in body
        assert "Read/Grep" not in body

        sidecar = json.loads((out / TOOLLESS_META_NAME).read_text(encoding="utf-8"))
        assert sidecar == meta
        assert sidecar["packet_kind"] == "toolless"
        assert sidecar["review_type"] == "plan"
        assert sidecar["body_path"] == TOOLLESS_BODY_NAME
        assert sidecar["coverage"]["skipped"] == []
        # The primary sidecar is left untouched.
        assert json.loads((out / "review-packet.meta.json").read_text())["tools_overflow"] is True

    def test_plan_diff_is_limited_to_the_change_directory(
        self, overflowing_repo, tmp_path: Path,
    ) -> None:
        repo, change = overflowing_repo
        body_path, meta = build_toolless_packet(
            change_id=CHANGE_ID, review_type="plan", round_num=1,
            artifacts_dir=change, worktree_path=repo, output_dir=tmp_path / "o",
            rule_config=_rules(),
        )
        body = body_path.read_text(encoding="utf-8")
        assert f"diff --git a/openspec/changes/{CHANGE_ID}/proposal.md" in body
        assert "diff --git a/big_0.py" not in body
        assert meta["coverage"]["scope"] == f"openspec/changes/{CHANGE_ID}/"

    def test_artifacts_too_large_for_budget_still_flag_tools_overflow(
        self, overflowing_repo, tmp_path: Path,
    ) -> None:
        repo, change = overflowing_repo
        (change / "design.md").write_text(_blob("HUGE", BUDGET_CHARS + 10), encoding="utf-8")
        body_path, meta = build_toolless_packet(
            change_id=CHANGE_ID, review_type="plan", round_num=1,
            artifacts_dir=change, worktree_path=repo, output_dir=tmp_path / "o",
            rule_config=_rules(),
        )
        assert meta["tools_overflow"] is True
        assert len(body_path.read_text(encoding="utf-8")) <= BUDGET_CHARS


class TestImplementationToollessPacket:
    def test_dropped_files_are_listed_in_coverage_skipped(
        self, overflowing_repo, tmp_path: Path,
    ) -> None:
        repo, change = overflowing_repo
        (repo / "package-lock.json").write_text('{"lock": true}\n', encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "lockfile")
        rules = RuleConfig(exclude=["package-lock.json"])

        body_path, meta = build_toolless_packet(
            change_id=CHANGE_ID, review_type="implementation", round_num=1,
            artifacts_dir=change, worktree_path=repo, output_dir=tmp_path / "o",
            rule_config=rules,
        )

        body = body_path.read_text(encoding="utf-8")
        skipped = {entry["path"]: entry["reason"] for entry in meta["coverage"]["skipped"]}
        assert meta["tools_overflow"] is False
        assert len(body) <= BUDGET_CHARS
        assert "package-lock.json" in skipped
        # Three 150k files cannot all fit: at least one is dropped for budget,
        # and no dropped file's content leaks into the body.
        over_budget = [p for p, r in skipped.items() if r == "over_budget"]
        assert over_budget
        for path in over_budget:
            assert f"diff --git a/{path}" not in body
        assert meta["coverage"]["scope"] == "rule_group_selection"
        assert "Read/Grep" not in body
        for path in over_budget:
            assert path in body  # listed as not reviewed, so no finding is expected

    def test_small_diff_skips_nothing(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "--initial-branch=main")
        _git(repo, "config", "commit.gpgsign", "false")
        (repo / "a.py").write_text("a\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        _git(repo, "checkout", "-qb", "feature")
        (repo / "a.py").write_text("a\nb\n", encoding="utf-8")
        _git(repo, "commit", "-qam", "change")
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()

        body_path, meta = build_toolless_packet(
            change_id=CHANGE_ID, review_type="implementation", round_num=1,
            artifacts_dir=artifacts, worktree_path=repo, output_dir=tmp_path / "o",
            rule_config=_rules(),
        )
        assert meta["coverage"]["skipped"] == []
        assert meta["tools_overflow"] is False
        assert "diff --git a/a.py" in body_path.read_text(encoding="utf-8")

    def test_unknown_review_type_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            build_toolless_packet(
                change_id=CHANGE_ID, review_type="validation", round_num=1,
                artifacts_dir=tmp_path, worktree_path=tmp_path, output_dir=tmp_path / "o",
            )
