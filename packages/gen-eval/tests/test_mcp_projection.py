"""The OpenAPI-to-MCP projection and its three carve-outs (task 2.3).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · a surface that does not expose an operation is not a gap
      · one surface element serving two operations is covered once
      · the many-to-one binding is authorable in a contract

Design decisions: D4 (coverage keyed on operation × surface), D7 (the
projection is mechanical but not total).

D7's projection is a **default, not a law**, and the three carve-outs are
what stop it from inventing a surface:

``description``
    Copied from the operation verbatim. An agent reads it to decide whether
    to call the tool, so paraphrasing or truncating it changes behaviour —
    the contract has to be authored for agent consumption, not only for
    validation.
``resources and prompts``
    Not operations. They may be declared, and they stay out of operation ×
    surface coverage entirely; counting them as uncovered interfaces would be
    a permanent false gap.
``many-to-one``
    One MCP tool may serve several operations. ``check_locks`` serves both
    ``list_active_locks`` and ``get_lock_status`` in the real coordinator by
    branching on ``file_paths`` being None. Deriving one tool per operation
    there invents two tools that do not exist — and then subset verification
    reports three findings: ``check_locks`` as undocumented excess plus two
    invented tools as omissions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from gen_eval.service_descriptor import ServiceDescriptor
from tests.test_service_descriptor import CONTRACT_PATH, write_contract

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def descriptor() -> ServiceDescriptor:
    return ServiceDescriptor.from_contract(CONTRACT_PATH)


def tool_named(descriptor: ServiceDescriptor, name: str) -> Any:
    for tool in descriptor.mcp_tools():
        if tool.name == name:
            return tool
    raise AssertionError(
        f"no projected tool {name!r} in {[t.name for t in descriptor.mcp_tools()]}"
    )


PARAMETER_CONTRACT: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "params", "version": "1.0.0"},
    "paths": {
        "/items/{item_id}": {
            "post": {
                "operationId": "update_item",
                "summary": "Update an item.",
                "x-gen-eval-surface": {
                    "http": {"exposed": True, "element": "POST /items/{item_id}"},
                    "mcp": {"exposed": True},
                },
                "parameters": [
                    {
                        "name": "item_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {"name": "dry_run", "in": "query", "schema": {"type": "boolean"}},
                    {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                },
                            }
                        }
                    },
                },
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}

CARVE_OUT_CONTRACT: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "carve", "version": "1.0.0"},
    "x-gen-eval-mcp": {
        "resources": ["config://settings", "log://recent"],
        "prompts": ["summarize_incident"],
    },
    "paths": {
        "/things": {
            "get": {
                "operationId": "list_things",
                "summary": "List things.",
                "x-gen-eval-surface": {
                    "http": {"exposed": True, "element": "GET /things"},
                    "mcp": {"exposed": True, "element": "list_things"},
                },
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


# ---------------------------------------------------------------------------
# The mechanical part
# ---------------------------------------------------------------------------


class TestProjection:
    def test_a_tool_is_projected_per_exposed_operation(self, descriptor: ServiceDescriptor) -> None:
        names = {tool.name for tool in descriptor.mcp_tools()}
        assert names == {"acquire_lock", "check_locks", "release_lock"}

    def test_the_tool_name_defaults_to_the_operation_id(self, tmp_path: Path) -> None:
        """Derivation is the default; a binding without an element still derives."""
        derived = ServiceDescriptor.from_contract(write_contract(tmp_path, PARAMETER_CONTRACT))
        assert [tool.name for tool in derived.mcp_tools()] == ["update_item"]

    def test_input_schema_flattens_path_query_and_body(self, tmp_path: Path) -> None:
        derived = ServiceDescriptor.from_contract(write_contract(tmp_path, PARAMETER_CONTRACT))
        schema = tool_named(derived, "update_item").input_schema
        assert set(schema["properties"]) == {"item_id", "dry_run", "title", "tags"}
        assert schema["type"] == "object"

    def test_required_parameters_stay_required(self, tmp_path: Path) -> None:
        derived = ServiceDescriptor.from_contract(write_contract(tmp_path, PARAMETER_CONTRACT))
        assert set(tool_named(derived, "update_item").input_schema["required"]) == {
            "item_id",
            "title",
        }

    def test_header_parameters_are_not_flattened_into_the_tool_input(self, tmp_path: Path) -> None:
        """D7 names (path, query, body). Transport headers are not tool arguments."""
        derived = ServiceDescriptor.from_contract(write_contract(tmp_path, PARAMETER_CONTRACT))
        assert "X-Trace" not in tool_named(derived, "update_item").input_schema["properties"]


# ---------------------------------------------------------------------------
# Carve-out 1 — descriptions are load-bearing
# ---------------------------------------------------------------------------


class TestCarveOutDescriptions:
    def test_carve_out_description_is_copied_verbatim(self, descriptor: ServiceDescriptor) -> None:
        """Byte-for-byte. An agent reads this to decide whether to call."""
        summary = descriptor.operation("acquire_lock").summary
        assert summary  # the fixture must actually carry one
        assert tool_named(descriptor, "acquire_lock").description == summary

    def test_carve_out_a_fan_in_tool_keeps_every_bound_description(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """Dropping one operation's summary hides half of what the tool does."""
        description = tool_named(descriptor, "check_locks").description
        for operation_id in ("list_active_locks", "get_lock_status"):
            assert descriptor.operation(operation_id).summary in description


