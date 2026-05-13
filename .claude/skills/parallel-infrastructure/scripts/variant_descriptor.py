"""VariantDescriptor + synthesize_variants — the parallel-infrastructure
half of the prototyping stage (D9, D7).

A ``VariantDescriptor`` is the in-memory representation of one row in
``prototype-findings.md`` — a single variant skeleton's record after the
prototype-feature skill has dispatched, scored, and human-reviewed it.

``synthesize_variants(descriptors, change_id)`` collapses N descriptors
into a single ``synthesis_plan`` dict that ``/iterate-on-plan
--prototype-context`` consumes during convergence-aware refinement.
The plan enumerates per-aspect source-variant picks and surfaces
multi-pick situations as ``convergence.merge-*`` recommended findings
rather than silently collapsing them — D7's "best design is synthesis,
not winners" principle.

The dict shapes here mirror ``contracts/schemas/variant-descriptor.schema.json``
and ``contracts/schemas/synthesis-plan.schema.json``. Round-trip tests
in ``skills/tests/parallel-infrastructure/`` validate against the
published schemas to catch drift.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Literal

ASPECTS: Final[tuple[str, str, str, str]] = ("data_model", "api", "tests", "layout")
AspectName = Literal["data_model", "api", "tests", "layout"]

_VARIANT_ID_RE = re.compile(r"^v[1-9][0-9]*$")
_BRANCH_RE = re.compile(r"^prototype/.+/v[1-9][0-9]*$")


@dataclass
class AutomatedScores:
    """Smoke + spec-coverage scores for one variant skeleton.

    Mirrors the ``automated_scores`` sub-object in the schema. Optional
    free-form fields (smoke.report, spec.missing) are kept as plain
    members so to_dict() round-trips cleanly.
    """

    smoke_pass: bool
    smoke_report: str | None = None
    spec_covered: int = 0
    spec_total: int = 0
    spec_missing: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AutomatedScores":
        smoke = d["smoke"]
        spec = d["spec"]
        return cls(
            smoke_pass=bool(smoke["pass"]),
            smoke_report=smoke.get("report"),
            spec_covered=int(spec["covered"]),
            spec_total=int(spec["total"]),
            spec_missing=list(spec.get("missing", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        smoke: dict[str, Any] = {"pass": self.smoke_pass}
        if self.smoke_report is not None:
            smoke["report"] = self.smoke_report
        spec: dict[str, Any] = {
            "covered": self.spec_covered,
            "total": self.spec_total,
        }
        if self.spec_missing:
            spec["missing"] = list(self.spec_missing)
        return {"smoke": smoke, "spec": spec}


@dataclass
class VariantDescriptor:
    """In-memory record of one prototype variant.

    Mirrors ``contracts/schemas/variant-descriptor.schema.json``. The
    pattern checks for ``variant_id`` and ``branch`` are duplicated here
    because callers construct descriptors directly (not through JSON
    Schema validation) and we want a loud failure rather than a silent
    bad write into prototype-findings.md.
    """

    variant_id: str
    angle: str
    vendor: str
    branch: str
    automated_scores: AutomatedScores
    human_picks: dict[AspectName, bool]
    vendor_fallback: bool = False
    synthesis_hint: str | None = None

    def __post_init__(self) -> None:
        if not _VARIANT_ID_RE.match(self.variant_id):
            raise ValueError(
                f"Invalid variant_id={self.variant_id!r}; "
                "must match ^v[1-9][0-9]*$ (e.g. 'v1', 'v10')."
            )
        if not _BRANCH_RE.match(self.branch):
            raise ValueError(
                f"Invalid branch={self.branch!r}; "
                "must match ^prototype/.+/v[1-9][0-9]*$."
            )
        missing = [a for a in ASPECTS if a not in self.human_picks]
        if missing:
            raise ValueError(
                f"human_picks missing required aspects: {missing}"
            )
        extra = [k for k in self.human_picks if k not in ASPECTS]
        if extra:
            raise ValueError(
                f"human_picks has unknown aspects: {extra}"
            )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VariantDescriptor":
        return cls(
            variant_id=d["variant_id"],
            angle=d["angle"],
            vendor=d["vendor"],
            branch=d["branch"],
            automated_scores=AutomatedScores.from_dict(d["automated_scores"]),
            human_picks=dict(d["human_picks"]),
            vendor_fallback=bool(d.get("vendor_fallback", False)),
            synthesis_hint=d.get("synthesis_hint"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "variant_id": self.variant_id,
            "angle": self.angle,
            "vendor": self.vendor,
            "branch": self.branch,
            "automated_scores": self.automated_scores.to_dict(),
            "human_picks": dict(self.human_picks),
        }
        if self.vendor_fallback:
            out["vendor_fallback"] = True
        if self.synthesis_hint:
            out["synthesis_hint"] = self.synthesis_hint
        return out


def _variant_sort_key(variant_id: str) -> int:
    """Numeric sort key for variant IDs ('v3' < 'v10')."""
    return int(variant_id[1:])


def _aspect_pickers(
    descriptors: list[VariantDescriptor], aspect: str
) -> list[VariantDescriptor]:
    """Variants whose human_picks[aspect] is True, sorted by variant id."""
    pickers = [d for d in descriptors if d.human_picks.get(aspect)]
    return sorted(pickers, key=lambda d: _variant_sort_key(d.variant_id))


def synthesize_variants(
    descriptors: list[VariantDescriptor],
    change_id: str,
) -> dict[str, Any]:
    """Collapse N variants into a SynthesisPlan dict.

    Algorithm per aspect (data_model / api / tests / layout):
      - 0 variants picked  → source = 'rewrite'  (emit convergence.rewrite-<aspect>)
      - 1 variant picked   → source = that variant's id (no extra finding)
      - 2+ variants picked → source = lowest variant id (default tie-break),
                             emit convergence.merge-<aspect>-<vA>-and-<vB>
                             so iterate-on-plan can surface the disagreement
                             to the user during convergence refinement.

    The lowest-id tie-break is intentionally simple: the synthesis plan
    needs *some* default source for the schema, and the merge finding
    carries the genuinely interesting signal (multiple humans wanted
    this aspect from different variants — a real synthesis opportunity).
    """
    if not descriptors:
        raise ValueError(
            "synthesize_variants requires at least one descriptor"
        )

    per_aspect_picks: dict[str, dict[str, Any]] = {}
    recommended_findings: list[dict[str, Any]] = []

    for aspect in ASPECTS:
        pickers = _aspect_pickers(descriptors, aspect)
        if not pickers:
            per_aspect_picks[aspect] = {
                "source": "rewrite",
                "rationale": f"no variant was selected for {aspect}",
            }
            recommended_findings.append({
                "type": f"convergence.rewrite-{aspect.replace('_', '-')}",
                "criticality": "medium",
                "description": (
                    f"No variant was selected for {aspect}; iterate-on-plan "
                    "should rewrite this aspect from other context."
                ),
                "source_variants": [],
            })
            continue

        winner = pickers[0]
        per_aspect_picks[aspect] = {"source": winner.variant_id}

        if len(pickers) > 1:
            ids = [p.variant_id for p in pickers]
            joined = "-and-".join(ids)
            recommended_findings.append({
                "type": f"convergence.merge-{aspect.replace('_', '-')}-{joined}",
                "criticality": "high",
                "description": (
                    f"{len(pickers)} variants were picked for {aspect} "
                    f"({', '.join(ids)}); default source is {winner.variant_id} "
                    "but iterate-on-plan should consider merging contributions."
                ),
                "source_variants": ids,
            })

    plan: dict[str, Any] = {
        "change_id": change_id,
        "per_aspect_picks": per_aspect_picks,
        "recommended_findings": recommended_findings,
    }

    hints = [d.synthesis_hint for d in descriptors if d.synthesis_hint]
    if hints:
        plan["synthesis_notes"] = " | ".join(hints)

    return plan


__all__ = [
    "ASPECTS",
    "AspectName",
    "AutomatedScores",
    "VariantDescriptor",
    "synthesize_variants",
]
