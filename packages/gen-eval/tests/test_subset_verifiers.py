"""The implementation exposes no surface its contract omits (task 4.1).

Spec scenarios:
  - gen-eval-framework.implemented-surface-subset-verification
      · undocumented CLI flag is reported
      · verification distinguishes excess from omission

Design decisions: D1 (the contract is the source; introspection only verifies).

D1 makes the contract the declared surface and forbids introspection from
*populating* it. That leaves one job introspection is still needed for, and it
runs in one direction only: the implementation must be a **subset** of the
contract. Excess is a contract violation — a flag users can reach that nothing
documents. Omission is not: a contracted flag the parser never grew is a
coverage gap, reported by the coverage model, and reporting it here as well
would mean the same defect arrives twice under two names.

That asymmetry is the whole design, so the negative control matters as much as
the positive one: a parser missing a contracted flag must produce **zero**
violations here.

``--help`` is the standing case for exclusions. argparse installs it; the
application never declares it; the contract deliberately omits it (see the
header of ``openspec/contracts/gen-eval-framework/cli/gen-eval.yaml``). A
verifier that reported it would be wrong on every argparse program ever
written.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from gen_eval.descriptor import ToolDescriptor
from gen_eval.service_descriptor import ServiceDescriptor
from gen_eval.verify import Violation, verify_argparse, verify_fastapi, verify_mcp
from tests.test_service_descriptor import CONTRACT_PATH

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_CONTRACT = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"

CONTRACT_TEXT = """\
contract_version: "1"
tool:
  name: widget
  executable: widget
commands:
  - name: ""
    flags:
      - name: --input
        type: path
        required: true
      - name: --dry-run
        type: boolean
      - name: --verbose
        short: -v
        type: boolean
