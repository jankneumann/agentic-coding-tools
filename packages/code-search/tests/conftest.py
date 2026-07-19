"""Skip-marker wiring: DB/embedder-dependent tests auto-skip when the resource is absent."""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    have_db = bool(os.environ.get("POSTGRES_DSN"))
    have_embedder = _cocoindex_importable()
    skip_db = pytest.mark.skip(reason="no POSTGRES_DSN — live ParadeDB required")
    skip_emb = pytest.mark.skip(reason="cocoindex/embedder not installed or unreachable")
    for item in items:
        if "requires_db" in item.keywords and not have_db:
            item.add_marker(skip_db)
        if "requires_embedder" in item.keywords and not have_embedder:
            item.add_marker(skip_emb)


def _cocoindex_importable() -> bool:
    import importlib.util

    return importlib.util.find_spec("cocoindex") is not None
