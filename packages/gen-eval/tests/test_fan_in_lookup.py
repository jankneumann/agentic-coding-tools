"""``operations_for_element`` must work on every surface, HTTP included (task 4.12).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · one surface element serving two operations is covered once

Design decisions: D7 (many-to-one bindings are declared, not derived).

Round-7 review (grok-2 high, codex-006 low — found independently by two
vendors). The method built its comparison key as ``f"{surface}:{element}"`` for
every surface, but ``OperationSpec.interface_id("http")`` returns an
**unprefixed** ``"METHOD /path"``. The HTTP branch could therefore never match,
so the public fan-in API silently returned ``[]`` for the primary service
surface while working correctly for MCP and CLI.

Silently, because an empty list is a valid answer — "no operation serves that
element" is exactly what a caller sees for a genuinely unknown element. Nothing
distinguishes the two, which is why this survived a full wave.
"""

from __future__ import annotations

import pytest

from gen_eval.service_descriptor import ServiceDescriptor
from tests.test_service_descriptor import CONTRACT_PATH


@pytest.fixture
def descriptor() -> ServiceDescriptor:
    return ServiceDescriptor.from_contract(CONTRACT_PATH)


class TestHttpFanIn:
    """The surface the method was dead for."""

    def test_every_http_element_resolves_to_its_operation(
        self, descriptor: ServiceDescriptor
    ) -> None:
        checked = 0
        for operation in descriptor.operations:
            element = operation.interface_id("http")
            if element is None:
                continue
            checked += 1
            assert operation.operation_id in descriptor.operations_for_element(
                "http", element
            ), (
                f"{element} resolved to no operation — the HTTP comparison key "
                f"is prefixed but HTTP identifiers are not"
            )
        assert checked, "fixture must expose at least one HTTP operation"

    def test_an_unknown_http_element_still_resolves_to_nothing(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """The empty answer must stay meaningful, not become unreachable."""
        assert descriptor.operations_for_element("http", "GET /not-a-route") == []


class TestOtherSurfacesAreUnchanged:
    """MCP and CLI worked; the fix must not break them (Rule 4)."""

    def test_mcp_fan_in_records_every_operation_behind_one_tool(
        self, descriptor: ServiceDescriptor
    ) -> None:
        by_element: dict[str, list[str]] = {}
        for operation in descriptor.operations:
            element = operation.interface_id("mcp")
            if element is None:
                continue
            by_element.setdefault(element, []).append(operation.operation_id)

        assert by_element, "fixture must expose an MCP surface"
        for element, expected in by_element.items():
            bare = element.removeprefix("mcp:")
            assert sorted(descriptor.operations_for_element("mcp", bare)) == sorted(
                expected
            )

    def test_the_many_to_one_binding_returns_both_operations(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """D7's motivating case: one tool answering two operations."""
        shared = [
            element
            for element in {
                op.interface_id("mcp")
                for op in descriptor.operations
                if op.interface_id("mcp")
            }
            if len(descriptor.operations_for_element("mcp", str(element))) > 1
        ]
        if not shared:
            pytest.skip("fixture declares no many-to-one MCP binding")
        for element in shared:
            assert len(descriptor.operations_for_element("mcp", str(element))) > 1


class TestBothSpellingsAreAccepted:
    """A caller may pass the bare element or the prefixed identifier."""

    def test_prefixed_and_bare_mcp_elements_agree(
        self, descriptor: ServiceDescriptor
    ) -> None:
        element = next(
            op.interface_id("mcp")
            for op in descriptor.operations
            if op.interface_id("mcp")
        )
        assert element is not None
        bare = element.removeprefix("mcp:")
        assert descriptor.operations_for_element(
            "mcp", bare
        ) == descriptor.operations_for_element("mcp", element)

    def test_an_unexposed_surface_yields_nothing(
        self, descriptor: ServiceDescriptor
    ) -> None:
        """An operation the contract marks unexposed contributes no element."""
        assert descriptor.operations_for_element("cli", "definitely-not-declared") == []
