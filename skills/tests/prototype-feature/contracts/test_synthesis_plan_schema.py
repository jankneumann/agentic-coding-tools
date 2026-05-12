"""Validation tests for the SynthesisPlan JSON Schema.

Spec scenarios covered:
- skill-workflow.VariantDescriptorSchema.synthesis_plan — schema is
  well-formed; per_aspect_picks enforces source ∈ {v<n>, "rewrite"};
  recommended_findings enforces convergence.* type prefix.
- skill-workflow.PrototypeFindingsArtifact.human-pick-and-choose — the
  four aspects (data_model, api, tests, layout) must all be addressed
  by per_aspect_picks.
"""

from __future__ import annotations

import copy

import jsonschema
import pytest
from jsonschema import Draft202012Validator


class TestSchemaIsWellFormed:
    """The schema itself meta-validates against draft 2020-12."""

    def test_meta_validation_passes(self, synthesis_plan_schema: dict) -> None:
        Draft202012Validator.check_schema(synthesis_plan_schema)

    def test_dialect_is_draft_2020_12(self, synthesis_plan_schema: dict) -> None:
        assert (
            synthesis_plan_schema["$schema"]
            == "https://json-schema.org/draft/2020-12/schema"
        )

    def test_id_is_versioned(self, synthesis_plan_schema: dict) -> None:
        assert synthesis_plan_schema["$id"].endswith(".v1.schema.json")


class TestRequiredFieldsEnforced:
    """change_id, per_aspect_picks, recommended_findings are required."""

    def test_canonical_plan_validates(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        jsonschema.validate(valid_synthesis_plan, synthesis_plan_schema)

    def test_missing_change_id_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        del plan["change_id"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_missing_per_aspect_picks_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        del plan["per_aspect_picks"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_missing_recommended_findings_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        del plan["recommended_findings"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)


class TestPerAspectPicksShape:
    """per_aspect_picks must address all four aspects with valid sources."""

    def test_all_four_aspects_required(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        for aspect in ("data_model", "api", "tests", "layout"):
            plan = copy.deepcopy(valid_synthesis_plan)
            del plan["per_aspect_picks"][aspect]
            with pytest.raises(jsonschema.ValidationError) as excinfo:
                jsonschema.validate(plan, synthesis_plan_schema)
            assert aspect in str(excinfo.value)

    def test_extra_aspect_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["docs"] = {"source": "v1"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)


class TestAspectPickSource:
    """source must be either v<n> variant id or the literal 'rewrite'."""

    def test_variant_source_accepted(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["data_model"] = {"source": "v5"}
        jsonschema.validate(plan, synthesis_plan_schema)

    def test_rewrite_source_accepted(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["api"] = {"source": "rewrite"}
        jsonschema.validate(plan, synthesis_plan_schema)

    def test_arbitrary_string_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["data_model"] = {"source": "merge-v1-v2"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_v0_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["data_model"] = {"source": "v0"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_pick_without_source_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["data_model"] = {"rationale": "missing source"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)


class TestRecommendedFindingsShape:
    """Each finding requires type, criticality, description; type prefix is enforced."""

    def test_convergence_type_prefix_required(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["recommended_findings"][0]["type"] = "clarity.missing-acceptance-criterion"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_dotted_convergence_subtype_accepted(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        # convergence.merge-A-data-model-with-B-api per proposal text
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["recommended_findings"][0]["type"] = "convergence.merge-data-model-with-api"
        jsonschema.validate(plan, synthesis_plan_schema)

    def test_invalid_criticality_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["recommended_findings"][0]["criticality"] = "blocker"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_finding_missing_description_rejected(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        del plan["recommended_findings"][0]["description"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)

    def test_empty_findings_list_accepted(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        # A synthesis run that produced no convergence recommendations
        # is valid — the iterator simply has nothing to surface.
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["recommended_findings"] = []
        jsonschema.validate(plan, synthesis_plan_schema)

    def test_source_variants_pattern_enforced(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["recommended_findings"][0]["source_variants"] = ["v1", "main"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(plan, synthesis_plan_schema)


class TestOptionalFields:
    """synthesis_notes and per-pick rationale are optional."""

    def test_plan_without_synthesis_notes_validates(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan.pop("synthesis_notes", None)
        jsonschema.validate(plan, synthesis_plan_schema)

    def test_aspect_pick_without_rationale_validates(
        self, synthesis_plan_schema: dict, valid_synthesis_plan: dict
    ) -> None:
        plan = copy.deepcopy(valid_synthesis_plan)
        plan["per_aspect_picks"]["api"] = {"source": "v1"}
        jsonschema.validate(plan, synthesis_plan_schema)