"""


@pytest.fixture(scope="module")
def widget(tmp_path_factory: pytest.TempPathFactory) -> ToolDescriptor:
    path = tmp_path_factory.mktemp("contract") / "widget.yaml"
    path.write_text(CONTRACT_TEXT)
    return ToolDescriptor.from_contract(path)


@pytest.fixture(scope="module")
def gen_eval_tool() -> ToolDescriptor:
    return ToolDescriptor.from_contract(CLI_CONTRACT)


def conformant_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="widget")
    parser.add_argument("--input", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def elements(violations: list[Violation]) -> set[str]:
    return {violation.element for violation in violations}


# ---------------------------------------------------------------------------
# Excess
# ---------------------------------------------------------------------------


class TestUndocumentedFlagIsReported:
    def test_an_undocumented_flag_produces_a_violation(self, widget: ToolDescriptor) -> None:
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--force"}

    def test_the_violation_names_the_flag(self, widget: ToolDescriptor) -> None:
        """An operator has to be able to act on it without re-deriving anything."""
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        (violation,) = verify_argparse(parser, widget)
        assert "--force" in violation.message
        assert violation.surface == "cli"

    def test_every_undocumented_flag_is_reported_not_just_the_first(
        self, widget: ToolDescriptor
    ) -> None:
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--retry", type=int)
        assert elements(verify_argparse(parser, widget)) == {"cli:--force", "cli:--retry"}

    def test_an_undocumented_short_flag_is_reported_under_its_long_name(
        self, widget: ToolDescriptor
    ) -> None:
        """One action is one flag however many spellings it has."""
        parser = conformant_parser()
        parser.add_argument("--quiet", "-q", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--quiet"}


# ---------------------------------------------------------------------------
# Not excess
# ---------------------------------------------------------------------------


class TestConformantImplementationIsSilent:
    def test_a_conformant_parser_reports_nothing(self, widget: ToolDescriptor) -> None:
        assert verify_argparse(conformant_parser(), widget) == []

    def test_the_argparse_supplied_help_flag_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        """argparse installs --help; the application never declared it.

        Reporting it would make the verifier wrong on every argparse program,
        and it is why the gen-eval contract documents the omission rather than
        contracting a flag it does not own.
        """
        assert "cli:--help" not in elements(verify_argparse(conformant_parser(), widget))

    def test_an_argparse_version_action_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        parser = conformant_parser()
        parser.add_argument("--version", action="version", version="1.0")
        assert verify_argparse(parser, widget) == []

    def test_a_positional_argument_is_not_reported_as_a_flag(
        self, widget: ToolDescriptor
    ) -> None:
        """A positional has no option strings; it is a different coverage unit."""
        parser = conformant_parser()
        parser.add_argument("target")
        assert elements(verify_argparse(parser, widget)) == set()


class TestOmissionIsCoveragesJob:
    """The asymmetry D1 rests on, asserted as a negative control."""

    def test_a_contracted_flag_the_parser_lacks_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="widget")
        parser.add_argument("--input", required=True)
        assert verify_argparse(parser, widget) == []

    def test_a_parser_declaring_nothing_at_all_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        """Zero violations, three uncovered units. Two different reports."""
        assert verify_argparse(argparse.ArgumentParser(prog="widget"), widget) == []

    def test_excess_and_omission_together_report_only_the_excess(
        self, widget: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="widget")
        parser.add_argument("--input", required=True)
        parser.add_argument("--force", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--force"}


# ---------------------------------------------------------------------------
# Against the real contract
# ---------------------------------------------------------------------------


class TestAgainstGenEvalsOwnContract:
    """The surface this change owns end to end (task 4.7 wires it into CI)."""

    def test_a_parser_matching_the_contract_is_silent(
        self, gen_eval_tool: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="gen-eval")
        for unit in gen_eval_tool.all_interfaces():
            parser.add_argument(unit.removeprefix("cli:"), action="store_true")
        assert verify_argparse(parser, gen_eval_tool) == []

    def test_adding_one_uncontracted_flag_turns_it_red(
        self, gen_eval_tool: ToolDescriptor
    ) -> None:
        """The gate must be shown to fail, not merely to pass."""
        parser = argparse.ArgumentParser(prog="gen-eval")
        for unit in gen_eval_tool.all_interfaces():
            parser.add_argument(unit.removeprefix("cli:"), action="store_true")
        parser.add_argument("--undeclared", action="store_true")
        assert elements(verify_argparse(parser, gen_eval_tool)) == {"cli:--undeclared"}


# ---------------------------------------------------------------------------
# HTTP (task 4.3)
# ---------------------------------------------------------------------------


CONFORMANT_PATHS = {
    "/locks/acquire": {"post": {"operationId": "acquire_lock"}},
    "/locks/active": {"get": {"operationId": "list_active_locks"}},
    "/locks/status/{path}": {"get": {"operationId": "get_lock_status"}},
    "/locks/{lock_id}": {"delete": {"operationId": "release_lock"}},
    "/locks/reap": {"post": {"operationId": "reap_expired_locks"}},
}


def openapi_document(paths: dict[str, Any]) -> dict[str, Any]:
    return {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": paths}


class _AppLike:
    """Stands in for a FastAPI app: something with a callable ``openapi()``."""

    def __init__(self, document: dict[str, Any]) -> None:
        self._document = document

    def openapi(self) -> dict[str, Any]:
        return self._document


@pytest.fixture(scope="module")
def service() -> ServiceDescriptor:
    return ServiceDescriptor.from_contract(CONTRACT_PATH)


class TestUndocumentedEndpointIsReported:
    def test_an_undocumented_route_produces_a_violation(self, service: ServiceDescriptor) -> None:
        paths = {**CONFORMANT_PATHS, "/locks/steal": {"post": {"operationId": "steal_lock"}}}
        violations = verify_fastapi(openapi_document(paths), service)
        assert elements(violations) == {"POST /locks/steal"}

    def test_the_violation_names_the_route_and_the_surface(
        self, service: ServiceDescriptor
    ) -> None:
        paths = {**CONFORMANT_PATHS, "/locks/steal": {"post": {}}}
        (violation,) = verify_fastapi(openapi_document(paths), service)
        assert "/locks/steal" in violation.message
        assert violation.surface == "http"

    def test_an_undocumented_method_on_a_contracted_path_is_reported(
        self, service: ServiceDescriptor
    ) -> None:
        """The path is contracted; this verb on it is not. Method is part of the element."""
        paths = {**CONFORMANT_PATHS, "/locks/acquire": {"post": {}, "put": {}}}
        assert elements(verify_fastapi(openapi_document(paths), service)) == {
            "PUT /locks/acquire"
        }


class TestConformantApplicationIsSilent:
    def test_a_conformant_document_reports_nothing(self, service: ServiceDescriptor) -> None:
        assert verify_fastapi(openapi_document(CONFORMANT_PATHS), service) == []

    def test_a_parametric_path_matches_its_contracted_template(
        self, service: ServiceDescriptor
    ) -> None:
        """Both sides spell the template the same way; no regex needed here."""
        paths = {"/locks/status/{path}": {"get": {}}}
        assert verify_fastapi(openapi_document(paths), service) == []

    def test_a_contracted_route_the_app_lacks_is_not_a_violation(
        self, service: ServiceDescriptor
    ) -> None:
        """Omission is coverage's job on this surface too."""
        assert verify_fastapi(openapi_document({}), service) == []

    def test_path_item_keys_that_are_not_methods_are_ignored(
        self, service: ServiceDescriptor
    ) -> None:
        """``parameters`` and ``summary`` are siblings of the verbs, not verbs."""
        paths = {
            "/locks/acquire": {
                "post": {},
                "parameters": [{"name": "x", "in": "query"}],
                "summary": "Locks.",
            }
        }
        assert verify_fastapi(openapi_document(paths), service) == []

    def test_an_app_object_is_accepted_as_well_as_a_document(
        self, service: ServiceDescriptor
    ) -> None:
        """`verify_fastapi(app, ...)` is the documented call; fastapi is not imported."""
        app = _AppLike(openapi_document({**CONFORMANT_PATHS, "/locks/steal": {"post": {}}}))
        assert elements(verify_fastapi(app, service)) == {"POST /locks/steal"}

    def test_a_surface_the_contract_marks_unexposed_is_not_an_http_violation(
        self, service: ServiceDescriptor
    ) -> None:
        """``release_lock`` is exposed on HTTP and not on CLI. This is the HTTP check."""
        assert verify_fastapi(openapi_document({"/locks/{lock_id}": {"delete": {}}}), service) == []


