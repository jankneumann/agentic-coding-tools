"""Validation tests for the VariantDescriptor JSON Schema.

Spec scenarios covered:
- skill-workflow.VariantDescriptorSchema.published — schema is well-formed,
  meta-validates against draft 2020-12, and required fields enforce the
  shape designed in D9.

Each test asserts a single property of the schema or its instances so
that failures localize to one design intent.
"""

from __future__ import annotations

import copy

import jsonschema
from jsonschema import Draft202012Validator


class TestSchemaIsWellFormed:
    """The schema itself meta-validates against draft 2020-12."""

    def test_meta_validation_passes(self, variant_descriptor_schema: dict) -> None:
        # Meta-validation raises if the schema document violates the
        # draft 2020-12 vocabulary. No assertion needed.
        Draft202012Validator.check_schema(variant_descriptor_schema)

    def test_dialect_is_draft_2020_12(self, variant_descriptor_schema: dict) -> None:
        assert (
            variant_descriptor_schema["$schema"]
            == "https://json-schema.org/draft/2020-12/schema"
        )

    def test_id_is_versioned(self, variant_descriptor_schema: dict) -> None:
        # v1 stability promise from contracts/README.md: additive within v1,
        # breaking changes require a new file. The $id encodes that version.
        assert variant_descriptor_schema["$id"].endswith(".v1.schema.json")

    def test_additional_properties_are_forbidden(self, variant_descriptor_schema: dict) -> None:
        # Forbidding additional properties at the top level prevents the
        # human_picks dict from silently accepting typos like "data-model"
        # vs "data_model".
        assert variant_descriptor_schema["additionalProperties"] is False


class TestRequiredFieldsEnforced:
    """Omitting any required field fails validation with a clear path."""

    def test_canonical_descriptor_validates(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        jsonschema.validate(valid_descriptor, variant_descriptor_schema)

    def test_missing_variant_id_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["variant_id"]
        with __import__("pytest").raises(jsonschema.ValidationError) as excinfo:
            jsonschema.validate(descriptor, variant_descriptor_schema)
        assert "variant_id" in str(excinfo.value)

    def test_missing_angle_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["angle"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_missing_vendor_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["vendor"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_missing_branch_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["branch"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_missing_automated_scores_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["automated_scores"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_missing_human_picks_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["human_picks"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)


class TestVariantIdPattern:
    """variant_id must match ^v[1-9][0-9]*$ (v1, v2, ..., v10, v99)."""

    def test_v1_through_v9_accepted(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        for vid in ("v1", "v2", "v3", "v9"):
            descriptor = copy.deepcopy(valid_descriptor)
            descriptor["variant_id"] = vid
            descriptor["branch"] = f"prototype/add-prototyping-stage/{vid}"
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_double_digit_variant_accepted(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        # The spec caps variants at 6 today, but the schema permits double
        # digits so we don't need a schema rev if the cap is raised.
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["variant_id"] = "v10"
        descriptor["branch"] = "prototype/add-prototyping-stage/v10"
        jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_v0_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["variant_id"] = "v0"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_uppercase_v_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["variant_id"] = "V1"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_no_prefix_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["variant_id"] = "1"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)


class TestBranchPattern:
    """branch must match ^prototype/.+/v[1-9][0-9]*$."""

    def test_canonical_branch_accepted(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        # Already validated in TestRequiredFieldsEnforced; this is the
        # branch-pattern-specific assertion.
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["branch"] = "prototype/some-change-id/v1"
        jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_branch_without_prototype_prefix_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["branch"] = "openspec/some-change-id/v1"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_branch_without_variant_suffix_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["branch"] = "prototype/some-change-id"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)


class TestAutomatedScoresShape:
    """automated_scores requires both smoke and spec sub-objects."""

    def test_missing_smoke_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["automated_scores"]["smoke"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_missing_spec_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        del descriptor["automated_scores"]["spec"]
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_smoke_without_pass_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["automated_scores"]["smoke"] = {"report": "missing pass field"}
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_spec_without_covered_or_total_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["automated_scores"]["spec"] = {"missing": []}
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_spec_covered_must_be_non_negative(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["automated_scores"]["spec"]["covered"] = -1
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_skeleton_failed_to_deploy_recorded(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        # spec scenario: PrototypeFeatureSkill.skeleton-fails-to-deploy —
        # smoke pass=False is a valid recorded outcome, not a schema error.
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["automated_scores"]["smoke"] = {
            "pass": False,
            "report": "container failed to start",
        }
        jsonschema.validate(descriptor, variant_descriptor_schema)


class TestHumanPicksShape:
    """human_picks must include all four aspects, all booleans."""

    def test_all_four_aspects_required(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        for aspect in ("data_model", "api", "tests", "layout"):
            descriptor = copy.deepcopy(valid_descriptor)
            del descriptor["human_picks"][aspect]
            with __import__("pytest").raises(jsonschema.ValidationError) as excinfo:
                jsonschema.validate(descriptor, variant_descriptor_schema)
            assert aspect in str(excinfo.value)

    def test_extra_aspect_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["human_picks"]["docs"] = True
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_string_pick_rejected(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["human_picks"]["data_model"] = "yes"
        with __import__("pytest").raises(jsonschema.ValidationError):
            jsonschema.validate(descriptor, variant_descriptor_schema)


class TestOptionalFields:
    """vendor_fallback and synthesis_hint are optional."""

    def test_descriptor_without_optional_fields_validates(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor.pop("synthesis_hint", None)
        descriptor.pop("vendor_fallback", None)
        jsonschema.validate(descriptor, variant_descriptor_schema)

    def test_vendor_fallback_recorded_when_set(
        self, variant_descriptor_schema: dict, valid_descriptor: dict
    ) -> None:
        # Spec scenario: VendorDiversityPolicy.recorded — when fallback was
        # triggered, vendor_fallback=True is a valid recorded value.
        descriptor = copy.deepcopy(valid_descriptor)
        descriptor["vendor_fallback"] = True
        jsonschema.validate(descriptor, variant_descriptor_schema)
