"""Installed schema-asset tests: offline presence and reference resolution.

Spec scenarios: project-context-refresh-records.16, .18
Design decisions: D1, D5
"""

from __future__ import annotations

import json
from pathlib import Path

import models as m
import pytest

_ASSET_DIR = (
    Path(m.__file__).resolve().parent.parent
    / "install_assets"
    / "openspec"
    / "schemas"
)
_FILES = (
    "context-refresh-types.schema.json",
    "context-refresh-operation.schema.json",
    "context-refresh-manifest.schema.json",
)


def test_all_three_schemas_are_installed() -> None:
    for name in _FILES:
        assert (_ASSET_DIR / name).is_file(), name


def test_schemas_are_draft_2020_12_with_absolute_ids() -> None:
    for name in _FILES:
        data = json.loads((_ASSET_DIR / name).read_text(encoding="utf-8"))
        assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert data["$id"].startswith("https://")


def test_top_level_schemas_pin_version_one_and_close_objects() -> None:
    for name in ("context-refresh-operation.schema.json", "context-refresh-manifest.schema.json"):
        data = json.loads((_ASSET_DIR / name).read_text(encoding="utf-8"))
        assert data["additionalProperties"] is False
        assert data["properties"]["schema_version"]["const"] == 1


def test_relative_refs_resolve_offline() -> None:
    # The operation schema references ./context-refresh-types via $ref; if the
    # local registry did not resolve it, validation would raise a resolution
    # error instead of a clean pass/fail.
    valid_producer_ref_doc = {
        "schema_version": 1,
        "operation_id": m.derive_operation_id("r", "e" * 40),
        "repository_id": "r",
        "source_revision": "e" * 40,
        "state": "pending",
        "record_revision": 1,
        "attempt": 0,
        "created_at": "2026-07-24T00:00:00+00:00",
        "updated_at": "2026-07-24T00:00:00+00:00",
        "producer_results": [],
        "semantic_index": {
            "status": "pending",
            "requested_revision": "e" * 40,
            "operation_id": None,
            "registry_record_id": None,
            "indexed_revision": None,
            "fallback": {"kind": "exact-search", "reason": "not complete"},
        },
        "manifest": {"status": "absent", "path": None, "sha256": None},
    }
    # Passes cleanly using only local assets — no network fetch.
    m.validate_document(valid_producer_ref_doc, "operation")

    # A cross-referenced type violation (bad fallback kind in shared types) is
    # caught, proving the $ref actually resolved to the types schema.
    valid_producer_ref_doc["semantic_index"]["fallback"]["kind"] = "not-a-kind"
    with pytest.raises(m.RecordValidationError):
        m.validate_document(valid_producer_ref_doc, "operation")
