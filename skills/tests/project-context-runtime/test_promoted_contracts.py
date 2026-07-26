"""Guard the promoted context-refresh contracts against archive-drift.

The three context-refresh JSON Schemas exist in two live locations by design:

* ``skills/project-context-runtime/install_assets/openspec/schemas/`` — what the
  runtime loads at import time (``models.py``) and what ``install.sh`` ships into
  consumer repositories, which have no ``openspec/contracts/`` of their own.
* ``openspec/contracts/project-context-refresh/schemas/`` — the stable,
  capability-scoped home described in ``openspec/contracts/README.md``, so the
  contract keeps a path that does not move when its originating change is
  archived.

Two copies can silently diverge, which is precisely the failure the promoted
location exists to prevent. These tests pin them together: change the runtime's
schema and the promoted copy must be updated in the same commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALL_ASSETS = (
    REPO_ROOT / "skills/project-context-runtime/install_assets/openspec/schemas"
)
PROMOTED = REPO_ROOT / "openspec/contracts/project-context-refresh/schemas"

SCHEMA_NAMES = (
    "context-refresh-manifest.schema.json",
    "context-refresh-operation.schema.json",
    "context-refresh-types.schema.json",
)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_contract_exists(name: str) -> None:
    """Every runtime schema has a promoted counterpart."""
    assert (PROMOTED / name).is_file(), (
        f"{name} is missing from {PROMOTED.relative_to(REPO_ROOT)}. "
        "Promote it (see openspec/contracts/README.md) so the contract survives "
        "archival of its originating change."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_contract_matches_runtime(name: str) -> None:
    """The promoted copy is byte-identical to the one the runtime loads."""
    runtime = (INSTALL_ASSETS / name).read_bytes()
    promoted = (PROMOTED / name).read_bytes()
    assert runtime == promoted, (
        f"{name} has drifted between install_assets/ and openspec/contracts/. "
        "Update both in the same commit — the runtime loads the install_assets "
        "copy, while tools and downstream repos reference the promoted one."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_contract_is_valid_json_schema(name: str) -> None:
    """The promoted copy is well-formed and declares a schema version."""
    doc = json.loads((PROMOTED / name).read_text(encoding="utf-8"))
    assert doc.get("$schema"), f"{name} declares no $schema"
    assert doc.get("$id"), f"{name} declares no $id"


def test_no_unpromoted_runtime_schemas() -> None:
    """A newly added runtime schema must be promoted too, not silently skipped.

    Without this, SCHEMA_NAMES above would quietly go stale: a fourth schema
    could land in install_assets/ and never reach the stable location.
    """
    runtime_names = {p.name for p in INSTALL_ASSETS.glob("*.schema.json")}
    assert runtime_names == set(SCHEMA_NAMES), (
        "install_assets/ schema set changed. Promote the new/removed schema to "
        "openspec/contracts/project-context-refresh/schemas/ and update "
        "SCHEMA_NAMES plus the table in openspec/contracts/README.md."
    )
