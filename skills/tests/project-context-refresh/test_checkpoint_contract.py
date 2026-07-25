"""Contract tests for the branch-local context checkpoint report schema (ri-09 tasks 1.1-1.2).

Spec scenarios: pcro "Report validates against the checkpoint schema",
pcro "Checkpoint indexing uses a work-package namespace".
Design decisions: D4 (a checkpoint is structurally barred from the canonical
namespace), D7 (published location and byte-stable report), D8 (no ``failed``
checkpoint state — drift is data, not failure).

The canonical source of the schema is the install asset under
``skills/project-context-refresh/install_assets/openspec/schemas/``; the copy at
``openspec/schemas/`` is its generated mirror and must be byte-identical.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_NAME = "context-checkpoint.schema.json"
_CANONICAL_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "project-context-refresh"
    / "install_assets"
    / "openspec"
    / "schemas"
    / _SCHEMA_NAME
)
_MIRRORED_SCHEMA = _REPO_ROOT / "openspec" / "schemas" / _SCHEMA_NAME
_RUNTIME_ASSET_DIR = (
    _REPO_ROOT
    / "skills"
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
)
_TYPES_SCHEMA = _RUNTIME_ASSET_DIR / "context-refresh-types.schema.json"
_SIBLING_SCHEMAS = (
    "context-refresh-types.schema.json",
    "context-refresh-operation.schema.json",
    "context-refresh-manifest.schema.json",
)

REV = "a" * 40
MERGE_BASE = "b" * 40


# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #
def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return _load(_CANONICAL_SCHEMA)


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    """Validator wired to a local registry so the sibling ``$ref``s resolve offline."""
    Draft202012Validator.check_schema(schema)
    types_schema = _load(_TYPES_SCHEMA)
    registry = Registry().with_resources(
        [
            (
                doc["$id"],
                Resource.from_contents(doc, default_specification=DRAFT202012),
            )
            for doc in (schema, types_schema)
        ]
    )
    return Draft202012Validator(schema, registry=registry)


def _valid_checkpoint() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "change_id": "add-branch-local-context-checkpoints",
        "package_id": "wp-contracts",
        "source_revision": REV,
        "merge_base_revision": MERGE_BASE,
        "namespace": {
            "kind": "work_package",
            "key": "add-branch-local-context-checkpoints--wp-contracts",
        },
        "scope": {
            "read_allow": ["skills/project-context-refresh/**", "openspec/schemas/**"],
            "deny": ["**/.venv/**"],
        },
        "context_impact": {
            "status": "declared",
            "surfaces": ["documentation", "apis"],
        },
        "producer_results": [
            {
                "producer_id": "documentation",
                "producer_version": "2.0.0",
                "status": "fresh",
                "artifacts": [
                    {"path": "docs/index.md", "change": "modified", "sha256": "c" * 64}
                ],
                "validations": [
                    {"validation_id": "docs.lint", "status": "passed", "summary": "ok"}
                ],
                "remediation": [],
            }
        ],
        "architecture": {
            "freshness": "fresh",
            "delta_authoritative": True,
            "changed_nodes": ["skills/project-context-refresh/scripts/checkpoint.py"],
        },
        "semantic_index": {
            "status": "succeeded",
            "requested_revision": REV,
            "operation_id": "op-1",
            "registry_record_id": "rec-1",
            "indexed_revision": REV,
        },
        "checkpoint_status": "succeeded",
    }


def _errors(validator: Draft202012Validator, doc: dict[str, Any]) -> list[Any]:
    return sorted(validator.iter_errors(doc), key=lambda err: list(err.absolute_path))


def _paths(errors: list[Any]) -> set[str]:
    return {"/".join(str(part) for part in err.absolute_path) for err in errors}


# --------------------------------------------------------------------------- #
# Publication (task 1.3)
# --------------------------------------------------------------------------- #
class TestPublishedSchema:
    def test_schema_is_published_as_an_install_asset(self) -> None:
        assert _CANONICAL_SCHEMA.is_file(), (
            f"missing canonical install asset: {_CANONICAL_SCHEMA}"
        )

    def test_openspec_mirror_is_byte_identical_to_the_install_asset(self) -> None:
        assert _MIRRORED_SCHEMA.is_file(), f"missing mirror: {_MIRRORED_SCHEMA}"
        assert (
            _MIRRORED_SCHEMA.read_bytes() == _CANONICAL_SCHEMA.read_bytes()
        ), "openspec/schemas mirror has drifted from the install asset"

    def test_schema_is_draft_2020_12_with_an_absolute_id(
        self, schema: dict[str, Any]
    ) -> None:
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].startswith("https://")
        assert schema["$id"].endswith(f"/{_SCHEMA_NAME}")

    def test_schema_pins_version_one_and_closes_the_top_level_object(
        self, schema: dict[str, Any]
    ) -> None:
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schema_version"]["const"] == 1

    def test_name_does_not_collide_with_the_roadmap_resume_contract(self) -> None:
        # D7: checkpoint.schema.json is already the autopilot-roadmap resume state.
        roadmap_schema = _REPO_ROOT / "openspec" / "schemas" / "checkpoint.schema.json"
        assert roadmap_schema.is_file()
        assert roadmap_schema != _MIRRORED_SCHEMA


# --------------------------------------------------------------------------- #
# Document validation (task 1.1)
# --------------------------------------------------------------------------- #
class TestValidDocument:
    def test_a_complete_checkpoint_is_accepted(
        self, validator: Draft202012Validator
    ) -> None:
        assert _errors(validator, _valid_checkpoint()) == []

    def test_merge_base_revision_is_optional(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        del doc["merge_base_revision"]
        assert _errors(validator, doc) == []

    @pytest.mark.parametrize(
        "field",
        [
            "schema_version",
            "change_id",
            "package_id",
            "source_revision",
            "namespace",
            "scope",
            "context_impact",
            "producer_results",
            "architecture",
            "semantic_index",
            "checkpoint_status",
        ],
    )
    def test_every_required_field_is_actually_required(
        self, validator: Draft202012Validator, field: str
    ) -> None:
        doc = _valid_checkpoint()
        del doc[field]
        assert _errors(validator, doc), f"{field} was removed but the document validated"


class TestNamespaceIsNonCanonical:
    """D4 — a checkpoint is structurally barred from the canonical namespace."""

    def test_main_namespace_kind_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["namespace"]["kind"] = "main"
        errors = _errors(validator, doc)
        assert errors, "namespace.kind 'main' must be rejected"
        assert "namespace/kind" in _paths(errors)

    def test_enum_is_exactly_work_package_and_feature(
        self, schema: dict[str, Any]
    ) -> None:
        enum = schema["properties"]["namespace"]["properties"]["kind"]["enum"]
        assert sorted(enum) == ["feature", "work_package"]

    @pytest.mark.parametrize("kind", ["work_package", "feature"])
    def test_non_canonical_kinds_are_accepted(
        self, validator: Draft202012Validator, kind: str
    ) -> None:
        doc = _valid_checkpoint()
        doc["namespace"]["kind"] = kind
        assert _errors(validator, doc) == []


class TestCheckpointStatusHasNoFailedState:
    """D8 — drift is data; a checkpoint that cannot report writes no report."""

    def test_failed_status_is_rejected(self, validator: Draft202012Validator) -> None:
        doc = _valid_checkpoint()
        doc["checkpoint_status"] = "failed"
        errors = _errors(validator, doc)
        assert errors, "checkpoint_status 'failed' must be rejected"
        assert "checkpoint_status" in _paths(errors)

    @pytest.mark.parametrize("status", ["succeeded", "degraded"])
    def test_terminal_states_are_accepted(
        self, validator: Draft202012Validator, status: str
    ) -> None:
        doc = _valid_checkpoint()
        doc["checkpoint_status"] = status
        assert _errors(validator, doc) == []

    def test_a_degraded_checkpoint_still_carries_deterministic_findings(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["checkpoint_status"] = "degraded"
        doc["semantic_index"] = {
            "status": "not-configured",
            "requested_revision": REV,
            "operation_id": None,
            "registry_record_id": None,
            "indexed_revision": None,
            "fallback": {"kind": "exact-search", "reason": "POSTGRES_DSN unset"},
        }
        assert _errors(validator, doc) == []
        assert doc["producer_results"], "deterministic findings must survive degradation"


class TestContextImpactStatus:
    """D2 — an unmigrated package is reported explicitly, never as impact-free."""

    def test_unmigrated_is_accepted_alongside_a_non_empty_surface_list(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["context_impact"] = {
            "status": "unmigrated",
            "surfaces": ["architecture", "semantic_code"],
        }
        assert _errors(validator, doc) == []

    def test_unmigrated_is_representable_with_no_surfaces(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["context_impact"] = {"status": "unmigrated", "surfaces": []}
        assert _errors(validator, doc) == []

    @pytest.mark.parametrize("status", ["declared", "rationalized", "unmigrated"])
    def test_reportable_statuses_are_accepted(
        self, validator: Draft202012Validator, status: str
    ) -> None:
        doc = _valid_checkpoint()
        doc["context_impact"]["status"] = status
        assert _errors(validator, doc) == []

    @pytest.mark.parametrize("status", ["undeclared", "spurious_rationale"])
    def test_blocking_statuses_cannot_appear_in_a_report(
        self, validator: Draft202012Validator, status: str
    ) -> None:
        # These block before a checkpoint ever runs, so a report carrying one
        # would be self-contradictory.
        doc = _valid_checkpoint()
        doc["context_impact"]["status"] = status
        assert "context_impact/status" in _paths(_errors(validator, doc))

    def test_unknown_surface_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["context_impact"]["surfaces"] = ["not-a-surface"]
        assert _errors(validator, doc)


class TestClosedObjects:
    """``additionalProperties: false`` must actually bite."""

    def test_unknown_top_level_key_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["generated_at"] = "2026-07-25T00:00:00+00:00"
        errors = _errors(validator, doc)
        assert errors, "an unknown top-level key must be rejected"
        assert any("generated_at" in err.message for err in errors)

    @pytest.mark.parametrize(
        "container", ["namespace", "scope", "context_impact", "architecture"]
    )
    def test_nested_objects_are_closed_too(
        self, validator: Draft202012Validator, container: str
    ) -> None:
        doc = _valid_checkpoint()
        doc[container]["unexpected_key"] = "x"
        assert _errors(validator, doc), f"{container} accepted an unknown key"


class TestArchitectureFindings:
    def test_freshness_enum_and_delta_flag_are_present(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["architecture"] = {
            "freshness": "stale",
            "delta_authoritative": False,
            "changed_nodes": [],
        }
        assert _errors(validator, doc) == []

    def test_unknown_freshness_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_checkpoint()
        doc["architecture"]["freshness"] = "probably-fine"
        assert "architecture/freshness" in _paths(_errors(validator, doc))


# --------------------------------------------------------------------------- #
# Reference resolution (task 1.2)
# --------------------------------------------------------------------------- #
def _install_layout(target: Path, *, include_types: bool = True) -> Path:
    """Reproduce what ``install.sh`` writes into ``<target>/openspec/schemas/``."""
    schemas = target / "openspec" / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_CANONICAL_SCHEMA, schemas / _SCHEMA_NAME)
    for name in _SIBLING_SCHEMAS:
        if name == "context-refresh-types.schema.json" and not include_types:
            continue
        shutil.copyfile(_RUNTIME_ASSET_DIR / name, schemas / name)
    return schemas


def _directory_registry(schema_dir: Path) -> Registry:
    """A registry that can only resolve URIs backed by a file in *schema_dir*.

    Nothing is pre-registered, so a ``$ref`` resolves only if the referenced
    document is genuinely sitting beside the checkpoint schema on disk.
    """

    def retrieve(uri: str) -> Resource[dict[str, Any]]:
        candidate = schema_dir / uri.rsplit("/", 1)[-1]
        if not candidate.is_file():
            raise NoSuchResource(ref=uri)
        return Resource.from_contents(
            json.loads(candidate.read_text(encoding="utf-8")),
            default_specification=DRAFT202012,
        )

    return Registry(retrieve=retrieve)


def _installed_validator(schema_dir: Path) -> Draft202012Validator:
    root = json.loads((schema_dir / _SCHEMA_NAME).read_text(encoding="utf-8"))
    return Draft202012Validator(root, registry=_directory_registry(schema_dir))


class TestSiblingRefsResolveWhenInstalled:
    """The three ``$ref``s must resolve from disk, not merely be present as strings."""

    def test_refs_use_the_sibling_relative_convention(
        self, schema: dict[str, Any]
    ) -> None:
        props = schema["properties"]
        assert (
            props["source_revision"]["$ref"]
            == "./context-refresh-types.schema.json#/$defs/GitRevision"
        )
        assert (
            props["merge_base_revision"]["$ref"]
            == "./context-refresh-types.schema.json#/$defs/GitRevision"
        )
        assert (
            props["producer_results"]["items"]["$ref"]
            == "./context-refresh-types.schema.json#/$defs/ProducerResult"
        )
        assert (
            props["semantic_index"]["$ref"]
            == "./context-refresh-types.schema.json#/$defs/SemanticIndexReference"
        )

    def test_valid_document_validates_against_the_installed_layout(
        self, tmp_path: Path
    ) -> None:
        installed = _installed_validator(_install_layout(tmp_path))
        assert _errors(installed, _valid_checkpoint()) == []

    def test_git_revision_ref_resolves_to_the_shared_definition(
        self, tmp_path: Path
    ) -> None:
        installed = _installed_validator(_install_layout(tmp_path))
        doc = _valid_checkpoint()
        doc["source_revision"] = "not-a-sha"
        doc["merge_base_revision"] = "nope"
        paths = _paths(_errors(installed, doc))
        assert "source_revision" in paths
        assert "merge_base_revision" in paths

    def test_producer_result_ref_resolves_to_the_shared_definition(
        self, tmp_path: Path
    ) -> None:
        installed = _installed_validator(_install_layout(tmp_path))
        doc = _valid_checkpoint()
        doc["producer_results"][0]["status"] = "not-a-status"
        assert "producer_results/0/status" in _paths(_errors(installed, doc))

    def test_producer_result_conditional_rules_are_inherited(
        self, tmp_path: Path
    ) -> None:
        # A degraded ProducerResult requires a fallback and remediation; that
        # rule lives only in the shared types schema.
        installed = _installed_validator(_install_layout(tmp_path))
        doc = _valid_checkpoint()
        doc["producer_results"][0]["status"] = "degraded"
        assert _errors(installed, doc), "degraded result without fallback must fail"

        doc["producer_results"][0]["remediation"] = [{"summary": "re-run the producer"}]
        doc["producer_results"][0]["fallback"] = {
            "kind": "direct-source",
            "reason": "embedder offline",
        }
        assert _errors(installed, doc) == []

    def test_semantic_index_ref_resolves_to_the_shared_definition(
        self, tmp_path: Path
    ) -> None:
        installed = _installed_validator(_install_layout(tmp_path))
        doc = _valid_checkpoint()
        doc["semantic_index"]["status"] = "not-a-status"
        assert "semantic_index/status" in _paths(_errors(installed, doc))

    def test_resolution_fails_when_the_types_schema_is_not_installed_beside_it(
        self, tmp_path: Path
    ) -> None:
        # Negative control: proves the passing cases above are real resolutions
        # against the sibling file rather than an ambient pre-registered schema.
        schema_dir = _install_layout(tmp_path, include_types=False)
        installed = _installed_validator(schema_dir)
        with pytest.raises(Unresolvable):
            list(installed.iter_errors(_valid_checkpoint()))
