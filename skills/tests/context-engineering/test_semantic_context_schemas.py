"""The ri-12 semantic-context schemas are contracts, not documentation.

A schema that accepts everything it is shown proves nothing, so every test here
comes in a pair: one document that must validate, and the smallest possible
mutation of it that must not. The two headline rejections are the contradictory
states of design decision D10 — a section marked ``injected`` that also carries a
fallback, and a section marked ``fallback`` that also carries hits — because
those are the states the rendered surface would have no honest way to display.

Schemas are loaded from ``openspec/contracts/code-search/schemas/``, the promoted
path, never from the change directory. Binding tests to the change-local copy is
the archive-drift failure that ``openspec/contracts/README.md`` exists to prevent;
``test_promoted_semantic_context_contracts.py`` keeps the two copies identical.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMOTED = REPO_ROOT / "openspec/contracts/code-search/schemas"

HIT_SCHEMA_NAME = "semantic-context-hit.schema.json"
SECTION_SCHEMA_NAME = "semantic-context-section.schema.json"

FULL_REVISION = "1cf51386d0c0ffee1cf51386d0c0ffee1cf51386"
OTHER_REVISION = "abcdef0123456789abcdef0123456789abcdef01"
INDEX_ID = "9f1c0b3a-6d2e-4f81-9a44-0e1b2c3d4e5f"


def load(name: str) -> dict[str, Any]:
    return json.loads((PROMOTED / name).read_text(encoding="utf-8"))


HIT_SCHEMA = load(HIT_SCHEMA_NAME)
SECTION_SCHEMA = load(SECTION_SCHEMA_NAME)

# The section references the hit schema relatively. Resolving that reference is
# part of what is under test: if it silently failed to resolve, every malformed
# hit nested in a section would validate.
REGISTRY = Registry().with_resources(
    [
        (schema["$id"], Resource.from_contents(schema))
        for schema in (HIT_SCHEMA, SECTION_SCHEMA)
    ]
)

hit_validator = Draft202012Validator(HIT_SCHEMA, registry=REGISTRY)
section_validator = Draft202012Validator(SECTION_SCHEMA, registry=REGISTRY)


def valid_hit() -> dict[str, Any]:
    return {
        "file_path": "skills/context-engineering/scripts/semantic_context.py",
        "start_line": 120,
        "end_line": 158,
        "score": 0.8123,
        "indexed_commit": FULL_REVISION,
        "index_id": INDEX_ID,
        "scope_decision": "allowed",
        "language": "python",
        "content": "def collect_semantic_context(request):\n    ...\n",
    }


def valid_injected_section() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "injected",
        "consumer": "implement-feature",
        "requested_revision": FULL_REVISION,
        "hits": [valid_hit()],
        "omissions": [
            {
                "file_path": "skills/context-engineering/scripts/render.py",
                "start_line": 10,
                "end_line": 90,
                "reason": "hit_line_cap",
            }
        ],
        "provenance": {
            "repo_slug": "agentic_coding_tools",
            "namespace_kind": "work_package",
            "namespace_key": "inject-scoped-semantic-context-into-coding-jobs--wp-retrieval",
            "index_id": INDEX_ID,
            "scope_decision": "allowed",
            "scope_authority": "principal_grant",
            "read_allow_count": 4,
            "deny_count": 1,
        },
    }


def valid_fallback_section() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "fallback",
        "consumer": "quick-task",
        "requested_revision": FULL_REVISION,
        "hits": [],
        "omissions": [],
        "fallback": {
            "trigger": "mismatched",
            "reason": "index_revision_differs",
            "strategy": "exact_search",
            "service_state": "revision_mismatch",
        },
    }


def mutate(document: dict[str, Any], **changes: Any) -> dict[str, Any]:
    updated = copy.deepcopy(document)
    updated.update(changes)
    return updated


# --------------------------------------------------------------------------
# The schemas are themselves well-formed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", [HIT_SCHEMA_NAME, SECTION_SCHEMA_NAME])
def test_schema_is_a_valid_json_schema(name: str) -> None:
    Draft202012Validator.check_schema(load(name))


@pytest.mark.parametrize("schema", [HIT_SCHEMA, SECTION_SCHEMA], ids=["hit", "section"])
def test_schema_is_closed(schema: dict[str, Any]) -> None:
    """An open contract cannot be relied on: unknown fields would pass review."""
    assert schema["additionalProperties"] is False


# --------------------------------------------------------------------------
# The two contradictory states (D10)
# --------------------------------------------------------------------------


def test_injected_section_validates() -> None:
    assert section_validator.is_valid(valid_injected_section())


def test_fallback_section_validates() -> None:
    assert section_validator.is_valid(valid_fallback_section())


def test_injected_section_carrying_a_fallback_is_rejected() -> None:
    """``status="injected"`` plus a fallback record has no rendering."""
    document = mutate(
        valid_injected_section(),
        fallback={
            "trigger": "stale",
            "reason": "working_tree_dirty",
            "strategy": "exact_search",
        },
    )
    assert not section_validator.is_valid(document)


def test_fallback_section_carrying_hits_is_rejected() -> None:
    """``status="fallback"`` plus hits would show excerpts it just disclaimed."""
    document = mutate(valid_fallback_section(), hits=[valid_hit()])
    assert not section_validator.is_valid(document)


def test_injected_section_without_hits_is_rejected() -> None:
    """Injecting nothing is a fallback, not an empty injection."""
    assert not section_validator.is_valid(mutate(valid_injected_section(), hits=[]))


def test_injected_section_without_provenance_is_rejected() -> None:
    document = valid_injected_section()
    del document["provenance"]
    assert not section_validator.is_valid(document)


def test_fallback_section_without_a_fallback_record_is_rejected() -> None:
    document = valid_fallback_section()
    del document["fallback"]
    assert not section_validator.is_valid(document)


def test_fallback_section_carrying_provenance_is_rejected() -> None:
    """Provenance names the index that answered; nothing answered."""
    document = mutate(
        valid_fallback_section(),
        provenance=valid_injected_section()["provenance"],
    )
    assert not section_validator.is_valid(document)


# --------------------------------------------------------------------------
# Closed enums and version pinning
# --------------------------------------------------------------------------


def test_unknown_status_is_rejected() -> None:
    assert not section_validator.is_valid(
        mutate(valid_injected_section(), status="partial")
    )


def test_unknown_schema_version_is_rejected() -> None:
    assert not section_validator.is_valid(
        mutate(valid_injected_section(), schema_version=2)
    )


def test_unknown_top_level_field_is_rejected() -> None:
    assert not section_validator.is_valid(
        mutate(valid_injected_section(), rendered_markdown="## Semantic code context")
    )


@pytest.mark.parametrize(
    "reason",
    [
        "duplicate_exact",
        "duplicate_contained",
        "hit_count_cap",
        "file_count_cap",
        "hit_line_cap",
        "total_line_cap",
        "scope_filtered",
    ],
)
def test_every_documented_omission_reason_is_accepted(reason: str) -> None:
    document = valid_injected_section()
    document["omissions"][0]["reason"] = reason
    assert section_validator.is_valid(document)


def test_unknown_omission_reason_is_rejected() -> None:
    document = valid_injected_section()
    document["omissions"][0]["reason"] = "too_long"
    assert not section_validator.is_valid(document)


@pytest.mark.parametrize(
    "trigger", ["stale", "unavailable", "mismatched", "out_of_scope"]
)
def test_every_documented_fallback_trigger_is_accepted(trigger: str) -> None:
    document = valid_fallback_section()
    document["fallback"]["trigger"] = trigger
    assert section_validator.is_valid(document)


def test_unknown_fallback_trigger_is_rejected() -> None:
    document = valid_fallback_section()
    document["fallback"]["trigger"] = "degraded"
    assert not section_validator.is_valid(document)


def test_non_exact_search_strategy_is_rejected() -> None:
    """Exact search plus direct reads is the only fallback ri-12 offers."""
    document = valid_fallback_section()
    document["fallback"]["strategy"] = "keyword_search"
    assert not section_validator.is_valid(document)


def test_unknown_service_state_is_rejected() -> None:
    """``service_state`` mirrors ri-03's ``CodeSearchState``; nothing else."""
    document = valid_fallback_section()
    document["fallback"]["service_state"] = "degraded"
    assert not section_validator.is_valid(document)


