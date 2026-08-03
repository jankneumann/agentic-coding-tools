"""Tests for the published CLI contract schema (design D5).

A tool's invocation surface is contracted separately from OpenAPI: flags are
process configuration rather than operation parameters, and OpenAPI cannot
express exit codes at all. This module pins the schema that makes that
contract checkable.

The obligation that matters here is *rejection*. A schema that accepts every
well-formed-looking document proves nothing — the derivation drift guard is
built on the assumption that a contract which would derive an empty surface
cannot validate in the first place (design D3). Most tests below therefore
assert a broken contract FAILS, not that a good one passes.

The schema is read from its **promoted** location under
``openspec/contracts/``, not from the in-flight change directory. That is the
path its own ``$id`` claims, the path DOWNSTREAM DS-3 points consumers at, and
the only one that survives archival of the change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
SCHEMA_PATH = (
    REPO_ROOT
    / "openspec"
    / "contracts"
    / "gen-eval-framework"
    / "schemas"
    / "cli-contract.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    if not SCHEMA_PATH.is_file():
        pytest.fail(
            f"CLI contract schema not promoted to {SCHEMA_PATH.relative_to(REPO_ROOT)} "
            "— its $id points there and DOWNSTREAM DS-3 directs consumers to it "
            "(task 1.9)"
        )
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def _minimal() -> dict[str, Any]:
    """The smallest contract that is meant to validate.

    A flat flag-only CLI: exactly one command with an empty name, carrying at
    least one flag so it contributes a coverage unit.
    """
    return {
        "contract_version": "1",
        "tool": {"name": "gen-eval", "executable": "gen-eval"},
        "commands": [
            {
                "name": "",
                "flags": [{"name": "--descriptor", "type": "path", "required": True}],
            }
        ],
    }


class TestSchemaItself:
    """The schema document is well-formed and self-consistent."""

    def test_is_a_valid_2020_12_schema(self, schema: dict[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)

    def test_id_matches_promoted_location(self, schema: dict[str, Any]) -> None:
        assert schema["$id"].endswith(
            "/openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json"
        ), "$id must name the promoted path, or consumers resolving it will 404"


class TestAcceptsWellFormedContracts:
    """Positive controls — without these the rejection tests prove nothing."""

    def test_minimal_flat_cli(self, validator: Draft202012Validator) -> None:
        validator.validate(_minimal())

    def test_named_subcommand_needs_no_flags(
        self, validator: Draft202012Validator
    ) -> None:
        """A non-empty name is itself a coverage unit, so flags are optional."""
        contract = _minimal()
        contract["commands"] = [{"name": "lock acquire"}]
        validator.validate(contract)

    def test_full_surface(self, validator: Draft202012Validator) -> None:
        contract = _minimal()
        contract["exit_codes"] = [
            {"code": 0, "meaning": "pass rate met the threshold"},
            {"code": 64, "meaning": "usage error", "sysexits_name": "EX_USAGE"},
        ]
        contract["commands"][0]["flags"].append(
            {
                "name": "--report-format",
                "short": "-r",
                "type": "enum",
                "choices": ["markdown", "json", "both"],
                "default": "both",
                "short_circuits": False,
            }
        )
        contract["commands"][0]["positionals"] = [
            {"name": "target", "type": "path", "required": False}
        ]
        validator.validate(contract)

    def test_many_to_one_operation_binding(
        self, validator: Draft202012Validator
    ) -> None:
        """One surface element may serve several operations (design D4)."""
        contract = _minimal()
        contract["commands"][0]["operation_ids"] = [
            "list_active_locks",
            "get_lock_status",
        ]
        validator.validate(contract)


class TestRejectsStructurallyBrokenContracts:
    """Required fields and closed shapes."""

    @pytest.mark.parametrize("missing", ["contract_version", "tool", "commands"])
    def test_top_level_field_is_required(
        self, validator: Draft202012Validator, missing: str
    ) -> None:
        contract = _minimal()
        del contract[missing]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_no_commands_at_all_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"] = []
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_unknown_top_level_property_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        """additionalProperties: false — a typo'd key must not pass silently."""
        contract = _minimal()
        contract["exit_code"] = []  # singular: a plausible typo for exit_codes
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_tool_requires_executable(self, validator: Draft202012Validator) -> None:
        contract = _minimal()
        del contract["tool"]["executable"]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_contract_version_must_be_a_numeric_string(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["contract_version"] = 1  # int, not string
        with pytest.raises(Exception):
            validator.validate(contract)


class TestRejectsContractsThatWouldDeriveAnEmptySurface:
    """The fail-closed floor (design D3).

    This is the class of defect the whole guard exists for: a contract that is
    structurally valid but derives no nameable coverage unit. Such a document
    passed non-emptiness and count-match checks while producing an empty
    surface, which is why D3 counts coverage units rather than commands.
    """

    def test_empty_name_with_no_flags_or_positionals(
        self, validator: Draft202012Validator
    ) -> None:
        """``[{"name": ""}]`` — the exact shape that defeated three earlier guards."""
        contract = _minimal()
        contract["commands"] = [{"name": ""}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_empty_name_with_empty_flag_list(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"] = [{"name": "", "flags": []}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_empty_name_with_empty_positional_list(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"] = [{"name": "", "positionals": []}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_whitespace_only_command_name(
        self, validator: Draft202012Validator
    ) -> None:
        """Whitespace would count as a named subcommand while deriving no identifier."""
        contract = _minimal()
        contract["commands"] = [{"name": "   "}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_empty_name_with_a_positional_is_accepted(
        self, validator: Draft202012Validator
    ) -> None:
        """Negative control: positionals satisfy the floor just as flags do.

        Without this, the three rejections above could be passing because the
        schema rejects every empty-named command, which would wrongly forbid
        flat CLIs entirely.
        """
        contract = _minimal()
        contract["commands"] = [
            {"name": "", "positionals": [{"name": "target", "type": "path"}]}
        ]
        validator.validate(contract)


class TestRejectsMalformedFlags:
    def test_flag_name_must_carry_leading_dashes(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"] = [{"name": "descriptor", "type": "path"}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_flag_name_must_be_lowercase(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"] = [{"name": "--Descriptor", "type": "path"}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_flag_type_is_a_closed_enum(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"] = [{"name": "--count", "type": "int"}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_flag_requires_a_type(self, validator: Draft202012Validator) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"] = [{"name": "--descriptor"}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_short_form_is_a_single_letter(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"][0]["short"] = "-desc"
        with pytest.raises(Exception):
            validator.validate(contract)


class TestRejectsMalformedPositionals:
    def test_positional_name_must_be_non_whitespace(
        self, validator: Draft202012Validator
    ) -> None:
        """An unnamed positional is not a nameable coverage unit (design D3)."""
        contract = _minimal()
        contract["commands"][0]["positionals"] = [{"name": "  ", "type": "path"}]
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_positional_type_is_a_closed_enum(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["positionals"] = [
            {"name": "target", "type": "boolean"}  # valid for flags, not positionals
        ]
        with pytest.raises(Exception):
            validator.validate(contract)


class TestRejectsMalformedExitCodes:
    def test_exit_code_requires_a_meaning(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["exit_codes"] = [{"code": 64}]
        with pytest.raises(Exception):
            validator.validate(contract)

    @pytest.mark.parametrize("code", [-1, 256])
    def test_exit_code_is_within_process_range(
        self, validator: Draft202012Validator, code: int
    ) -> None:
        contract = _minimal()
        contract["exit_codes"] = [{"code": code, "meaning": "out of range"}]
        with pytest.raises(Exception):
            validator.validate(contract)


class TestRejectsMalformedBindings:
    @pytest.mark.parametrize("missing", ["location", "parameter"])
    def test_binding_requires_both_fields(
        self, validator: Draft202012Validator, missing: str
    ) -> None:
        binding = {"location": "query", "parameter": "descriptor"}
        del binding[missing]
        contract = _minimal()
        contract["commands"][0]["flags"][0]["binds_to"] = binding
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_binding_location_is_a_closed_enum(
        self, validator: Draft202012Validator
    ) -> None:
        contract = _minimal()
        contract["commands"][0]["flags"][0]["binds_to"] = {
            "location": "cookie",
            "parameter": "descriptor",
        }
        with pytest.raises(Exception):
            validator.validate(contract)

    def test_operation_ids_must_not_be_empty(
        self, validator: Draft202012Validator
    ) -> None:
        """An empty array asserts a binding while declaring none."""
        contract = _minimal()
        contract["commands"][0]["operation_ids"] = []
        with pytest.raises(Exception):
            validator.validate(contract)
