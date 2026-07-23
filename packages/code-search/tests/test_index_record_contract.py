from __future__ import annotations

import json
from pathlib import Path

import pytest


jsonschema = pytest.importorskip("jsonschema")

CONTRACT = (
    Path(__file__).parents[3]
    / "openspec/changes/add-revision-aware-semantic-index-registry/contracts"
    / "index-record.schema.json"
)
NOW = "2026-07-23T12:00:00+00:00"
LEASE_TOKEN = "11111111-1111-4111-8111-111111111111"


def record_for(status: str) -> dict[str, object]:
    leased = status in {"indexing", "deleting"}
    return {
        "index_id": "22222222-2222-4222-8222-222222222222",
        "storage_key": "i_22222222222242228222222222222222",
        "repo_slug": "repo",
        "namespace_kind": "feature",
        "namespace_key": "feature/review",
        "source_revision": "a" * 40,
        "embedder_model": "model",
        "embedding_dim": 768,
        "status": status,
        "attempt_count": 1,
        "chunk_count": 3 if status == "ready" else None,
        "last_error": None,
        "lease_token": LEASE_TOKEN if leased else None,
        "lease_owner": "worker" if leased else None,
        "lease_expires_at": NOW if leased else None,
        "retention_until": NOW,
        "started_at": NOW,
        "completed_at": NOW if status == "ready" else None,
        "deleted_at": NOW if status == "deleted" else None,
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "indexing",
        "ready",
        "failed",
        "not_configured",
        "deleting",
        "deleted",
    ],
)
def test_json_schema_accepts_every_valid_lifecycle_shape(status: str) -> None:
    schema = json.loads(CONTRACT.read_text())
    jsonschema.Draft202012Validator(schema).validate(record_for(status))


def test_json_schema_rejects_deleted_record_without_deleted_timestamp() -> None:
    schema = json.loads(CONTRACT.read_text())
    invalid = record_for("deleted")
    invalid["deleted_at"] = None

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(invalid)
