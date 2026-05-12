"""Tests for ``synthesize_variants(descriptors, change_id) -> synthesis_plan``.

Spec scenarios covered:
- skill-workflow.VariantDescriptorSchema.synthesis_plan — output validates
  against contracts/schemas/synthesis-plan.schema.json.
- skill-workflow.PrototypeFindingsArtifact.human-pick-and-choose — output
  reflects per-aspect human picks (data_model / api / tests / layout) and
  surfaces multi-pick situations as ``convergence.merge-*`` recommended
  findings rather than collapsing them to a single winner.

Design decisions: D7 (pick-and-choose, not pick-one-winner), D9 (schema).
"""

from __future__ import annotations

import jsonschema
import pytest
from variant_descriptor import VariantDescriptor, synthesize_variants


def _from_fixtures(*payloads: dict) -> list[VariantDescriptor]:
    return [VariantDescriptor.from_dict(p) for p in payloads]


class TestPerAspectPicksFromHumanFeedback:
    """Each aspect's source is derived from human_picks across variants."""

    def test_single_pick_per_aspect_routes_to_picked_variant(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        descriptor_v3: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Setup: v1 picks data_model+tests, v2 picks api, v3 picks layout.
        # Every aspect has exactly one picker — no merge needed.
        descriptors = _from_fixtures(descriptor_v1, descriptor_v2, descriptor_v3)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        assert plan["per_aspect_picks"]["data_model"]["source"] == "v1"
        assert plan["per_aspect_picks"]["api"]["source"] == "v2"
        assert plan["per_aspect_picks"]["tests"]["source"] == "v1"
        assert plan["per_aspect_picks"]["layout"]["source"] == "v3"

    def test_no_pick_for_aspect_routes_to_rewrite(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Setup: drop v3, so layout has zero picks across the surviving variants.
        descriptors = _from_fixtures(descriptor_v1, descriptor_v2)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        # layout: no variant was picked → rewrite
        assert plan["per_aspect_picks"]["layout"]["source"] == "rewrite"
        # data_model still goes to v1
        assert plan["per_aspect_picks"]["data_model"]["source"] == "v1"

    def test_multi_pick_for_aspect_uses_lowest_id_as_default(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Setup: both v1 AND v2 picked for data_model. The schema demands
        # a single source per aspect, so the algorithm must choose one.
        # Tie-break = lowest variant id; the disagreement surfaces as a
        # convergence.merge-* finding (verified in TestRecommendedFindings).
        v2_dual = {**descriptor_v2}
        v2_dual["human_picks"] = {**v2_dual["human_picks"], "data_model": True}
        descriptors = _from_fixtures(descriptor_v1, v2_dual)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        assert plan["per_aspect_picks"]["data_model"]["source"] == "v1"


class TestRecommendedFindingsForConvergence:
    """Multi-pick → ``convergence.merge-*``; no-pick → ``convergence.rewrite-*``."""

    def test_emits_merge_finding_for_multi_pick_aspect(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Both v1 and v2 picked for data_model — synthesis should not silently
        # discard v2's contribution.
        v2_dual = {**descriptor_v2}
        v2_dual["human_picks"] = {**v2_dual["human_picks"], "data_model": True}
        descriptors = _from_fixtures(descriptor_v1, v2_dual)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        merge_findings = [
            f
            for f in plan["recommended_findings"]
            if f["type"].startswith("convergence.merge-data-model")
        ]
        assert len(merge_findings) == 1, (
            f"expected exactly one merge finding for data_model, got {plan['recommended_findings']}"
        )
        assert set(merge_findings[0]["source_variants"]) == {"v1", "v2"}
        assert merge_findings[0]["criticality"] in {"critical", "high", "medium", "low"}

    def test_emits_rewrite_finding_when_no_variant_picked(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # No variant picks layout among the two we pass in.
        descriptors = _from_fixtures(descriptor_v1, descriptor_v2)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        rewrite_findings = [
            f
            for f in plan["recommended_findings"]
            if f["type"] == "convergence.rewrite-layout"
        ]
        assert len(rewrite_findings) == 1
        # No source_variants for a rewrite — there's nothing to merge.
        assert rewrite_findings[0].get("source_variants", []) == []

    def test_no_findings_when_all_aspects_have_unique_picks(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        descriptor_v3: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Clean case: each aspect is picked by exactly one variant. The plan
        # itself communicates the picks; no convergence findings are needed.
        descriptors = _from_fixtures(descriptor_v1, descriptor_v2, descriptor_v3)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        # The "tests" aspect (v1 picks tests, v2/v3 don't) should NOT emit a
        # merge or rewrite finding — that would be noise.
        irrelevant = [
            f
            for f in plan["recommended_findings"]
            if "tests" in f["type"]
        ]
        assert irrelevant == []


class TestSynthesisNotesAggregation:
    """``synthesis_hint`` values from variants flow into ``synthesis_notes``."""

    def test_concatenates_synthesis_hints(
        self,
        descriptor_v1: dict,
        descriptor_v2: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        v2_with_hint = {**descriptor_v2, "synthesis_hint": "v2 has the cleanest API"}
        descriptors = _from_fixtures(descriptor_v1, v2_with_hint)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        notes = plan.get("synthesis_notes", "")
        assert "v1 nailed the data model" in notes
        assert "v2 has the cleanest API" in notes

    def test_omits_synthesis_notes_when_no_hints_present(
        self,
        descriptor_v2: dict,
        descriptor_v3: dict,
        synthesis_plan_schema: dict,
    ) -> None:
        # Neither v2 nor v3 carries a synthesis_hint in the fixtures.
        descriptors = _from_fixtures(descriptor_v2, descriptor_v3)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        # Either omitted or empty string — both schema-valid; we prefer omitted
        # so the rendered findings file doesn't show an empty section.
        assert "synthesis_notes" not in plan or plan["synthesis_notes"] == ""


class TestEdgeCases:
    def test_empty_descriptor_list_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            synthesize_variants([], change_id="add-foo")

    def test_change_id_propagates_to_plan(
        self, descriptor_v1: dict, descriptor_v2: dict, descriptor_v3: dict
    ) -> None:
        descriptors = _from_fixtures(descriptor_v1, descriptor_v2, descriptor_v3)
        plan = synthesize_variants(descriptors, change_id="my-different-change")
        assert plan["change_id"] == "my-different-change"

    def test_smoke_failure_does_not_block_synthesis(
        self,
        descriptor_v1: dict,
        descriptor_v3: dict,  # has smoke pass=False
        synthesis_plan_schema: dict,
    ) -> None:
        # Spec scenario: VariantScoring.skeleton-fails-to-deploy — a failed
        # smoke phase MUST NOT exclude the variant from human pick-and-choose;
        # the human can still want its layout. Synthesis should pass through.
        descriptors = _from_fixtures(descriptor_v1, descriptor_v3)
        plan = synthesize_variants(descriptors, change_id="add-foo")
        jsonschema.validate(plan, synthesis_plan_schema)

        # v3 was picked for layout — that pick must survive even though
        # its smoke phase failed.
        assert plan["per_aspect_picks"]["layout"]["source"] == "v3"
