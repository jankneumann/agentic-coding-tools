"""Schema contract tests for the gate/replan records (wp-contracts, tasks 0.1-0.2).

These freeze the coordination boundary the other three packages meet at: wp-autopilot-gates
writes GateRequest and GateDecisionRecord, wp-replan writes ReplanRequest, and wp-skill-docs
documents the `gate-check` protocol against GateRequest. A field invented on one side and
not the other is a bug the rest of the change cannot catch, so it is caught here.

The `resolution` enum is pinned to `approval_gate.Resolution` in CODE rather than restated
as a literal list: design D4 adds two console members to that enum, and a hand-copied list
would silently drift the first time anyone adds a third.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACTS = (
    _REPO_ROOT
    / "openspec" / "schemas"
)
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gates"

SCHEMA_NAMES = ("gate-request", "gate-decision", "replan-request")

# `shared.approval_gate` imports `from shared.trust_posture import ...`, so the
# PARENT of the package must be on the path — inserting skills/shared itself makes
# trust_posture importable but breaks approval_gate.
sys.path.insert(0, str(_REPO_ROOT / "skills"))


def _schema(name: str) -> dict:
    return json.loads((_CONTRACTS / f"{name}.schema.json").read_text())


def _validator(name: str) -> Draft202012Validator:
    """Resolve sibling $ref (replan-request references gate-decision) from disk.

    Uses `referencing` rather than the deprecated RefResolver so this test does not
    start emitting DeprecationWarnings the moment jsonschema drops the old API.
    """
    schema = _schema(name)
    registry = Registry()
    for other in SCHEMA_NAMES:
        other_schema = _schema(other)
        resource = Resource.from_contents(other_schema, default_specification=DRAFT202012)
        # Register under both the relative filename used by $ref and the absolute $id.
        registry = registry.with_resources(
            [(f"{other}.schema.json", resource), (other_schema["$id"], resource)]
        )
    return Draft202012Validator(schema, registry=registry)


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES / f"{name}.json").read_text())


class TestSchemasAreWellFormed:
    @pytest.mark.parametrize("name", SCHEMA_NAMES)
    def test_schema_is_valid_2020_12(self, name: str) -> None:
        schema = _schema(name)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["$id"].endswith(f"{name}.schema.json")

    @pytest.mark.parametrize("name", SCHEMA_NAMES)
    def test_schema_forbids_unknown_top_level_fields(self, name: str) -> None:
        """A record the writer and reader disagree about must fail loudly, not silently
        carry an ignored key. gate-decision is the deliberate exception: it is a superset
        of ApprovalDecision.to_audit_record(), which may grow fields."""
        schema = _schema(name)
        if name == "gate-decision":
            assert schema["additionalProperties"] is True
        else:
            assert schema["additionalProperties"] is False


class TestResolutionEnumTracksTheLibrary:
    def test_gate_decision_resolution_equals_library_plus_console(self) -> None:
        """D4: the two console resolutions live in approval_gate.Resolution, so the audit
        record has ONE shape whatever produced it. Pinning the schema to the enum in code
        means adding a member without updating the schema fails here."""
        from shared.approval_gate import Resolution  # type: ignore[import-not-found]

        schema_values = set(
            _schema("gate-decision")["properties"]["resolution"]["enum"]
        )
        library_values = {r.value for r in Resolution}
        assert schema_values == library_values, (
            "gate-decision.resolution must equal approval_gate.Resolution exactly; "
            f"schema-only={sorted(schema_values - library_values)}, "
            f"library-only={sorted(library_values - schema_values)}"
        )
        # The two console members are the point of D4 — assert them by name so a
        # rename cannot quietly satisfy the set comparison above.
        assert {"console_approved", "console_rejected"} <= library_values

    def test_gate_enum_matches_trust_posture(self) -> None:
        """Every schema that names a gate must name the same eight."""
        from shared.trust_posture import Gate  # type: ignore[import-not-found]

        expected = {g.value for g in Gate}
        assert set(_schema("gate-request")["properties"]["gate"]["enum"]) == expected
        assert set(_schema("gate-decision")["properties"]["gate"]["enum"]) == expected


class TestFixturesMatchTheirSchemas:
    @pytest.mark.parametrize("name", SCHEMA_NAMES)
    def test_valid_fixture_validates(self, name: str) -> None:
        _validator(name).validate(_fixture(f"{name}-valid"))

    @pytest.mark.parametrize("name", SCHEMA_NAMES)
    def test_invalid_fixture_is_rejected(self, name: str) -> None:
        errors = list(_validator(name).iter_errors(_fixture(f"{name}-invalid")))
        assert errors, f"{name}-invalid.json unexpectedly validated"
