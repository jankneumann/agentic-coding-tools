from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from code_search_pkg import chunk_table_name
from code_search_pkg.identifiers import (
    index_chunk_table_name,
    storage_key_for_index,
    validate_storage_key,
)
from code_search_pkg.registry import (
    IndexIdentity,
    IndexStatus,
    NamespaceKind,
    SemanticIndexRecord,
)


SHA1 = "a" * 40
SHA256 = "b" * 64


def test_exact_identity_accepts_full_object_ids_and_explicit_namespaces() -> None:
    main = IndexIdentity("repo", NamespaceKind.MAIN, "main", SHA1, "model", 768)
    feature = IndexIdentity(
        "repo", NamespaceKind.FEATURE, "feature/refactor", SHA256, "model", 768
    )

    assert main.source_revision == SHA1
    assert feature.namespace_kind is NamespaceKind.FEATURE
    assert main.natural_key == ("repo", "main", "main", SHA1, "model", 768)


@pytest.mark.parametrize(
    ("kind", "key", "revision"),
    [
        (NamespaceKind.MAIN, "trunk", SHA1),
        (NamespaceKind.FEATURE, "", SHA1),
        (NamespaceKind.WORK_PACKAGE, "x" * 256, SHA1),
        (NamespaceKind.FEATURE, "feature", "main"),
        (NamespaceKind.FEATURE, "feature", "A" * 40),
        (NamespaceKind.FEATURE, "feature", "a" * 39),
    ],
)
def test_exact_identity_rejects_refs_and_invalid_namespace_shapes(
    kind: NamespaceKind, key: str, revision: str
) -> None:
    with pytest.raises(ValueError):
        IndexIdentity("repo", kind, key, revision, "model", 768)


def test_storage_identifiers_are_uuid_derived_safe_and_isolated() -> None:
    first = UUID("11111111-1111-4111-8111-111111111111")
    second = UUID("22222222-2222-4222-8222-222222222222")

    assert storage_key_for_index(first) == "i_11111111111141118111111111111111"
    assert validate_storage_key(storage_key_for_index(first)) == storage_key_for_index(
        first
    )
    assert index_chunk_table_name(first) == (
        "code_chunks__i_11111111111141118111111111111111"
    )
    assert index_chunk_table_name(first) != index_chunk_table_name(second)
    with pytest.raises(ValueError):
        validate_storage_key("i_bad;drop_table")


def test_record_serializes_to_the_frozen_json_shape() -> None:
    now = datetime(2026, 7, 23, 12, tzinfo=UTC)
    record = SemanticIndexRecord(
        index_id=UUID("11111111-1111-4111-8111-111111111111"),
        storage_key="i_11111111111141118111111111111111",
        repo_slug="repo",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision=SHA1,
        embedder_model="model",
        embedding_dim=768,
        status=IndexStatus.READY,
        attempt_count=1,
        chunk_count=9,
        last_error=None,
        lease_token=None,
        lease_owner=None,
        lease_expires_at=None,
        retention_until=None,
        started_at=now,
        completed_at=now,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )

    payload = record.to_dict()

    assert set(payload) == {
        "index_id",
        "storage_key",
        "repo_slug",
        "namespace_kind",
        "namespace_key",
        "source_revision",
        "embedder_model",
        "embedding_dim",
        "status",
        "attempt_count",
        "chunk_count",
        "last_error",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "retention_until",
        "started_at",
        "completed_at",
        "deleted_at",
        "created_at",
        "updated_at",
    }
    assert payload["index_id"] == str(record.index_id)
    assert payload["namespace_kind"] == "main"
    assert payload["status"] == "ready"
    assert payload["completed_at"] == now.isoformat()

    decoded = SemanticIndexRecord.from_row(
        {
            **payload,
            "index_id": payload["index_id"],
            "lease_token": None,
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "completed_at": now,
        }
    )
    assert decoded == record


def test_legacy_repo_slug_table_naming_remains_available() -> None:
    assert chunk_table_name("my_repo") == "code_chunks__my_repo"
