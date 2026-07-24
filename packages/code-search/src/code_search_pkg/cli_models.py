"""Pure structured-result helpers for the code-search CLI."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_PIPELINE_PAYLOAD = {
    "schema": "code-search-pipeline-v2",
    "cocoindex": ">=1.0.13,<1.1.0",
    "cocoindex_code": "0.2.37",
    "chunking": {"size": 1000, "minimum": 250, "overlap": 150},
    "chunk_identity": "path-aware-v2-with-ordinal",
    "chunk_set_digest": "v1",
    "storage_adapter": "isolated-attempt-fenced-publication-v1",
    "policy": {"version": 1, "hard_security_version": 1},
    "secret_scanner": "local-built-in-v1",
}
PIPELINE_FINGERPRINT = hashlib.sha256(
    json.dumps(
        _PIPELINE_PAYLOAD,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def ephemeral_result(
    *,
    repo_slug: str,
    source_revision: str,
    namespace_kind: str,
    namespace_key: str,
    status: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "durable": False,
        "reused": False,
        "repo_slug": repo_slug,
        "source_revision": source_revision,
        "namespace_kind": namespace_kind,
        "namespace_key": namespace_key,
        "index_id": None,
        "storage_key": None,
        "parent_index_id": None,
        "parent_revision": None,
        "promoted": False,
        "counts": {
            "eligible_files": 0,
            "copied_files": 0,
            "changed_files": 0,
            "removed_files": 0,
            "skipped_files": 0,
            "embedded_chunks": 0,
            "chunks": 0,
        },
        "error": {"code": code, "message": message},
    }
