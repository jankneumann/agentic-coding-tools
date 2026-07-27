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
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMOTED = REPO_ROOT / "openspec/contracts/code-search/schemas"
CHANGE_ID = "inject-scoped-semantic-context-into-coding-jobs"
CONTRACTS_README = REPO_ROOT / "openspec/changes" / CHANGE_ID / "contracts/README.md"
COORDINATOR_SOURCE = REPO_ROOT / "agent-coordinator/src/code_search.py"

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


def fallback_section(
    trigger: str, reason: str, service_state: str | None = None
) -> dict[str, Any]:
    fallback: dict[str, Any] = {
        "trigger": trigger,
        "reason": reason,
        "strategy": "exact_search",
    }
    if service_state is not None:
        fallback["service_state"] = service_state
    return {
        "schema_version": 1,
        "status": "fallback",
        "consumer": "quick-task",
        "requested_revision": FULL_REVISION,
        "hits": [],
        "omissions": [],
        "fallback": fallback,
    }


def valid_fallback_section() -> dict[str, Any]:
    return fallback_section(
        "mismatched", "index_revision_differs", "revision_mismatch"
    )


# One contract-valid fallback per trigger. A literal table rather than a loop
# over the enum, because *which* reason and *which* service state a trigger
# admits is a design decision (D8, D14) and the schema now constrains it: a
# generic fixture reused across triggers would be rejected for the wrong reason.
TRIGGER_FIXTURES: dict[str, tuple[str, str | None]] = {
    "stale": ("working_tree_dirty", None),
    "unavailable": ("service_unavailable", "unavailable"),
    "mismatched": ("index_revision_differs", "revision_mismatch"),
    "out_of_scope": ("scope_rejected", "scope_rejected"),
    "no_context": ("index_returned_no_hits", "ready"),
}

#: The two D14 reasons: the search worked, and the section still has nothing to
#: show. They are reasons under one trigger rather than two triggers because the
#: remedy is identical; they are two reasons rather than one because "the index
#: held nothing similar" and "this client's own selection kept nothing" are
#: different facts about the world.
RELEVANCE_REASONS = ("index_returned_no_hits", "all_hits_omitted")


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


def test_the_trigger_fixture_table_covers_the_schema_enum() -> None:
    """Adding a trigger to the schema without a valid example fails here.

    Totality at the contract level: every trigger the schema admits must have a
    document that demonstrably validates, or the enum grows members no producer
    can legally emit.
    """
    assert set(TRIGGER_FIXTURES) == set(fallback_trigger_enum())


@pytest.mark.parametrize("trigger", sorted(TRIGGER_FIXTURES))
def test_every_documented_fallback_trigger_is_accepted(trigger: str) -> None:
    reason, state = TRIGGER_FIXTURES[trigger]
    assert section_validator.is_valid(fallback_section(trigger, reason, state))


def test_unknown_fallback_trigger_is_rejected() -> None:
    document = valid_fallback_section()
    document["fallback"]["trigger"] = "degraded"
    assert not section_validator.is_valid(document)


# --------------------------------------------------------------------------
# D14 — a healthy, current index that yields nothing is representable
# --------------------------------------------------------------------------


@pytest.mark.parametrize("reason", RELEVANCE_REASONS)
def test_a_successful_empty_search_has_an_honest_representation(reason: str) -> None:
    """The defect D14 fixes: `state=ready` with nothing to show was unsayable.

    Before D14 the only vocabulary for it was `unavailable` / `unknown_state`,
    which reports a correctly functioning service as broken.
    """
    assert section_validator.is_valid(fallback_section("no_context", reason, "ready"))


def test_the_two_relevance_reasons_are_distinct_schema_members() -> None:
    """"The index returned nothing" and "selection kept nothing" are two facts.

    Collapsing them would make the artifact unable to say whether raising the
    budget could have produced context.
    """
    enum = fallback_reason_enum()
    assert set(RELEVANCE_REASONS) <= set(enum)
    assert len(set(RELEVANCE_REASONS)) == 2


@pytest.mark.parametrize(
    "service_state",
    [None, "not_indexed", "unavailable", "revision_mismatch", "scope_rejected"],
    ids=["absent", "not_indexed", "unavailable", "revision_mismatch", "scope_rejected"],
)
def test_no_context_without_a_ready_service_state_is_rejected(
    service_state: str | None,
) -> None:
    """`no_context` asserts the service answered and answered well.

    Without the `ready` requirement the trigger could be emitted from a path
    that never queried, which would turn "we checked and there is nothing" into
    an unfalsifiable claim.
    """
    document = fallback_section("no_context", "index_returned_no_hits", service_state)
    assert not section_validator.is_valid(document)


@pytest.mark.parametrize("trigger", ["stale", "unavailable", "mismatched", "out_of_scope"])
@pytest.mark.parametrize("reason", RELEVANCE_REASONS)
def test_a_relevance_reason_under_another_trigger_is_rejected(
    trigger: str, reason: str
) -> None:
    """The pairing is closed both ways, so a producer cannot mix vocabularies.

    `unavailable` / `index_returned_no_hits` would re-create the original defect
    in the opposite direction: a working service filed under a broken one.
    """
    document = fallback_section(trigger, reason, TRIGGER_FIXTURES[trigger][1])
    assert not section_validator.is_valid(document)


