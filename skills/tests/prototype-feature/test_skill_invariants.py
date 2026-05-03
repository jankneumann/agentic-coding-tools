"""Skill-level invariants for /prototype-feature.

These tests cover the *properties* the SKILL.md workflow guarantees,
without dispatching real Task() agents:

  4.2 — isolated worktree per variant: the plan produces non-overlapping
        worktree paths and branches; the per-variant agent prompt
        (step 4 in SKILL.md) sandboxes writes to its own branch.
  4.4 — scoring: SKILL.md step 5 invokes ``/validate-feature --phase
        smoke,spec`` only — never deploy / e2e / security on skeletons.

End-to-end coverage of the actual dispatch + scoring pipeline is the
job of wp-integration (task 8.1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[2] / "prototype-feature"
SKILL_SCRIPTS = SKILL_DIR / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from dispatch_variants import plan_variants


class TestIsolationProperty:
    """4.2: each variant's writable footprint is disjoint from peers."""

    def test_variant_branches_are_distinct(self) -> None:
        plan = plan_variants(change_id="add-foo")
        branches = {v.branch for v in plan.variants}
        assert len(branches) == len(plan.variants), (
            "variants must land on distinct branches; otherwise commits "
            "from different agents would clobber each other"
        )

    def test_variant_worktrees_are_distinct(self) -> None:
        plan = plan_variants(change_id="add-foo")
        paths = {v.worktree_relpath for v in plan.variants}
        assert len(paths) == len(plan.variants), (
            "variants must occupy distinct worktree directories"
        )

    def test_variant_worktrees_nested_under_change(self) -> None:
        # All variant worktrees live under .git-worktrees/<change-id>/
        # so /cleanup-feature can find them by directory glob.
        plan = plan_variants(change_id="add-foo")
        for v in plan.variants:
            assert v.worktree_relpath.startswith(".git-worktrees/add-foo/"), (
                f"variant worktree path {v.worktree_relpath} not under the "
                "change-id directory; cleanup-feature would miss it"
            )

    def test_variant_branches_share_prototype_namespace(self) -> None:
        # All variant branches live under prototype/<change-id>/ so
        # cleanup-feature's branch-pattern delete works (D4).
        plan = plan_variants(change_id="add-foo")
        for v in plan.variants:
            assert v.branch.startswith("prototype/add-foo/"), (
                f"variant branch {v.branch} outside prototype namespace; "
                "cleanup-feature pattern delete would skip it"
            )


class TestScoringInvariants:
    """4.4: SKILL.md step 5 limits scoring to smoke + spec phases (D6)."""

    def test_skill_doc_references_only_cheap_phases(self) -> None:
        # Read the SKILL.md and assert it requests only --phase smoke,spec.
        # Heavy phases (deploy, e2e, security) on incomplete skeletons would
        # be wasteful at best and misleading at worst.
        skill_md = (SKILL_DIR / "SKILL.md").read_text()

        # Positive: smoke,spec must be invoked
        assert "--phase smoke,spec" in skill_md, (
            "SKILL.md must request the smoke,spec validation phases for "
            "scoring per D6"
        )

        # Negative: heavy phases must not appear in the scoring step.
        # (They may legitimately appear elsewhere in prose, so we narrow to
        # the line that contains the validate-feature invocation.)
        invocation_lines = [
            line for line in skill_md.splitlines()
            if "/validate-feature" in line and "--phase" in line
        ]
        assert invocation_lines, "no /validate-feature --phase invocation found"
        for line in invocation_lines:
            for heavy in ("deploy", "e2e", "security"):
                assert heavy not in line, (
                    f"SKILL.md scoring step references heavy phase {heavy!r} "
                    f"on line: {line.strip()!r}. Skeletons should not run heavy phases."
                )


class TestAngleAssignmentDeterministic:
    """Angles are assigned by index — same flags ⇒ same plan, always."""

    def test_same_inputs_yield_same_plan(self) -> None:
        plan_a = plan_variants(change_id="add-foo")
        plan_b = plan_variants(change_id="add-foo")
        assert [v.variant_id for v in plan_a.variants] == [
            v.variant_id for v in plan_b.variants
        ]
        assert [v.angle for v in plan_a.variants] == [
            v.angle for v in plan_b.variants
        ]
        assert [v.branch for v in plan_a.variants] == [
            v.branch for v in plan_b.variants
        ]
