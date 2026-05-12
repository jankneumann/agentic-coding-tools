"""Tests for the VariantDescriptor dataclass.

Spec scenarios covered:
- skill-workflow.VariantDescriptorSchema.published — dataclass mirrors
  the contracts/schemas/variant-descriptor.schema.json shape, including
  required fields and optional ``synthesis_hint`` / ``vendor_fallback``.

Design decisions: D9.

The dataclass is the in-memory representation of a single variant's
record in ``prototype-findings.md``. Tests assert that:
  - construction with required fields succeeds
  - missing required fields fail at construction time
  - ``to_dict`` round-trips through the JSON Schema
"""

from __future__ import annotations

import jsonschema
import pytest
from variant_descriptor import VariantDescriptor


class TestVariantDescriptorConstruction:
    def test_constructs_with_full_payload(self, descriptor_v1: dict) -> None:
        # Sanity: the canonical fixture round-trips through the dataclass.
        vd = VariantDescriptor.from_dict(descriptor_v1)
        assert vd.variant_id == "v1"
        assert vd.angle == "simplest"
        assert vd.vendor == "claude-opus-4-7"
        assert vd.branch == "prototype/add-foo/v1"
        assert vd.synthesis_hint == "v1 nailed the data model — keep it"
        assert vd.vendor_fallback is False  # default

    def test_constructs_without_optional_fields(self, descriptor_v2: dict) -> None:
        # descriptor_v2 fixture omits both synthesis_hint and vendor_fallback.
        vd = VariantDescriptor.from_dict(descriptor_v2)
        assert vd.synthesis_hint is None
        assert vd.vendor_fallback is False

    def test_vendor_fallback_recorded_when_set(self, descriptor_v1: dict) -> None:
        # Spec scenario VendorDiversityPolicy.recorded — when fallback fires,
        # it MUST be persisted on the descriptor for synthesis to weigh.
        payload = {**descriptor_v1, "vendor_fallback": True}
        vd = VariantDescriptor.from_dict(payload)
        assert vd.vendor_fallback is True


class TestVariantDescriptorRoundTrip:
    def test_to_dict_validates_against_schema(
        self,
        descriptor_v1: dict,
        variant_descriptor_schema: dict,
    ) -> None:
        # Round-trip the descriptor through the dataclass and back to a dict,
        # then validate against the published schema. This catches drift
        # between the schema and the in-memory representation.
        vd = VariantDescriptor.from_dict(descriptor_v1)
        roundtripped = vd.to_dict()
        jsonschema.validate(roundtripped, variant_descriptor_schema)

    def test_to_dict_omits_optional_fields_when_unset(
        self,
        descriptor_v2: dict,
        variant_descriptor_schema: dict,
    ) -> None:
        # We don't want to_dict to emit ``synthesis_hint: None`` because the
        # schema's ``additionalProperties: false`` would still tolerate it
        # but downstream tools (Markdown renderers) shouldn't display "None".
        vd = VariantDescriptor.from_dict(descriptor_v2)
        out = vd.to_dict()
        assert "synthesis_hint" not in out
        # vendor_fallback may stay as False (it's a bool with default in the
        # schema) — confirm validation still passes either way
        jsonschema.validate(out, variant_descriptor_schema)


class TestVariantDescriptorValidation:
    def test_missing_required_field_raises(self, descriptor_v1: dict) -> None:
        # If a required field is missing, the dataclass should raise
        # rather than silently produce a partial object.
        for field in (
            "variant_id",
            "angle",
            "vendor",
            "branch",
            "automated_scores",
            "human_picks",
        ):
            payload = {k: v for k, v in descriptor_v1.items() if k != field}
            with pytest.raises((TypeError, KeyError)):
                VariantDescriptor.from_dict(payload)

    def test_invalid_variant_id_raises(self, descriptor_v1: dict) -> None:
        payload = {**descriptor_v1, "variant_id": "V1"}  # uppercase rejected
        with pytest.raises(ValueError, match="variant_id"):
            VariantDescriptor.from_dict(payload)

    def test_invalid_branch_raises(self, descriptor_v1: dict) -> None:
        payload = {**descriptor_v1, "branch": "openspec/add-foo/v1"}
        with pytest.raises(ValueError, match="branch"):
            VariantDescriptor.from_dict(payload)