# ---------------------------------------------------------------------------
# Carve-out 2 — resources and prompts are not operations
# ---------------------------------------------------------------------------


class TestCarveOutResourcesAndPrompts:
    @pytest.fixture(scope="class")
    def carved(self, tmp_path_factory: pytest.TempPathFactory) -> ServiceDescriptor:
        path = write_contract(tmp_path_factory.mktemp("carve"), CARVE_OUT_CONTRACT)
        return ServiceDescriptor.from_contract(path)

    def test_resources_and_prompts_are_declared(self, carved: ServiceDescriptor) -> None:
        """A descriptor MAY declare them — the carve-out is about coverage."""
        assert carved.mcp_resources == ["config://settings", "log://recent"]
        assert carved.mcp_prompts == ["summarize_incident"]

    def test_carve_out_resources_are_not_projected_as_tools(
        self, carved: ServiceDescriptor
    ) -> None:
        assert [tool.name for tool in carved.mcp_tools()] == ["list_things"]

    def test_resources_do_not_appear_in_the_declared_surface(
        self, carved: ServiceDescriptor
    ) -> None:
        surface = carved.all_interfaces()
        assert not [i for i in surface if "config://" in i or "log://" in i]
        assert "mcp:summarize_incident" not in surface

    def test_carve_out_resources_do_not_count_as_coverage_units(
        self, carved: ServiceDescriptor
    ) -> None:
        """Three declared resources/prompts, one operation. The unit is the operation."""
        assert carved.coverage_unit_count() == 1


# ---------------------------------------------------------------------------
# Carve-out 3 — many-to-one is declared, not derived
# ---------------------------------------------------------------------------


class TestCarveOutManyToOne:
    def test_carve_out_an_explicit_binding_suppresses_name_derivation(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """Two operations, one bound element, one tool — not two.

        This is the assertion the whole carve-out exists for: the derived
        names must NOT appear alongside the bound one.
        """
        names = [tool.name for tool in descriptor.mcp_tools()]
        assert names.count("check_locks") == 1
        assert "list_active_locks" not in names
        assert "get_lock_status" not in names

    def test_carve_out_the_fan_in_is_recorded(self, descriptor: ServiceDescriptor) -> None:
        """Without the record, coverage cannot credit both operations later."""
        assert sorted(tool_named(descriptor, "check_locks").operation_ids) == [
            "get_lock_status",
            "list_active_locks",
        ]

    def test_carve_out_a_one_to_one_tool_records_its_single_operation(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """Negative control: fan-in is not recorded for everything indiscriminately."""
        assert tool_named(descriptor, "acquire_lock").operation_ids == ["acquire_lock"]

    def test_carve_out_an_unexposed_operation_is_not_projected(
        self, descriptor: ServiceDescriptor
    ) -> None:
        names = [tool.name for tool in descriptor.mcp_tools()]
        assert "reap_expired_locks" not in names

    def test_the_fan_in_input_schema_unions_both_operations(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """One tool serving two operations must accept either one's arguments."""
        schema = tool_named(descriptor, "check_locks").input_schema
        assert "path" in schema["properties"]

    def test_a_parameter_required_by_only_one_bound_operation_is_optional(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """``path`` is required for get_lock_status and absent from list_active_locks.

        Marking it globally required would make the tool unable to express
        the listing call at all — the real ``check_locks`` branches on the
        argument being None.
        """
        schema = tool_named(descriptor, "check_locks").input_schema
        assert "path" not in schema.get("required", [])

    def test_the_declared_surface_counts_the_bound_element_once(
        self, descriptor: ServiceDescriptor
    ) -> None:
        assert descriptor.all_interfaces().count("mcp:check_locks") == 1

    def test_the_binding_is_authorable_in_the_contract(self) -> None:
        """The spec rejects a binding that exists only in derived output."""
        contract = yaml.safe_load(CONTRACT_PATH.read_text())
        elements = [
            operation.get("x-gen-eval-surface", {}).get("mcp", {}).get("element")
            for item in contract["paths"].values()
            for operation in item.values()
        ]
        assert elements.count("check_locks") == 2
