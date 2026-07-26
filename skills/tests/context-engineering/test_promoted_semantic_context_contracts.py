"""Guard the promoted ri-12 semantic-context contracts against archive-drift.

Both schemas exist in two live locations by design:

* ``openspec/changes/inject-scoped-semantic-context-into-coding-jobs/contracts/schemas/``
  — the in-flight copy, which moves to ``openspec/changes/archive/<date>-<id>/``
  the moment this change is archived.
* ``openspec/contracts/code-search/schemas/`` — the stable, capability-scoped
  home described in ``openspec/contracts/README.md``. This path does not move.

Design decision D10 requires the promotion to happen *inside* this change, so no
window opens in which a consumer can bind to the change-local path and then break
on archival. These tests are what makes that requirement enforceable: they fail
if a schema is authored but never promoted, if the two copies drift, or if a
promoted schema still advertises a change-local ``$id``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGE_ID = "inject-scoped-semantic-context-into-coding-jobs"
CHANGE_LOCAL = REPO_ROOT / "openspec/changes" / CHANGE_ID / "contracts/schemas"
PROMOTED = REPO_ROOT / "openspec/contracts/code-search/schemas"

SCHEMA_NAMES = (
    "semantic-context-hit.schema.json",
    "semantic-context-section.schema.json",
)

# Every promoted schema must claim this as its own base URI, so a ``$ref``
# between the two resolves to the promoted sibling rather than to a path that
# disappears on archival.
STABLE_ID_PREFIX = (
    "https://agentic-coding-tools/openspec/contracts/code-search/schemas/"
)


def relative(path: Path) -> str:
    """Repo-relative form of ``path``, for assertion messages."""
    return str(path.relative_to(REPO_ROOT))


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_change_local_schema_exists(name: str) -> None:
    """The in-flight copy this test claims to guard is actually authored.

    Without this the byte-compare below would raise ``FileNotFoundError`` and
    read as an unrelated crash rather than naming the missing file.
    """
    path = CHANGE_LOCAL / name
    assert path.is_file(), f"{name} is missing from {relative(CHANGE_LOCAL)}"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_copy_exists(name: str) -> None:
    """The stable copy exists before the change is archived (D10)."""
    path = PROMOTED / name
    assert path.is_file(), (
        f"{name} has not been promoted to {relative(PROMOTED)}. "
        "Copy it there in the same commit that authors it; tests and consumers "
        "load the promoted path, which survives archival."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_copy_is_byte_identical(name: str) -> None:
    """The two copies never diverge — they are changed in the same commit."""
    source = (CHANGE_LOCAL / name).read_bytes()
    promoted = (PROMOTED / name).read_bytes()
    assert promoted == source, (
        f"{name} differs between {relative(CHANGE_LOCAL)} and "
        f"{relative(PROMOTED)}. Two copies of one contract must stay "
        "byte-identical; update both in the same commit."
    )


def test_every_change_local_schema_is_promoted() -> None:
    """A newly authored schema cannot be left behind unpromoted.

    Asserting only over ``SCHEMA_NAMES`` would let a third schema be added to
    the change directory and silently never reach the stable path.
    """
    authored = {path.name for path in CHANGE_LOCAL.glob("*.schema.json")}
    promoted = {path.name for path in PROMOTED.glob("semantic-context-*.schema.json")}
    assert authored == set(SCHEMA_NAMES), (
        f"{relative(CHANGE_LOCAL)} holds {sorted(authored)}; SCHEMA_NAMES lists "
        f"{sorted(SCHEMA_NAMES)}. Add the new schema to SCHEMA_NAMES so it is guarded."
    )
    assert authored <= promoted, (
        f"not promoted: {sorted(authored - promoted)}. "
        f"Copy them into {relative(PROMOTED)}."
    )


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_promoted_schema_id_is_the_stable_path(name: str) -> None:
    """``$id`` names the promoted location, so ``$ref`` resolves there too.

    The section schema references the hit schema relatively. If ``$id`` pointed
    at ``openspec/changes/<id>/...`` the reference would resolve into a directory
    that archival moves — the exact drift the promoted location prevents.
    """
    schema = json.loads((PROMOTED / name).read_text(encoding="utf-8"))
    assert schema.get("$id") == STABLE_ID_PREFIX + name, (
        f"{name} declares $id={schema.get('$id')!r}; expected "
        f"{STABLE_ID_PREFIX + name!r} so relative $refs resolve to the "
        "promoted sibling."
    )
