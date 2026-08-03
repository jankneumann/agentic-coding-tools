"""A fan-in merge must not invent a type neither operation declared (task 4.18).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · one surface element serving two operations is covered once

Design decisions: D7 (many-to-one bindings are declared, not derived).

Round-7 review. ``_merge_schemas`` unions properties with a dict spread, so
when two bound operations both declare ``id`` — one an integer, one a string —
the tool is published with whichever came last. Every call routed to the other
operation then fails validation against a schema that operation never declared.

Contrast the ``required`` handling directly above it: intersecting is a
*reasoned* narrowing, argued in the design and load-bearing for the real
``check_locks`` shape. Property clobber is not reasoned; it is the dict spread's
default, and it silently answers a question the contract left contradictory.

D7 says a many-to-one binding is *declared*. Declaring one is therefore a claim
the contract author makes, and an incoherent claim is an error in the contract —
something to report at derivation time, when the author can still fix it, rather
than resolve by argument order and discover in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gen_eval.service_descriptor import ServiceDescriptor, _merge_schemas
from tests.test_service_descriptor import CONTRACT_PATH, write_contract


def schema(**properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties)}


def fan_in_contract(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Two operations bound to one MCP tool, each declaring an ``id`` query."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "fan-in", "version": "1.0.0"},
        "paths": {
            "/things/{id}": {
                "get": {
                    "operationId": "get_thing",
                    "summary": "Fetch a thing.",
                    "parameters": [
                        {"name": "id", "in": "query", "schema": left},
                    ],
                    "x-gen-eval-surface": {
                        "http": {"exposed": True, "element": "GET /things/{id}"},
                        "mcp": {"exposed": True, "element": "thing"},
                    },
                },
                "delete": {
                    "operationId": "delete_thing",
                    "summary": "Remove a thing.",
                    "parameters": [
                        {"name": "id", "in": "query", "schema": right},
                    ],
                    "x-gen-eval-surface": {
                        "http": {"exposed": True, "element": "DELETE /things/{id}"},
                        "mcp": {"exposed": True, "element": "thing"},
                    },
                },
            }
        },
    }


class TestConflictingPropertiesAreReported:
    """The merge must refuse to pick a winner."""

    def test_a_type_conflict_raises(self) -> None:
        with pytest.raises(ValueError, match="id"):
            _merge_schemas(
                schema(id={"type": "integer"}),
                schema(id={"type": "string"}),
                element="mcp:thing",
            )

    def test_the_message_names_the_element_and_both_schemas(self) -> None:
        """The author has to see which contract statement to change."""
        with pytest.raises(ValueError) as excinfo:
            _merge_schemas(
                schema(id={"type": "integer"}),
                schema(id={"type": "string"}),
                element="mcp:thing",
            )
        message = str(excinfo.value)
        assert "mcp:thing" in message
        assert "integer" in message and "string" in message

    def test_an_enum_conflict_raises(self) -> None:
        """Not only ``type`` — any validation-bearing difference is a conflict."""
        with pytest.raises(ValueError, match="mode"):
            _merge_schemas(
                schema(mode={"type": "string", "enum": ["a"]}),
                schema(mode={"type": "string", "enum": ["b"]}),
                element="mcp:thing",
            )

    def test_a_nested_conflict_raises(self) -> None:
        with pytest.raises(ValueError, match="tags"):
            _merge_schemas(
                schema(tags={"type": "array", "items": {"type": "string"}}),
                schema(tags={"type": "array", "items": {"type": "integer"}}),
                element="mcp:thing",
            )


class TestCompatibleMergesStillSucceed:
    """Rule 4 — everything that merged cleanly before must still merge."""

    def test_disjoint_properties_union(self) -> None:
        merged = _merge_schemas(
            schema(a={"type": "string"}),
            schema(b={"type": "integer"}),
            element="mcp:thing",
        )
        assert set(merged["properties"]) == {"a", "b"}

    def test_an_identical_property_merges_once(self) -> None:
        merged = _merge_schemas(
            schema(id={"type": "string"}),
            schema(id={"type": "string"}),
            element="mcp:thing",
        )
        assert merged["properties"] == {"id": {"type": "string"}}

    def test_an_annotation_only_difference_is_not_a_conflict(self) -> None:
        """Two operations describe the same argument in their own words."""
        merged = _merge_schemas(
            schema(id={"type": "string", "description": "the thing to fetch"}),
            schema(id={"type": "string", "description": "the thing to delete"}),
            element="mcp:thing",
        )
        assert merged["properties"]["id"]["type"] == "string"

    def test_required_still_intersects(self) -> None:
        """The reasoned narrowing directly above the clobber is untouched."""
        merged = _merge_schemas(
            {
                "type": "object",
                "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
                "required": ["a", "b"],
            },
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
            },
            element="mcp:thing",
        )
        assert merged["required"] == ["a"]

    def test_the_real_contract_still_projects(self) -> None:
        """The repo's own service contract must not start raising."""
        descriptor = ServiceDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.mcp_tools() is not None


class TestTheConflictSurfacesThroughTheProjection:
    """The defect is only reachable via a declared many-to-one binding."""

    def test_deriving_a_conflicted_fan_in_tool_raises(self, tmp_path: Path) -> None:
        """It fails at derivation, not at first use — the contract is read there."""
        path = write_contract(
            tmp_path, fan_in_contract({"type": "integer"}, {"type": "string"})
        )
        with pytest.raises(ValueError, match="mcp:thing"):
            ServiceDescriptor.from_contract(path)

    def test_a_coherent_fan_in_tool_still_projects(self, tmp_path: Path) -> None:
        path = write_contract(
            tmp_path, fan_in_contract({"type": "string"}, {"type": "string"})
        )
        descriptor = ServiceDescriptor.from_contract(path)
        tools = descriptor.mcp_tools()
        assert [t.name for t in tools] == ["thing"]
        assert sorted(tools[0].operation_ids) == ["delete_thing", "get_thing"]
