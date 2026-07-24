"""Repo-slug validation and per-repo table naming (design D2).

Zero heavy dependencies — importable and testable without cocoindex/torch/asyncpg, because
the slug rule is shared by the indexer, the query path, the coordinator service, and the
registry CHECK constraint. Keeping it here avoids drift between those call sites.
"""

from __future__ import annotations

import re
from uuid import UUID

# Mirrors the CHECK constraint on code_search_registry.repo_slug (contracts/db/schema.sql).
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,50}$")

CHUNK_TABLE_PREFIX = "code_chunks__"
STORAGE_KEY_RE = re.compile(r"^i_[0-9a-f]{32}$")


def validate_slug(repo_slug: str) -> str:
    """Return the slug unchanged if valid; raise ValueError otherwise.

    A valid slug is SQL-identifier-safe, so it can be interpolated into a table name without
    quoting or injection risk.
    """
    if not SLUG_RE.match(repo_slug):
        raise ValueError(
            f"invalid repo slug {repo_slug!r} (expected pattern {SLUG_RE.pattern})"
        )
    return repo_slug


def slugify(name: str) -> str:
    """Derive a candidate slug from an arbitrary repo name (design D2).

    Lowercase, non-alphanumerics collapsed to underscores, leading digits/underscores trimmed,
    truncated to the 51-char slug budget. The result is validated, so a name that cannot yield a
    legal slug raises rather than silently producing an unsafe identifier.
    """
    lowered = name.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    collapsed = re.sub(r"^[0-9_]+", "", collapsed)  # slug must start with a letter
    return validate_slug(collapsed[:51])


def chunk_table_name(repo_slug: str) -> str:
    """Per-repo chunk table name. Validates the slug first, so the returned name is SQL-safe."""
    return f"{CHUNK_TABLE_PREFIX}{validate_slug(repo_slug)}"


def storage_key_for_index(index_id: UUID | str) -> str:
    """Return the stable, SQL-safe storage key derived from an index UUID."""
    parsed = index_id if isinstance(index_id, UUID) else UUID(index_id)
    return f"i_{parsed.hex}"


def validate_storage_key(storage_key: str) -> str:
    """Return a valid isolated-storage key, or reject unsafe identifiers."""
    if not STORAGE_KEY_RE.fullmatch(storage_key):
        raise ValueError(
            f"invalid storage key {storage_key!r} "
            f"(expected pattern {STORAGE_KEY_RE.pattern})"
        )
    return storage_key


def index_chunk_table_name(index_id_or_storage_key: UUID | str) -> str:
    """Return the isolated chunk table name for an index UUID or storage key."""
    if isinstance(index_id_or_storage_key, UUID):
        storage_key = storage_key_for_index(index_id_or_storage_key)
    else:
        storage_key = (
            validate_storage_key(index_id_or_storage_key)
            if STORAGE_KEY_RE.fullmatch(index_id_or_storage_key)
            else storage_key_for_index(index_id_or_storage_key)
        )
    return f"{CHUNK_TABLE_PREFIX}{storage_key}"