# ---------------------------------------------------------------------------
# MCP (task 4.5)
# ---------------------------------------------------------------------------


#: What the fixture contract's MCP surface actually exposes. Three tools for
#: four exposed operations — list_active_locks and get_lock_status both bind
#: to check_locks. reap_expired_locks is exposed: false on MCP.
CONFORMANT_TOOLS = ["acquire_lock", "check_locks", "release_lock"]


class _ToolObject:
    """Stands in for an SDK tool record, which is an object with ``.name``."""

    def __init__(self, name: str) -> None:
        self.name = name


class TestManyToOneIsNotAFalsePositive:
    """The case the carve-out exists for (D4, D7).

    The real coordinator's ``check_locks`` serves both ``list_active_locks``
    and ``get_lock_status`` by branching on ``file_paths`` being None. A
    verifier comparing the server's listing against one derived name per
    operation reports THREE findings here, all wrong: ``check_locks`` as
    undocumented excess, plus two tools that do not exist as omissions.

    Comparison is against the set of BOUND elements, which is why zero is the
    right answer.
    """

    def test_a_conformant_listing_reports_nothing(self, service: ServiceDescriptor) -> None:
        assert verify_mcp(CONFORMANT_TOOLS, service) == []

    def test_the_shared_tool_is_not_reported_as_undocumented(
        self, service: ServiceDescriptor
    ) -> None:
        assert "mcp:check_locks" not in elements(verify_mcp(CONFORMANT_TOOLS, service))

    @pytest.mark.parametrize("operation_id", ["list_active_locks", "get_lock_status"])
    def test_the_bound_operations_are_not_reported_as_missing_tools(
        self, service: ServiceDescriptor, operation_id: str
    ) -> None:
        assert f"mcp:{operation_id}" not in elements(verify_mcp(CONFORMANT_TOOLS, service))

    def test_a_server_exposing_an_operation_id_instead_of_the_bound_element_is_excess(
        self, service: ServiceDescriptor
    ) -> None:
        """The sharp edge: comparison is against bound elements, not operation ids.

        ``list_active_locks`` is a real operation, and the contract says
        ``check_locks`` serves it. A server publishing a tool by that name is
        publishing something the contract does not describe.
        """
        tools = [*CONFORMANT_TOOLS, "list_active_locks"]
        assert elements(verify_mcp(tools, service)) == {"mcp:list_active_locks"}


class TestUndocumentedToolIsReported:
    def test_an_undocumented_tool_produces_a_violation(self, service: ServiceDescriptor) -> None:
        assert elements(verify_mcp([*CONFORMANT_TOOLS, "steal_lock"], service)) == {
            "mcp:steal_lock"
        }

    def test_the_violation_names_the_tool_and_the_surface(
        self, service: ServiceDescriptor
    ) -> None:
        (violation,) = verify_mcp([*CONFORMANT_TOOLS, "steal_lock"], service)
        assert "steal_lock" in violation.message
        assert violation.surface == "mcp"

    def test_a_tool_the_contract_marks_unexposed_on_mcp_is_a_violation(
        self, service: ServiceDescriptor
    ) -> None:
        """``reap_expired_locks`` is contracted `exposed: false` — internal only.

        Publishing it anyway is the case exposed:false exists to catch: the
        operation is real, and the contract's claim that agents cannot reach it
        has stopped being true.
        """
        tools = [*CONFORMANT_TOOLS, "reap_expired_locks"]
        assert elements(verify_mcp(tools, service)) == {"mcp:reap_expired_locks"}


class TestMcpOmissionAndInputShapes:
    def test_a_contracted_tool_the_server_lacks_is_not_a_violation(
        self, service: ServiceDescriptor
    ) -> None:
        assert verify_mcp([], service) == []

    def test_tool_objects_are_accepted_as_well_as_names(
        self, service: ServiceDescriptor
    ) -> None:
        """An SDK listing yields records, not strings."""
        tools = [_ToolObject(name) for name in [*CONFORMANT_TOOLS, "steal_lock"]]
        assert elements(verify_mcp(tools, service)) == {"mcp:steal_lock"}

    def test_tool_dicts_are_accepted_as_well_as_names(
        self, service: ServiceDescriptor
    ) -> None:
        """A JSON-RPC ``tools/list`` response yields dicts."""
        tools = [{"name": name} for name in [*CONFORMANT_TOOLS, "steal_lock"]]
        assert elements(verify_mcp(tools, service)) == {"mcp:steal_lock"}

    def test_a_tool_descriptor_has_no_mcp_surface_so_everything_is_excess(
        self, widget: ToolDescriptor
    ) -> None:
        """Negative control on declared_elements: no MCP contract, no MCP tools.

        A tool contract declares a CLI surface only. A server claiming to
        implement it while publishing MCP tools is publishing surface the
        contract does not describe at all.
        """
        assert elements(verify_mcp(["anything"], widget)) == {"mcp:anything"}