# --------------------------------------------------------------------------
# Per-hit provenance
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(HIT_SCHEMA["required"]))
def test_every_hit_field_is_required(field: str) -> None:
    """A hit missing any provenance field cannot be judged, so it is invalid."""
    document = valid_hit()
    del document[field]
    assert not hit_validator.is_valid(document)


def test_unknown_hit_field_is_rejected() -> None:
    assert not hit_validator.is_valid(mutate(valid_hit(), rank=1))


def test_downgraded_scope_decision_is_rejected() -> None:
    """A hit failing the local re-check is omitted, never rendered as rejected."""
    assert not hit_validator.is_valid(mutate(valid_hit(), scope_decision="rejected"))


@pytest.mark.parametrize(
    "index_id",
    ["not-a-uuid", "", "9f1c0b3a6d2e4f819a440e1b2c3d4e5f", INDEX_ID + "f"],
)
def test_non_uuid_index_id_is_rejected(index_id: str) -> None:
    """``format: uuid`` alone is an annotation — validators ignore it by default.

    Without a pattern the contract silently accepts any string here, and the
    identity of the index that served a hit stops being checkable.
    """
    assert not hit_validator.is_valid(mutate(valid_hit(), index_id=index_id))


@pytest.mark.parametrize(
    "file_path",
    [
        "/etc/passwd",
        "../outside/the/repo.py",
        "skills/../../etc/passwd",
        "skills/context-engineering/..",
    ],
)
def test_absolute_or_traversing_file_path_is_rejected(file_path: str) -> None:
    """The field is documented as repo-relative with no ``..``; enforce it.

    A rendered section names files the worker is invited to open, so a path that
    escapes the repository is a scope claim the contract must not be able to make.
    """
    assert not hit_validator.is_valid(mutate(valid_hit(), file_path=file_path))


