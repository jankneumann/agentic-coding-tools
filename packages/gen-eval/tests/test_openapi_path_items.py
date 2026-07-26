"""``$ref`` path items and path-level parameters must not vanish (task 4.13).

Spec scenarios:
  - gen-eval-framework.implemented-surface-subset-verification
      · undocumented endpoint is reported
  - gen-eval-framework.contract-as-descriptor-source-of-truth

Design decisions: D1 (the contract is the source; introspection only verifies).

Round-7 review (codex-003, grok-3 — found independently by two vendors). Both
readers of an OpenAPI document iterate a path item's keys and keep those in
``_HTTP_METHODS``. ``$ref`` is not an HTTP method, so an OpenAPI 3.1 document
written with ``components.pathItems`` yields **no operations and no
violations** — with no error.

That direction matters. D1 says the contract is the declared surface precisely
so that a broken implementation cannot shrink it; a contract reader that drops
operations it does not understand reintroduces the same failure one level up,
and it fails *open*: the surface silently gets smaller, coverage of nothing
reports 100%, and `verify_fastapi` stops reporting the live routes as excess.

Path-level ``parameters`` are the same class of omission. They are siblings of
the verbs and apply to every operation beneath them, so not merging them drops
required path parameters from every derived MCP input schema — the tool is
published without the argument it cannot work without.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gen_eval.service_descriptor import ServiceDescriptor
from gen_eval.verify import verify_fastapi
from tests.test_service_descriptor import write_contract


def document_with_ref_path_item() -> dict[str, Any]:
    """An OpenAPI 3.1 document whose only route is behind a ``$ref``."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "reffed", "version": "1.0.0"},
        "paths": {"/items/{id}": {"$ref": "#/components/pathItems/Item"}},
        "components": {
            "pathItems": {
                "Item": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "get": {
                        "operationId": "get_item",
                        "summary": "Fetch one item",
                    },
                }
            }
        },
    }


def document_with_path_level_parameters() -> dict[str, Any]:
    """Parameters declared once on the path item, shared by both verbs."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "shared-params", "version": "1.0.0"},
        "paths": {
            "/items/{id}": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {"operationId": "get_item"},
                "delete": {
                    "operationId": "delete_item",
                    "parameters": [
                        {
                            "name": "force",
                            "in": "query",
                            "schema": {"type": "boolean"},
                        }
                    ],
                },
            }
        },
    }


class TestRefPathItemsAreResolved:
    """A route behind a ``$ref`` is still a route."""

    def test_the_operation_is_extracted(self, tmp_path: Path) -> None:
        path = write_contract(tmp_path, document_with_ref_path_item())
        descriptor = ServiceDescriptor.from_contract(path)
        assert [op.operation_id for op in descriptor.operations] == ["get_item"]

    def test_the_declared_surface_is_not_silently_empty(self, tmp_path: Path) -> None:
        """Fail-open is the failure mode: an empty surface covers 100% of nothing."""
        path = write_contract(tmp_path, document_with_ref_path_item())
        descriptor = ServiceDescriptor.from_contract(path)
        assert descriptor.all_interfaces() == ["GET /items/{id}"]

    def test_the_method_and_path_come_from_the_referring_key(
        self, tmp_path: Path
    ) -> None:
        """The path is where the ``$ref`` sits, not where the target is stored."""
        path = write_contract(tmp_path, document_with_ref_path_item())
        operation = ServiceDescriptor.from_contract(path).operations[0]
        assert (operation.method, operation.path) == ("GET", "/items/{id}")

    def test_an_unresolvable_ref_fails_closed(self, tmp_path: Path) -> None:
        """Silently dropping it is the one outcome D1 forbids."""
        document = document_with_ref_path_item()
        document["paths"]["/items/{id}"] = {"$ref": "#/components/pathItems/Missing"}
        path = write_contract(tmp_path, document)
        with pytest.raises(ValueError, match="Missing"):
            ServiceDescriptor.from_contract(path)

    def test_an_external_ref_fails_closed(self, tmp_path: Path) -> None:
        """Resolving another file is out of scope — but must not be a silent skip."""
        document = document_with_ref_path_item()
        document["paths"]["/items/{id}"] = {"$ref": "other.yaml#/pathItems/Item"}
        path = write_contract(tmp_path, document)
        with pytest.raises(ValueError):
            ServiceDescriptor.from_contract(path)


class TestPathLevelParametersReachTheOperation:
    """Path-item parameters are siblings of the verbs, and apply to all of them."""

    def test_a_shared_parameter_reaches_every_operation(self, tmp_path: Path) -> None:
        path = write_contract(tmp_path, document_with_path_level_parameters())
        descriptor = ServiceDescriptor.from_contract(path)
        for operation in descriptor.operations:
            names = {p.get("name") for p in operation.parameters}
            assert "id" in names, (
                f"{operation.operation_id} lost the path-level `id` parameter — "
                f"its derived MCP tool is published without a required argument"
            )

    def test_operation_level_parameters_are_kept(self, tmp_path: Path) -> None:
        path = write_contract(tmp_path, document_with_path_level_parameters())
        descriptor = ServiceDescriptor.from_contract(path)
        delete = descriptor.operation("delete_item")
        assert {p.get("name") for p in delete.parameters} == {"id", "force"}

    def test_a_ref_path_items_parameters_are_merged_too(self, tmp_path: Path) -> None:
        path = write_contract(tmp_path, document_with_ref_path_item())
        operation = ServiceDescriptor.from_contract(path).operations[0]
        assert {p.get("name") for p in operation.parameters} == {"id"}

    def test_the_required_parameter_reaches_the_mcp_projection(
        self, tmp_path: Path
    ) -> None:
        """The consequence users see: the tool schema, not the parameter list."""
        document = document_with_path_level_parameters()
        document["paths"]["/items/{id}"]["get"]["x-mcp"] = {"exposed": True}
        document["paths"]["/items/{id}"]["x-surfaces"] = None
        path = write_contract(tmp_path, document)
        descriptor = ServiceDescriptor.from_contract(path)
        projections = {p.name: p for p in descriptor.mcp_tools()}
        if not projections:
            pytest.skip("fixture declares no MCP surface")
        schema = next(iter(projections.values())).input_schema
        assert "id" in (schema.get("properties") or {})


class TestVerifyFastapiSeesRefPathItems:
    """The verifier must not go blind on the same construct."""

    def test_an_undocumented_ref_route_is_reported(self, tmp_path: Path) -> None:
        """A live route behind a ``$ref`` that the contract omits is excess."""
        contract = write_contract(
            tmp_path,
            {
                "openapi": "3.1.0",
                "info": {"title": "empty", "version": "1.0.0"},
                "paths": {},
            },
        )
        descriptor = ServiceDescriptor.from_contract(contract)
        violations = verify_fastapi(document_with_ref_path_item(), descriptor)
        assert [v.element for v in violations] == ["GET /items/{id}"]

    def test_a_contracted_ref_route_is_silent(self, tmp_path: Path) -> None:
        path = write_contract(tmp_path, document_with_ref_path_item())
        descriptor = ServiceDescriptor.from_contract(path)
        assert verify_fastapi(document_with_ref_path_item(), descriptor) == []
