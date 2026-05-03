"""End-to-end integration test for the prototyping stage.

This is the wp-integration package's task 8.1 — a synthetic but
realistic flow that exercises the full data path:

  1. Build N VariantDescriptors (stand-ins for what /prototype-feature
     would produce after dispatch + scoring + human pick-and-choose).
  2. Write them to prototype-findings.md via collect_outcomes.
  3. Load them back via prototype_context (simulating
     /iterate-on-plan --prototype-context startup).
  4. Verify synthesis_plan + convergence findings flow through end-to-end
     and conform to schemas.

We do NOT spawn real Task() agents or real /validate-feature runs —
those are integration concerns that require network + LLM credentials
and aren't appropriate for CI.

Spec scenarios end-to-end-validated:
  - VariantDescriptorSchema.published, synthesis_plan
  - PrototypeFindingsArtifact.findings-artifact-produced,
    human-pick-and-choose
  - ConvergenceViaIterateOnPlan.convergence-mode-activated
  - VendorDiversityPolicy.recorded
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = REPO_ROOT / "skills"
for sub in (
    SKILLS / "parallel-infrastructure" / "scripts",
    SKILLS / "prototype-feature" / "scripts",
    SKILLS / "iterate-on-plan" / "scripts",
):
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))

from collect_outcomes import build_descriptor, write_findings_file
from prototype_context import PrototypeContextMissing, load_prototype_context
from variant_descriptor import (
    VariantDescriptor,
    synthesize_variants,
)

CHANGE_DIR_TEMPLATE = "openspec/changes/{change_id}"
SCHEMA_DIR = REPO_ROOT / "openspec" / "changes" / "add-prototyping-stage" / "contracts" / "schemas"


@pytest.fixture(scope="module")
def variant_descriptor_schema() -> dict:
    return json.loads((SCHEMA_DIR / "variant-descriptor.schema.json").read_text())


@pytest.fixture(scope="module")
def synthesis_plan_schema() -> dict:
    return json.loads((SCHEMA_DIR / "synthesis-plan.schema.json").read_text())


def _scoring(passed: bool = True, covered: int = 5, total: int = 5) -> dict:
    return {
        "smoke": {"pass": passed, "report": "stub"},
        "spec": {
            "covered": covered,
            "total": total,
            "missing": [] if covered == total else ["scenario-3"],
        },
    }


class TestPrototypeConvergenceEndToEnd:
    """The shape iterate-on-plan would actually see in production."""

    def test_full_flow_produces_synthesis_plan_with_convergence_findings(
        self,
        tmp_path: Path,
        variant_descriptor_schema: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        change_id = "add-fictional-feature"
        change_dir = tmp_path / CHANGE_DIR_TEMPLATE.format(change_id=change_id)
        change_dir.mkdir(parents=True)

        # Step A: build 3 descriptors with realistic pick patterns.
        # v1 wins data_model + tests; v2 wins api; v3 wins layout.
        # Plus one duplicate pick on data_model from v2 so we exercise
        # the convergence.merge-* finding path.
        descriptors = [
            build_descriptor(
                variant_id="v1",
                angle="simplest",
                vendor="claude-opus-4-7",
                change_id=change_id,
                scoring=_scoring(),
                human_picks={
                    "data_model": True,
                    "api": False,
                    "tests": True,
                    "layout": False,
                },
                synthesis_hint="v1 nailed the data model — keep it",
            ),
            build_descriptor(
                variant_id="v2",
                angle="extensible",
                vendor="codex",
                change_id=change_id,
                scoring=_scoring(covered=4),
                human_picks={
                    "data_model": True,  # ← second pick → merge finding
                    "api": True,
                    "tests": False,
                    "layout": False,
                },
                vendor_fallback=False,
            ),
            build_descriptor(
                variant_id="v3",
                angle="pragmatic",
                vendor="gemini",
                change_id=change_id,
                scoring=_scoring(passed=False, covered=2, total=5),
                human_picks={
                    "data_model": False,
                    "api": False,
                    "tests": False,
                    "layout": True,
                },
            ),
        ]
        for d in descriptors:
            jsonschema.validate(d.to_dict(), variant_descriptor_schema)

        # Step B: persist to prototype-findings.md
        out_path = write_findings_file(change_dir=change_dir, descriptors=descriptors)
        assert out_path.is_file()

        # Step C: load it back the way iterate-on-plan --prototype-context would
        ctx = load_prototype_context(change_dir=change_dir)
        assert ctx.change_id == change_id
        assert len(ctx.descriptors) == 3
        assert [d.variant_id for d in ctx.descriptors] == ["v1", "v2", "v3"]

        # Step D: synthesis plan + schema conformance
        plan = ctx.synthesis_plan
        jsonschema.validate(plan, synthesis_plan_schema)
        assert plan["change_id"] == change_id

        # Step E: per-aspect picks reflect the human feedback
        assert plan["per_aspect_picks"]["data_model"]["source"] == "v1"  # tie-break
        assert plan["per_aspect_picks"]["api"]["source"] == "v2"
        assert plan["per_aspect_picks"]["tests"]["source"] == "v1"
        assert plan["per_aspect_picks"]["layout"]["source"] == "v3"

        # Step F: convergence findings — the data_model multi-pick must
        # surface as a merge.* finding (D7: synthesis, not winners).
        merge_findings = [
            f
            for f in plan["recommended_findings"]
            if f["type"].startswith("convergence.merge-data-model")
        ]
        assert len(merge_findings) == 1, (
            f"expected exactly one merge finding for data_model "
            f"(humans picked v1 AND v2); got {plan['recommended_findings']}"
        )
        assert set(merge_findings[0]["source_variants"]) == {"v1", "v2"}

        # Step G: vendor diversity is recorded — v1=claude, v2=codex, v3=gemini
        # all flow through the descriptor round-trip without loss.
        vendors = {d.vendor for d in ctx.descriptors}
        assert vendors == {"claude-opus-4-7", "codex", "gemini"}

        # Step H: synthesis_notes carries the synthesis_hint forward
        assert "v1 nailed the data model" in plan.get("synthesis_notes", "")

    def test_smoke_failure_does_not_break_convergence(
        self,
        tmp_path: Path,
        variant_descriptor_schema: dict,
    ) -> None:
        # v3 in the previous test had smoke pass=False AND was picked for
        # layout. The flow must still produce a usable plan — failure to
        # deploy is data, not an exception.
        change_id = "add-fictional-feature"
        change_dir = tmp_path / CHANGE_DIR_TEMPLATE.format(change_id=change_id)
        change_dir.mkdir(parents=True)

        descriptor = build_descriptor(
            variant_id="v1",
            angle="simplest",
            vendor="claude-opus-4-7",
            change_id=change_id,
            scoring=_scoring(passed=False, covered=0, total=5),
            human_picks={
                "data_model": True,
                "api": True,
                "tests": True,
                "layout": True,
            },
        )
        jsonschema.validate(descriptor.to_dict(), variant_descriptor_schema)

        write_findings_file(change_dir=change_dir, descriptors=[descriptor])
        ctx = load_prototype_context(change_dir=change_dir)
        # All four aspects routed to v1 (the only variant).
        for aspect in ("data_model", "api", "tests", "layout"):
            assert ctx.synthesis_plan["per_aspect_picks"][aspect]["source"] == "v1"


class TestMissingFindingsFailFast:
    """Spec: ConvergenceViaIterateOnPlan.missing-prototype-artifacts."""

    def test_loader_raises_when_findings_absent(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)
        with pytest.raises(PrototypeContextMissing):
            load_prototype_context(change_dir=change_dir)
