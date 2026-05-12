"""Variant planning + vendor diversity policy for /prototype-feature.

Pure-function helpers that the SKILL.md workflow calls before dispatching
Task() agents. Keeping the planning surface unit-testable means we can
TDD the variant-count, angle-count, and vendor-diversity rules without
having to actually run parallel agents.

The actual Task() dispatch — creating worktrees per variant, sending
each agent its angle prompt, waiting for completion — happens in the
SKILL.md workflow steps. This module's job is to (a) refuse invalid
inputs early and (b) hand the SKILL a ready-to-execute plan.

Spec scenarios:
  - PrototypeFeatureSkill.default-variant-dispatch
  - PrototypeFeatureSkill.custom-variant-count-and-angles
  - PrototypeFeatureSkill.variant-count-out-of-bounds
  - VendorDiversityPolicy.sufficient / insufficient / recorded

Design decisions: D2 (default 3 variants), D3 (best-effort vendor
diversity with single-vendor fallback), D5 (angle prompts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# Bounds from D2 / spec. Kept as module constants so tests can assert
# against them directly — accidental changes to these break the spec contract.
MIN_VARIANTS: Final[int] = 2
MAX_VARIANTS: Final[int] = 6

# Default angles from D5. Tuple to make the default immutable; tests
# assert exact equality so any reordering shows up in CI.
DEFAULT_ANGLES: Final[tuple[str, str, str]] = (
    "simplest",
    "extensible",
    "pragmatic",
)


class VariantPlanError(ValueError):
    """Raised when the requested plan can't be satisfied (bad bounds,
    angle-count mismatch, no vendors)."""


@dataclass(frozen=True)
class VariantSpec:
    """Per-variant invocation parameters the SKILL workflow consumes."""

    variant_id: str
    angle: str
    branch: str
    worktree_relpath: str


@dataclass
class VariantPlan:
    """All N variant specs plus their shared change-id."""

    change_id: str
    variants: list[VariantSpec] = field(default_factory=list)


@dataclass
class VendorAssignment:
    """Result of resolve_vendor_assignment.

    ``per_variant`` is variant_id → vendor_name. ``fallback`` is True
    when fewer distinct vendors were available than variants requested
    (so all variants ended up on the most-available vendor per D3).
    """

    per_variant: dict[str, str]
    fallback: bool


def plan_variants(
    change_id: str,
    variants: int = 3,
    angles: list[str] | None = None,
) -> VariantPlan:
    """Validate inputs and emit a ready-to-dispatch VariantPlan.

    Rules (D2 / D5 / spec):
      - 2 ≤ variants ≤ 6 (else VariantPlanError)
      - angle count == variants (else VariantPlanError); when omitted,
        default angles are used ONLY if variants == 3, otherwise the
        caller must supply angles to avoid silent guessing.
    """
    if variants < MIN_VARIANTS or variants > MAX_VARIANTS:
        raise VariantPlanError(
            f"variants={variants} outside allowed range "
            f"{MIN_VARIANTS}-{MAX_VARIANTS}."
        )

    if angles is None:
        if variants != len(DEFAULT_ANGLES):
            raise VariantPlanError(
                f"variants={variants} but no --angles supplied; "
                f"default angles only cover {len(DEFAULT_ANGLES)} variants."
            )
        angles = list(DEFAULT_ANGLES)
    elif len(angles) != variants:
        raise VariantPlanError(
            f"--angles count ({len(angles)}) must equal "
            f"--variants ({variants})."
        )

    specs = [
        VariantSpec(
            variant_id=f"v{n}",
            angle=angles[n - 1],
            branch=f"prototype/{change_id}/v{n}",
            worktree_relpath=f".git-worktrees/{change_id}/v{n}",
        )
        for n in range(1, variants + 1)
    ]
    return VariantPlan(change_id=change_id, variants=specs)


def resolve_vendor_assignment(
    plan: VariantPlan,
    available_vendors: list[str],
) -> VendorAssignment:
    """Per D3: best-effort distinct vendor per variant; fall back to
    one-vendor-for-all when fewer distinct vendors than variants.

    Never raises on insufficient vendors — only on zero (truly unrunnable).
    """
    if not available_vendors:
        raise VariantPlanError(
            "No vendors available; cannot dispatch any variants."
        )

    n = len(plan.variants)
    distinct_count = len(set(available_vendors))

    if distinct_count >= n:
        # One distinct vendor per variant. Preserve the caller's order
        # so the assignment is deterministic.
        seen: set[str] = set()
        ordered_distinct: list[str] = []
        for v in available_vendors:
            if v not in seen:
                ordered_distinct.append(v)
                seen.add(v)
        per_variant = {
            spec.variant_id: ordered_distinct[i]
            for i, spec in enumerate(plan.variants)
        }
        return VendorAssignment(per_variant=per_variant, fallback=False)

    # Fallback path: all variants share the most-available vendor.
    # "Most-available" = first in the available_vendors list, which the
    # caller is expected to sort by health (vendor_health.HealthReport).
    fallback_vendor = available_vendors[0]
    per_variant = {spec.variant_id: fallback_vendor for spec in plan.variants}
    return VendorAssignment(per_variant=per_variant, fallback=True)


__all__ = [
    "DEFAULT_ANGLES",
    "MAX_VARIANTS",
    "MIN_VARIANTS",
    "VariantPlan",
    "VariantPlanError",
    "VariantSpec",
    "VendorAssignment",
    "plan_variants",
    "resolve_vendor_assignment",
]
