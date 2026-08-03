"""Schema-level tests for the work-package ``context_impact`` block (ri-08).

The work-packages schema is closed (``additionalProperties: false``) at every
level, so every assertion here fails against the pre-ri-08 schema with an
"Additional properties are not allowed" error. That is the point: these tests
must be red before the schema change lands.
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from wp_fixtures import SURFACES, minimal_document, minimal_package


def _validate(schema: dict[str, Any], document: dict[str, Any]) -> None:
    jsonschema.validate(instance=document, schema=schema)


def _errors(schema: dict[str, Any], document: dict[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(document)]


class TestContextImpactAccepted:
    def test_a_declaration_naming_every_surface_validates(self, schema):
        package = minimal_package(context_impact={"surfaces": list(SURFACES)})
        _validate(schema, minimal_document(package))

    @pytest.mark.parametrize("surface", SURFACES)
    def test_each_surface_is_accepted_individually(self, schema, surface):
        package = minimal_package(context_impact={"surfaces": [surface]})
        _validate(schema, minimal_document(package))

    def test_an_empty_surface_list_is_a_valid_no_impact_assertion(self, schema):
        package = minimal_package(context_impact={"surfaces": []})
        _validate(schema, minimal_document(package))

    def test_a_rationale_with_reason_and_approver_validates(self, schema):
        package = minimal_package(
            context_impact={
                "surfaces": ["apis"],
                "rationale": {
                    "documentation": {
                        "reason": "Only fixtures changed; no doc surface affected.",
                        "approved_by": "jankneumann",
                    }
                },
            }
        )
        _validate(schema, minimal_document(package))


class TestContextImpactRejected:
    def test_an_unknown_surface_is_rejected(self, schema):
        package = minimal_package(context_impact={"surfaces": ["telemetry"]})
        errors = _errors(schema, minimal_document(package))
        assert errors, "an unknown surface name must not validate"
        assert any("telemetry" in message for message in errors)

    def test_surfaces_is_required_when_the_block_is_present(self, schema):
        package = minimal_package(context_impact={"rationale": {}})
        errors = _errors(schema, minimal_document(package))
        assert any("surfaces" in message for message in errors)

    def test_a_rationale_without_an_approver_is_rejected(self, schema):
        package = minimal_package(
            context_impact={
                "surfaces": [],
                "rationale": {"apis": {"reason": "Not really an API change."}},
            }
        )
        errors = _errors(schema, minimal_document(package))
        assert any("approved_by" in message for message in errors)

    def test_an_empty_approver_string_is_rejected(self, schema):
        package = minimal_package(
            context_impact={
                "surfaces": [],
                "rationale": {"apis": {"reason": "Not an API change.", "approved_by": ""}},
            }
        )
        errors = _errors(schema, minimal_document(package))
        # Asserting on the *specific* message, not merely that some error exists:
        # before ri-08 every one of these documents fails with a blanket
        # "context_impact was unexpected", which would let a broken constraint
        # masquerade as a working one.
        assert any("non-empty" in message for message in errors), errors

    def test_an_unknown_surface_key_in_rationale_is_rejected(self, schema):
        package = minimal_package(
            context_impact={
                "surfaces": [],
                "rationale": {
                    "telemetry": {"reason": "Nope.", "approved_by": "jankneumann"}
                },
            }
        )
        errors = _errors(schema, minimal_document(package))
        assert any("telemetry" in message for message in errors), errors

    def test_unknown_keys_inside_the_block_are_rejected(self, schema):
        package = minimal_package(
            context_impact={"surfaces": [], "read_allow": ["docs/**"]}
        )
        errors = _errors(schema, minimal_document(package))
        assert any("read_allow" in message for message in errors), errors

    def test_duplicate_surfaces_are_rejected(self, schema):
        package = minimal_package(context_impact={"surfaces": ["apis", "apis"]})
        errors = _errors(schema, minimal_document(package))
        assert any("non-unique" in message for message in errors), errors


class TestBackwardCompatibility:
    def test_a_package_without_the_block_still_validates(self, schema):
        _validate(schema, minimal_document(minimal_package()))

    def test_no_previously_required_field_became_optional(self, schema):
        required = schema["$defs"]["WorkPackage"]["required"]
        for field in (
            "package_id",
            "task_type",
            "description",
            "depends_on",
            "priority",
            "locks",
            "scope",
            "worktree",
            "timeout_minutes",
            "retry_budget",
            "min_trust_level",
            "verification",
            "outputs",
        ):
            assert field in required, f"{field} must stay required"

    def test_context_impact_is_not_required(self, schema):
        assert "context_impact" not in schema["$defs"]["WorkPackage"]["required"]
