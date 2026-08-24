"""Traceability parsing on both contract archetypes, and citation resolution
(tasks 2.0-2.2, 2.4-2.5).

Spec scenarios:
  - Contracted Operations Cite The Requirements They Serve
      · an operation declares its citations
      · a citation names a requirement that exists

Design decisions: D1, D2.

Covers both contract shapes — OpenAPI ``x-traceability`` on an operation,
CLI contract ``traceability`` on a flag/command — parsing into one model, as
with ``x-gen-eval-surface``. Also covers task 2.0's schema promotion (a test
that loads each promoted copy, per the predecessor's own promotion guard)
and task 2.4/2.5's unresolved-citation failure, naming the id and its
nearest candidates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from gen_eval.descriptor import FlagSpec, PositionalSpec, ToolCommandSpec
from gen_eval.service_descriptor import ServiceDescriptor
from gen_eval.traceability import (
    RequirementResolver,
    TraceabilityBlock,
    UnresolvedRequirementError,
    resolve_citations,
)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
SCHEMAS_DIR = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "schemas"


# ---------------------------------------------------------------------------
# 2.0 — promoted schemas load, and their $id names the promoted location
# ---------------------------------------------------------------------------


class TestPromotedSchemasLoad:
    @pytest.mark.parametrize(
        "filename", ["traceability.schema.json", "traceability-exclusions.schema.json"]
    )
    def test_promoted_copy_loads(self, filename: str) -> None:
        path = SCHEMAS_DIR / filename
        if not path.is_file():
            pytest.fail(f"traceability schema not promoted to {path.relative_to(REPO_ROOT)}")
        schema = json.loads(path.read_text())
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)

    @pytest.mark.parametrize(
        "filename",
        [
            ("traceability.schema.json"),
            ("traceability-exclusions.schema.json"),
        ],
    )
    def test_id_matches_promoted_location(self, filename: str) -> None:
        schema = json.loads((SCHEMAS_DIR / filename).read_text())
        assert schema["$id"].endswith(
            f"/openspec/contracts/gen-eval-framework/schemas/{filename}"
        ), "$id must name the promoted path, or consumers resolving it will 404"


# ---------------------------------------------------------------------------
# 2.1/2.2 — parsing on the CLI (tool) archetype
# ---------------------------------------------------------------------------


class TestCliArchetypeParsing:
    def test_flag_carries_citations(self) -> None:
        flag = FlagSpec(
            name="--descriptor",
            type="path",
            traceability={"requirements": ["gen-eval-framework.descriptor-is-required"]},
        )
        assert flag.traceability is not None
        assert flag.traceability.requirements == [
            "gen-eval-framework.descriptor-is-required"
        ]
        assert flag.traceability.excluded is None

    def test_flag_carries_an_exclusion(self) -> None:
        flag = FlagSpec(
            name="--verbose",
            type="boolean",
            traceability={"excluded": {"reason": "output verbosity, no requirement governs it"}},
        )
        assert flag.traceability is not None
        assert flag.traceability.excluded.reason.startswith("output verbosity")
        assert flag.traceability.requirements is None

    def test_positional_carries_citations(self) -> None:
        positional = PositionalSpec(
            name="target",
            type="path",
            traceability={"requirements": ["gen-eval-framework.target-is-a-path"]},
        )
        assert positional.traceability.requirements == ["gen-eval-framework.target-is-a-path"]

    def test_named_command_carries_citations(self) -> None:
        command = ToolCommandSpec(
            name="lock acquire",
            traceability={"requirements": ["agent-coordinator.file-locking"]},
        )
        assert command.traceability.requirements == ["agent-coordinator.file-locking"]

    def test_absent_traceability_is_none_not_inferred(self) -> None:
        flag = FlagSpec(name="--output-dir", type="path")
        assert flag.traceability is None

    def test_traceability_survives_a_full_contract_parse(self) -> None:
        """The whole path a real contract takes: nested dicts through
        ``ToolCommandSpec(**c)``, exactly as ``ToolDescriptor.from_contract``
        constructs it — no bespoke parsing added for this field."""
        command_dict: dict[str, Any] = {
            "name": "",
            "flags": [
                {
                    "name": "--descriptor",
                    "type": "path",
                    "required": True,
                    "traceability": {"requirements": ["gen-eval-framework.x"]},
                }
            ],
        }
        command = ToolCommandSpec(**command_dict)
        assert command.flags[0].traceability.requirements == ["gen-eval-framework.x"]


# ---------------------------------------------------------------------------
# 2.1/2.2 — parsing on the service (OpenAPI) archetype
# ---------------------------------------------------------------------------


def _openapi_doc(operation_extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "widget", "version": "1"},
        "paths": {
            "/widgets": {
                "get": {
                    "operationId": "list_widgets",
                    **operation_extra,
                }
            }
        },
    }


class TestServiceArchetypeParsing:
    def test_operation_carries_citations_via_x_traceability(self, tmp_path: Path) -> None:
        import yaml

        doc = _openapi_doc(
            {"x-traceability": {"requirements": ["widget-capability.listing-is-supported"]}}
        )
        contract = tmp_path / "widget.yaml"
        contract.write_text(yaml.safe_dump(doc), encoding="utf-8")
        descriptor = ServiceDescriptor.from_contract(contract)
        op = descriptor.operation("list_widgets")
        assert op.traceability is not None
        assert op.traceability.requirements == ["widget-capability.listing-is-supported"]

    def test_operation_with_no_x_traceability_parses_none(self, tmp_path: Path) -> None:
        import yaml

        doc = _openapi_doc({})
        contract = tmp_path / "widget.yaml"
        contract.write_text(yaml.safe_dump(doc), encoding="utf-8")
        descriptor = ServiceDescriptor.from_contract(contract)
        assert descriptor.operation("list_widgets").traceability is None

    def test_operation_carries_an_exclusion(self, tmp_path: Path) -> None:
        import yaml

        doc = _openapi_doc(
            {"x-traceability": {"excluded": {"reason": "health probe, infra not product"}}}
        )
        contract = tmp_path / "widget.yaml"
        contract.write_text(yaml.safe_dump(doc), encoding="utf-8")
        descriptor = ServiceDescriptor.from_contract(contract)
        op = descriptor.operation("list_widgets")
        assert op.traceability.excluded.reason == "health probe, infra not product"


# ---------------------------------------------------------------------------
# The block itself rejects malformed shapes (mirrors the JSON schema oneOf)
# ---------------------------------------------------------------------------


class TestTraceabilityBlockValidation:
    def test_requirements_and_excluded_together_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceabilityBlock(requirements=["a.b"], excluded={"reason": "x"})

    def test_neither_requirements_nor_excluded_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceabilityBlock()

    def test_empty_requirements_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceabilityBlock(requirements=[])

    def test_blank_exclusion_reason_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceabilityBlock(excluded={"reason": ""})


# ---------------------------------------------------------------------------
# 2.4/2.5 — citation resolution, including the unresolved-citation failure
# ---------------------------------------------------------------------------


class TestResolveCitations:
    def test_resolves_a_real_citation(self) -> None:
        specs_root = REPO_ROOT / "openspec" / "specs"
        changes_root = REPO_ROOT / "openspec" / "changes"
        resolver = RequirementResolver(specs_root, changes_root)
        block = TraceabilityBlock(requirements=["agent-coordinator.file-locking"])
        assert resolve_citations(block, resolver) == ["File Locking"]

    def test_excluded_block_resolves_to_nothing(self) -> None:
        resolver = RequirementResolver(
            REPO_ROOT / "openspec" / "specs", REPO_ROOT / "openspec" / "changes"
        )
        block = TraceabilityBlock(excluded={"reason": "no interface"})
        assert resolve_citations(block, resolver) == []

    def test_unresolved_citation_names_the_id_and_candidates(self, tmp_path: Path) -> None:
        specs_root = tmp_path / "specs"
        (specs_root / "widget").mkdir(parents=True)
        (specs_root / "widget" / "spec.md").write_text(
            "## Requirements\n\n### Requirement: Alpha Feature\n\nThe system SHALL alpha.\n",
            encoding="utf-8",
        )
        resolver = RequirementResolver(specs_root, tmp_path / "changes")
        block = TraceabilityBlock(requirements=["widget.alpha-featur"])  # typo
        with pytest.raises(UnresolvedRequirementError) as excinfo:
            resolve_citations(block, resolver)
        message = str(excinfo.value)
        assert "widget.alpha-featur" in message
        assert "Alpha Feature" in message  # nearest candidate, display only

    def test_a_reworded_heading_breaks_its_citations(self, tmp_path: Path) -> None:
        """Requirement Identifiers Are Stable And Fail Closed: a reworded
        heading breaks its citations (task 2.4's spec scenario)."""
        specs_root = tmp_path / "specs"
        (specs_root / "widget").mkdir(parents=True)
        (specs_root / "widget" / "spec.md").write_text(
            "## Requirements\n\n### Requirement: Original Name\n\nThe system SHALL x.\n",
            encoding="utf-8",
        )
        resolver = RequirementResolver(specs_root, tmp_path / "changes")
        # A citation authored against the ORIGINAL heading, before a
        # (hypothetical) rewording that this fixture never applies — the
        # resolver must still fail closed on any id it cannot derive today.
        block = TraceabilityBlock(requirements=["widget.a-completely-different-heading"])
        with pytest.raises(UnresolvedRequirementError):
            resolve_citations(block, resolver)
