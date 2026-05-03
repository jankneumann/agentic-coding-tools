"""Unit tests for dispatch_variants helper logic.

Covered tasks:
  4.1 — variant count validation, angle-count matching, out-of-bounds
  4.3 — vendor diversity policy (sufficient / insufficient / recorded)

These tests exercise the planning/validation surface of
``dispatch_variants.py``. They DO NOT exercise the actual Task() agent
dispatch — that's covered by the wp-integration end-to-end test at the
end of the work-package DAG.

Spec scenarios:
- skill-workflow.PrototypeFeatureSkill.default-variant-dispatch,
  custom-variant-count-and-angles, variant-count-out-of-bounds
- skill-workflow.VendorDiversityPolicy.sufficient, insufficient, recorded
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "prototype-feature"
    / "scripts"
)
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from dispatch_variants import (
    DEFAULT_ANGLES,
    MAX_VARIANTS,
    MIN_VARIANTS,
    VariantPlan,
    VariantPlanError,
    plan_variants,
    resolve_vendor_assignment,
)


class TestVariantCountBounds:
    """Spec: PrototypeFeatureSkill.variant-count-out-of-bounds + default-dispatch."""

    def test_default_count_is_three(self) -> None:
        # Spec scenario default-variant-dispatch — no flags → 3 variants.
        plan = plan_variants(change_id="add-foo")
        assert len(plan.variants) == 3
        assert [v.variant_id for v in plan.variants] == ["v1", "v2", "v3"]

    def test_count_two_accepted(self) -> None:
        # N=2 is in-bounds; explicit angles required because DEFAULT_ANGLES
        # only covers N=3 and silently dropping one would be ambiguous.
        plan = plan_variants(
            change_id="add-foo",
            variants=2,
            angles=["simplest", "extensible"],
        )
        assert [v.variant_id for v in plan.variants] == ["v1", "v2"]

    def test_count_six_accepted(self) -> None:
        plan = plan_variants(
            change_id="add-foo",
            variants=6,
            angles=["a", "b", "c", "d", "e", "f"],
        )
        assert len(plan.variants) == 6

    def test_count_one_rejected(self) -> None:
        # Spec: variant-count-out-of-bounds — N=1 must be rejected.
        with pytest.raises(VariantPlanError, match="2-6"):
            plan_variants(change_id="add-foo", variants=1)

    def test_count_seven_rejected(self) -> None:
        with pytest.raises(VariantPlanError, match="2-6"):
            plan_variants(change_id="add-foo", variants=7, angles=["a"] * 7)

    def test_min_max_constants_match_spec(self) -> None:
        # Sanity: the constants document the spec's allowed range.
        assert MIN_VARIANTS == 2
        assert MAX_VARIANTS == 6


class TestAngleCountMatching:
    """Spec: PrototypeFeatureSkill.custom-variant-count-and-angles."""

    def test_default_angles_are_three(self) -> None:
        # D5: simplest, extensible, pragmatic.
        assert DEFAULT_ANGLES == ("simplest", "extensible", "pragmatic")

    def test_default_angles_used_when_count_is_three(self) -> None:
        plan = plan_variants(change_id="add-foo")
        angles = [v.angle for v in plan.variants]
        assert angles == list(DEFAULT_ANGLES)

    def test_custom_angles_match_count(self) -> None:
        plan = plan_variants(
            change_id="add-foo",
            variants=4,
            angles=["simplest", "extensible", "pragmatic", "perf-first"],
        )
        assert [v.angle for v in plan.variants] == [
            "simplest",
            "extensible",
            "pragmatic",
            "perf-first",
        ]

    def test_angle_count_mismatch_rejected(self) -> None:
        # Spec: count of angles SHALL match --variants exactly.
        with pytest.raises(VariantPlanError, match="angles"):
            plan_variants(
                change_id="add-foo",
                variants=3,
                angles=["simplest", "extensible"],
            )

    def test_default_angles_fail_when_count_not_three_and_no_angles_given(
        self,
    ) -> None:
        # When --variants is overridden but --angles isn't, we can't
        # silently fabricate angles — fail fast and ask the user.
        with pytest.raises(VariantPlanError, match="angles"):
            plan_variants(change_id="add-foo", variants=4)


class TestBranchAndPathPerVariant:
    """Each variant gets prototype/<change>/v<n> + .git-worktrees/<change>/v<n>."""

    def test_branch_uses_prototype_prefix(self) -> None:
        plan = plan_variants(change_id="add-foo")
        for n, v in enumerate(plan.variants, start=1):
            assert v.branch == f"prototype/add-foo/v{n}"

    def test_worktree_path_layout(self) -> None:
        plan = plan_variants(change_id="add-foo")
        for n, v in enumerate(plan.variants, start=1):
            assert v.worktree_relpath == f".git-worktrees/add-foo/v{n}"


class TestVendorDiversityPolicy:
    """Spec: VendorDiversityPolicy.sufficient / insufficient / recorded."""

    def test_sufficient_vendors_one_per_variant(self) -> None:
        # 3 distinct vendors available → one per variant, no fallback.
        plan = plan_variants(change_id="add-foo")
        assignment = resolve_vendor_assignment(
            plan, available_vendors=["claude", "codex", "gemini"]
        )
        assert assignment.fallback is False
        assert sorted(assignment.per_variant.values()) == ["claude", "codex", "gemini"]
        # Each variant got a distinct vendor.
        assert len(set(assignment.per_variant.values())) == 3

    def test_insufficient_vendors_falls_back_to_most_available(self) -> None:
        # Only 1 vendor available for 3 variants → all run on the same one
        # with fallback=True per D3.
        plan = plan_variants(change_id="add-foo")
        assignment = resolve_vendor_assignment(
            plan, available_vendors=["claude"]
        )
        assert assignment.fallback is True
        assert all(v == "claude" for v in assignment.per_variant.values())

    def test_two_vendors_three_variants_falls_back(self) -> None:
        # Strictly fewer distinct vendors than variants triggers fallback.
        plan = plan_variants(change_id="add-foo")
        assignment = resolve_vendor_assignment(
            plan, available_vendors=["claude", "codex"]
        )
        assert assignment.fallback is True

    def test_zero_vendors_raises(self) -> None:
        # No vendors at all is a true failure — the spec says we never
        # hard-block on availability, but zero is unrunnable.
        plan = plan_variants(change_id="add-foo")
        with pytest.raises(VariantPlanError, match="vendor"):
            resolve_vendor_assignment(plan, available_vendors=[])

    def test_assignment_recorded_per_variant(self) -> None:
        # Spec: VendorDiversityPolicy.recorded — per-variant vendor must
        # appear in the assignment so it can be persisted on the descriptor.
        plan = plan_variants(change_id="add-foo")
        assignment = resolve_vendor_assignment(
            plan, available_vendors=["claude", "codex", "gemini"]
        )
        assert set(assignment.per_variant.keys()) == {"v1", "v2", "v3"}