@pytest.mark.parametrize(
    "reason",
    ["service_unavailable", "unknown_state", "all_hits_scope_filtered"],
)
def test_no_context_admits_only_the_relevance_reasons(reason: str) -> None:
    """A trigger that means "nothing relevant" cannot carry an outage reason."""
    document = fallback_section("no_context", reason, "ready")
    assert not section_validator.is_valid(document)


def test_all_hits_scope_filtered_stays_under_out_of_scope() -> None:
    """A scope boundary event is not a relevance event, and keeps its own trigger.

    Both can arise from a `ready` response, but only one is a statement about
    the package's declared read scope.
    """
    assert section_validator.is_valid(
        fallback_section("out_of_scope", "all_hits_scope_filtered", "ready")
    )
    assert not section_validator.is_valid(
        fallback_section("no_context", "all_hits_scope_filtered", "ready")
    )


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


# --------------------------------------------------------------------------
# The rendered vocabulary diverges from ri-03's deliberately (D7)
# --------------------------------------------------------------------------

NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}

# ri-03 `CodeSearchHit` field -> the name ri-12 renders it under. The roadmap's
# acceptance wording says "score" and "indexed commit"; the shipped coordinator
# contract says "similarity" and "source_revision". Both names are correct in
# their own layer, so the divergence is pinned here rather than resolved by
# quietly renaming one side.
RENDER_MAPPING = {
    "similarity": "score",
    "source_revision": "indexed_commit",
}


def readme_text() -> str:
    return CONTRACTS_README.read_text(encoding="utf-8")


def omission_reason_enum() -> list[str]:
    return SECTION_SCHEMA["properties"]["omissions"]["items"]["properties"]["reason"][
        "enum"
    ]


def fallback_trigger_enum() -> list[str]:
    return SECTION_SCHEMA["properties"]["fallback"]["properties"]["trigger"]["enum"]


def fallback_reason_enum() -> list[str]:
    return SECTION_SCHEMA["properties"]["fallback"]["properties"]["reason"]["enum"]


@pytest.mark.parametrize(("coordinator_name", "rendered_name"), RENDER_MAPPING.items())
def test_coordinator_still_uses_the_name_the_mapping_translates_from(
    coordinator_name: str, rendered_name: str
) -> None:
    """If ri-03 renames a field the mapping is stale, and this fails loudly.

    The mapping is only meaningful while both vocabularies exist. Asserting
    against the real coordinator model, rather than against a copy of it, is what
    makes that detectable.
    """
    source = COORDINATOR_SOURCE.read_text(encoding="utf-8")
    hit_model = source.split("class CodeSearchHit", 1)[-1].split("\nclass ", 1)[0]
    assert re.search(rf"^\s+{coordinator_name}: ", hit_model, re.MULTILINE), (
        f"agent-coordinator CodeSearchHit no longer declares {coordinator_name!r}; "
        f"the {coordinator_name} -> {rendered_name} render mapping is stale."
    )


@pytest.mark.parametrize(("coordinator_name", "rendered_name"), RENDER_MAPPING.items())
def test_hit_schema_uses_the_rendered_name_only(
    coordinator_name: str, rendered_name: str
) -> None:
    """The divergence is deliberate: never both names, never the wire name."""
    properties = HIT_SCHEMA["properties"]
    assert rendered_name in properties
    assert coordinator_name not in properties, (
        f"{coordinator_name!r} leaked into the ri-12 hit schema. The rendered "
        f"surface uses {rendered_name!r}; unifying the two vocabularies silently "
        "is exactly what the mapping table exists to prevent."
    )


@pytest.mark.parametrize(("coordinator_name", "rendered_name"), RENDER_MAPPING.items())
def test_readme_pins_the_render_mapping(
    coordinator_name: str, rendered_name: str
) -> None:
    """The mapping is documented where a reader of the contract will find it."""
    assert re.search(
        rf"\|\s*`{coordinator_name}`\s*\|\s*`{rendered_name}`\s*\|", readme_text()
    ), (
        f"the contracts README has no mapping row for "
        f"`{coordinator_name}` -> `{rendered_name}`."
    )


@pytest.mark.parametrize(
    ("label", "values"),
    [
        ("omissions[].reason", omission_reason_enum()),
        ("fallback.trigger", fallback_trigger_enum()),
    ],
)
def test_readme_enum_count_matches_the_schema(label: str, values: list[str]) -> None:
    """A prose count that drifts from the enum misleads every later reader."""
    match = re.search(
        rf"`{re.escape(label)}`[^\n]*?exactly (\w+) values", readme_text()
    )
    assert match, f"the README states no value count for `{label}`."
    claimed = NUMBER_WORDS.get(match.group(1))
    assert claimed == len(values), (
        f"the README says `{label}` has {match.group(1)} values; the schema "
        f"defines {len(values)}: {values}."
    )


@pytest.mark.parametrize(
    "value", sorted(set(omission_reason_enum()) | set(fallback_trigger_enum()))
)
def test_readme_documents_every_enum_value(value: str) -> None:
    """Adding a code to the schema without documenting it fails here."""
    assert f"`{value}`" in readme_text(), (
        f"{value!r} is in the schema but never named in the contracts README."
    )
