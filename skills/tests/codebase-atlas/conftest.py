"""Path setup and fixtures for codebase-atlas tests.

Prepend the skill's ``scripts/`` directory so tests import bare module names
(``import atlas_model``), matching the repo's shared-runtime convention.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "codebase-atlas" / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


@pytest.fixture
def tiny_graph() -> dict:
    """A minimal graph exercising every shape the real artifact contains.

    Deliberately includes the awkward cases: a SQL table with columns (nesting),
    a node with no ``file`` (the unfiled group), a cross-file call, an intra-file
    call (must not become a module self-edge), and a dangling edge whose target
    is absent from the node list.
    """
    return {
        "snapshots": [
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "git_sha": "abc123def456",
                "tool_versions": {"graph_builder": "2.0.0"},
            }
        ],
        "entrypoints": ["py:api.handler"],
        "nodes": [
            {
                "id": "py:api.handler",
                "kind": "function",
                "language": "python",
                "name": "handler",
                "file": "api.py",
                "span": {"start": 10, "end": 20},
                "tags": ["entry_point", "async"],
                "signatures": {},
            },
            {
                "id": "py:api._helper",
                "kind": "function",
                "language": "python",
                "name": "_helper",
                "file": "api.py",
                "span": {"start": 30, "end": 34},
                "tags": ["private"],
                "signatures": {},
            },
            {
                "id": "py:store.save",
                "kind": "function",
                "language": "python",
                "name": "save",
                "file": "store.py",
                "span": {"start": 5, "end": 9},
                "tags": [],
                "signatures": {},
            },
            {
                "id": "pg:public.public.things",
                "kind": "table",
                "language": "sql",
                "name": "public.things",
                "file": "001_init.sql",
                "span": {"start": 1, "end": 1},
                "tags": [],
                "signatures": {},
            },
            {
                "id": "pg:public.public.things.id",
                "kind": "column",
                "language": "sql",
                "name": "id",
                "file": "001_init.sql",
                "span": {"start": 2, "end": 2},
                "tags": [],
                "signatures": {"type": "UUID"},
            },
            {
                "id": "pg:idx_things",
                "kind": "index",
                "language": "sql",
                "name": "idx_things",
                "file": "",
                "span": {"start": 1, "end": 1},
                "tags": [],
                "signatures": {},
            },
        ],
        "edges": [
            # cross-file: becomes a module-level edge
            {"from": "py:api.handler", "to": "py:store.save", "type": "call",
             "confidence": "high", "evidence": "ast:call:save"},
            # second cross-file edge, same pair: must aggregate to weight 2
            {"from": "py:api._helper", "to": "py:store.save", "type": "call",
             "confidence": "high", "evidence": "ast:call:save"},
            # intra-file: must NOT create a module self-edge
            {"from": "py:api.handler", "to": "py:api._helper", "type": "call",
             "confidence": "high", "evidence": "ast:call:_helper"},
            # dangling: target not in nodes, must be dropped and counted
            {"from": "py:api.handler", "to": "py:ghost.missing", "type": "call",
             "confidence": "low", "evidence": "ast:call:missing"},
        ],
    }