@pytest.mark.parametrize(
    "file_path",
    [
        "skills/context-engineering/scripts/semantic_context.py",
        "docs/guides/a..b.md",
        "a",
    ],
)
def test_ordinary_relative_file_path_is_accepted(file_path: str) -> None:
    """The traversal guard must not reject legitimate paths containing dots."""
    assert hit_validator.is_valid(mutate(valid_hit(), file_path=file_path))


@pytest.mark.parametrize("score", [1.5, -1.5])
def test_out_of_range_score_is_rejected(score: float) -> None:
    assert not hit_validator.is_valid(mutate(valid_hit(), score=score))


def test_zero_start_line_is_rejected() -> None:
    """Line numbers are 1-based and inclusive."""
    assert not hit_validator.is_valid(mutate(valid_hit(), start_line=0))


@pytest.mark.parametrize("revision", ["HEAD", "1cf5138", FULL_REVISION.upper(), ""])
def test_non_full_revision_indexed_commit_is_rejected(revision: str) -> None:
    """``indexed_commit`` carries ri-03's ``FullRevision`` shape, not a ref."""
    assert not hit_validator.is_valid(mutate(valid_hit(), indexed_commit=revision))


def test_non_full_revision_requested_revision_is_rejected() -> None:
    assert not section_validator.is_valid(
        mutate(valid_injected_section(), requested_revision="HEAD")
    )


# --------------------------------------------------------------------------
# The section's reference to the hit schema is live
# --------------------------------------------------------------------------


def test_section_rejects_a_malformed_nested_hit() -> None:
    """Proves the relative ``$ref`` resolved.

    If it had not, the hits array would be unconstrained and this document —
    whose only defect is inside a hit — would validate.
    """
    document = valid_injected_section()
    document["hits"][0]["score"] = 12.0
    assert not section_validator.is_valid(document)


def test_section_rejects_a_traversing_path_in_an_omission() -> None:
    """Omissions name files too, so they carry the same path guarantee."""
    document = valid_injected_section()
    document["omissions"][0]["file_path"] = "../outside/the/repo.py"
    assert not section_validator.is_valid(document)


def test_non_uuid_provenance_index_id_is_rejected() -> None:
    document = valid_injected_section()
    document["provenance"]["index_id"] = "not-a-uuid"
    assert not section_validator.is_valid(document)
