"""Contract tests for the architecture provenance schema (ri-04 tasks 1.1-1.2).

Covers spec scenarios architecture-refresh.1 (complete provenance shape),
architecture-refresh.6 (invalid provenance is rejected), and
architecture-refresh.10 (canonical ri-06 ProducerResult integration).

The published schema lives at ``openspec/schemas/architecture-provenance.schema.json``
and MUST NOT duplicate the shared ri-06 operation/result contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_PATH = _REPO_ROOT / "openspec" / "schemas" / "architecture-provenance.schema.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_provenance() -> dict:
    return {
        "schema_version": 2,
        "producer": {"producer_id": "architecture", "producer_version": "1.0.0"},
        "repository_id": "agentic-coding-tools",
        "source_revision": "0" * 40,
        "worktree_dirty": False,
        "mode": "full",
        "input_roots": ["src", "database/migrations"],
        "input_fingerprint": "a" * 64,
        "generated_at": "2023-11-14T22:13:20+00:00",
        "optional_tools": [{"name": "tree-sitter", "available": True, "version": "0.21.0"}],
        "validation": {"status": "passed", "error_count": 0, "warning_count": 0},
        "artifacts": [
            {
                "path": "docs/architecture-analysis/architecture.graph.json",
                "sha256": "b" * 64,
                "size_bytes": 2048,
                "required": True,
                "tier": "committed",
            }
        ],
    }


class TestPublishedSchema:
    def test_schema_is_published_at_canonical_location(self) -> None:
        assert _SCHEMA_PATH.is_file(), (
            "architecture-provenance.schema.json must be published under openspec/schemas/"
        )

    def test_complete_provenance_validates(self, validator: Draft202012Validator) -> None:
        # Scenario architecture-refresh.1
        errors = sorted(validator.iter_errors(_valid_provenance()), key=str)
        assert errors == [], f"expected valid, got: {[e.message for e in errors]}"

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda d: d.pop("input_fingerprint"), id="missing-fingerprint"),
            pytest.param(lambda d: d.pop("source_revision"), id="missing-source-revision"),
            pytest.param(lambda d: d.pop("producer"), id="missing-producer"),
            pytest.param(
                lambda d: d.update(source_revision="not-a-sha"), id="malformed-sha"
            ),
            pytest.param(
                lambda d: d.update(input_fingerprint="short"), id="malformed-fingerprint"
            ),
            pytest.param(lambda d: d.update(mode="sideways"), id="bad-mode-enum"),
            pytest.param(
                lambda d: d["producer"].update(producer_id="documentation"),
                id="wrong-producer-id",
            ),
            pytest.param(lambda d: d.update(artifacts=[]), id="empty-artifacts"),
            pytest.param(
                lambda d: d["validation"].update(error_count=3), id="nonzero-errors"
            ),
            pytest.param(
                lambda d: d["artifacts"][0].update(
                    path="/etc/passwd", sha256="c" * 64
                ),
                id="artifact-path-escape",
            ),
            pytest.param(lambda d: d.update(unexpected="x"), id="additional-property"),
            pytest.param(
                lambda d: d["artifacts"][0].pop("tier"), id="missing-artifact-tier"
            ),
            pytest.param(
                lambda d: d["artifacts"][0].update(tier="committed-ish"),
                id="unrecognized-artifact-tier",
            ),
            pytest.param(
                lambda d: d["artifacts"][0].update(tier=None), id="null-artifact-tier"
            ),
            pytest.param(lambda d: d.update(schema_version=1), id="stale-schema-version"),
        ],
    )
    def test_invalid_provenance_is_rejected(
        self, validator: Draft202012Validator, mutate
    ) -> None:
        # Scenario architecture-refresh.6 — fail closed on malformed provenance.
        doc = _valid_provenance()
        mutate(doc)
        errors = list(validator.iter_errors(doc))
        assert errors, "schema must reject malformed provenance"

    def test_artifact_paths_are_confined_to_arch_dir(
        self, validator: Draft202012Validator
    ) -> None:
        doc = _valid_provenance()
        doc["artifacts"][0]["path"] = "docs/architecture-analysis/../../secrets.json"
        assert list(validator.iter_errors(doc)), "traversal paths must be rejected"


    def test_schema_version_is_pinned_to_two(self, schema: dict) -> None:
        # Task 1.5 / D2 — const, not an enum of accepted versions.
        assert schema["properties"]["schema_version"] == {"type": "integer", "const": 2}

    def test_artifact_tier_is_required_and_enumerated(self, schema: dict) -> None:
        # Scenario architecture-refresh.16 / D1 — required, never optional-with-default.
        items = schema["properties"]["artifacts"]["items"]
        assert "tier" in items["required"]
        assert items["properties"]["tier"]["enum"] == ["committed", "local-cache"]
        assert items["additionalProperties"] is False

    def test_artifact_without_tier_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        # Scenario architecture-refresh.16 — a pre-tier record must fail closed rather
        # than being silently reinterpreted as "committed".
        doc = _valid_provenance()
        doc["artifacts"][0].pop("tier")
        assert list(validator.iter_errors(doc)), "artifact entries must declare a tier"

    def test_artifact_with_unrecognized_tier_is_rejected(
        self, validator: Draft202012Validator
    ) -> None:
        # Scenario architecture-refresh.16
        doc = _valid_provenance()
        doc["artifacts"][0]["tier"] = "generated"
        assert list(validator.iter_errors(doc)), "tier must be one of the two known tiers"

    @pytest.mark.parametrize("tier", ["committed", "local-cache"])
    def test_artifact_with_valid_tier_is_accepted(
        self, validator: Draft202012Validator, tier: str
    ) -> None:
        # Scenario architecture-refresh.16
        doc = _valid_provenance()
        doc["artifacts"][0]["tier"] = tier
        errors = sorted(validator.iter_errors(doc), key=str)
        assert errors == [], f"expected valid, got: {[e.message for e in errors]}"


class TestCanonicalRi06Integration:
    """The architecture producer records a ri-06 ProducerResult — proving the two
    schemas coexist without ri-04 copying shared contracts (scenario .10)."""

    def test_producer_result_accepts_architecture_producer(self) -> None:
        from models import (  # ri-06 canonical types, imported, not copied
            ChangeKind,
            ProducerResult,
            ProducerStatus,
            RepositoryArtifact,
            ValidationResult,
            ValidationStatus,
        )

        result = ProducerResult(
            producer_id="architecture",
            producer_version="1.0.0",
            status=ProducerStatus.FRESH,
            artifacts=(
                RepositoryArtifact(
                    path="docs/architecture-analysis/architecture.graph.json",
                    change=ChangeKind.MODIFIED,
                    sha256="b" * 64,
                ),
            ),
            validations=(
                ValidationResult(
                    validation_id="architecture-schema",
                    status=ValidationStatus.PASSED,
                    summary="graph schema valid",
                ),
            ),
        )
        assert result.producer_id == "architecture"
        assert result.status is ProducerStatus.FRESH
        # Round-trips through the canonical serializer without ri-04-specific keys.
        payload = result.to_dict()
        assert payload["producer_id"] == "architecture"
        assert "input_fingerprint" not in payload

    def test_published_schema_does_not_shadow_shared_types(self, schema: dict) -> None:
        # The architecture provenance doc must not redeclare canonical operation
        # fields — it is producer-specific evidence, not a second result schema.
        forbidden = {"producer_results", "semantic_index", "operation_id", "state"}
        assert forbidden.isdisjoint(schema["properties"].keys())
