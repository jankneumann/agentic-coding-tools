from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


CONTRACT_DIR = (
    Path(__file__).parents[3]
    / "openspec"
    / "changes"
    / "complete-incremental-semantic-indexing"
    / "contracts"
)
INDEX_ID = "11111111-1111-4111-8111-111111111111"
STORAGE_KEY = "i_11111111111141118111111111111111"


def load_schema(name: str) -> dict[str, object]:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def request() -> dict[str, object]:
    return {
        "repo_root": "/repo",
        "repo_slug": "repo",
        "source_revision": "a" * 40,
        "namespace_kind": "main",
        "namespace_key": "main",
        "embedder": {
            "provider": "local",
            "model": "model",
            "dimension": 3,
            "base_url": None,
            "credential_ref": None,
            "indexing_params": {"normalize": True},
        },
        "policy": {
            "include": ["src/**"],
            "exclude": [],
            "read_allow": ["src/**"],
            "deny": ["**/*.pem"],
            "respect_gitignore": True,
            "secret_scan": "local_required",
        },
        "lease_owner": "worker",
        "lease_duration_seconds": 300,
        "full_rebuild": False,
    }


def result(status: str, *, durable: bool) -> dict[str, object]:
    ready = status == "ready"
    return {
        "status": status,
        "durable": durable,
        "reused": False,
        "repo_slug": "repo",
        "source_revision": "a" * 40,
        "namespace_kind": "main",
        "namespace_key": "main",
        "index_id": INDEX_ID if durable else None,
        "storage_key": STORAGE_KEY if durable else None,
        "parent_index_id": None,
        "parent_revision": None,
        "promoted": False,
        "counts": {
            "eligible_files": 1,
            "copied_files": 0,
            "changed_files": 1,
            "removed_files": 0,
            "skipped_files": 0,
            "embedded_chunks": 1,
            "chunks": 1 if ready else 0,
        },
        "error": None
        if ready
        else {"code": "safe_error", "message": "sanitized result"},
    }


def test_request_contract_accepts_local_and_explicit_remote_provider() -> None:
    validator = jsonschema.Draft202012Validator(
        load_schema("index-request.schema.json")
    )
    validator.validate(request())

    remote = request()
    remote["embedder"] = {
        "provider": "openai_compatible",
        "model": "gateway-model",
        "dimension": 768,
        "base_url": "https://gateway.example.test/v1",
        "credential_ref": "env:CODE_SEARCH_API_KEY",
        "indexing_params": {"input_type": "document"},
    }
    validator.validate(remote)


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ({"credential_ref": "raw-secret"}, "credential_ref"),
        ({"base_url": "https://user:secret@example.test"}, "base_url"),
        ({"arbitrary_provider_option": "value"}, "arbitrary_provider_option"),
    ],
)
def test_request_contract_rejects_secret_or_unbounded_provider_fields(
    mutation: dict[str, object],
    field: str,
) -> None:
    invalid = request()
    invalid["embedder"] = {**invalid["embedder"], **mutation}  # type: ignore[arg-type]

    with pytest.raises(jsonschema.ValidationError, match=field):
        jsonschema.Draft202012Validator(
            load_schema("index-request.schema.json")
        ).validate(invalid)


@pytest.mark.parametrize(
    ("status", "durable"),
    [
        ("ready", True),
        ("not_configured", False),
        ("not_configured", True),
        ("failed", False),
        ("failed", True),
        ("conflict", True),
    ],
)
def test_execution_result_contract_accepts_terminal_shapes(
    status: str,
    durable: bool,
) -> None:
    jsonschema.Draft202012Validator(
        load_schema("index-execution-result.schema.json")
    ).validate(result(status, durable=durable))


@pytest.mark.parametrize(
    "invalid",
    [
        {**result("ready", durable=True), "durable": False},
        {**result("failed", durable=True), "reused": True},
        {
            **result("failed", durable=True),
            "parent_index_id": INDEX_ID,
            "parent_revision": "b" * 40,
        },
        {
            **result("ready", durable=True),
            "promoted": True,
            "namespace_kind": "feature",
            "namespace_key": "feature/x",
        },
    ],
)
def test_execution_result_contract_rejects_impossible_combinations(
    invalid: dict[str, object],
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(
            load_schema("index-execution-result.schema.json")
        ).validate(invalid)
