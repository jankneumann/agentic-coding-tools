"""Guard the promoted context-refresh contracts against archive-drift.

Every context-refresh JSON Schema exists in two live locations by design:

* ``skills/<owning-skill>/install_assets/openspec/schemas/`` — what the runtime
  loads at import time (``models.py``) and what ``install.sh`` ships into
  consumer repositories, which have no ``openspec/contracts/`` of their own.
* ``openspec/contracts/project-context-refresh/schemas/`` — the stable,
  capability-scoped home described in ``openspec/contracts/README.md``, so the
  contract keeps a path that does not move when its originating change is
  archived.

The owning skill is *not* uniform: the record schemas ship from
``project-context-runtime``, while the branch-local checkpoint and the drift-gate
report ship from ``project-context-refresh``. Both promote into the same
capability directory, because ``project-context-refresh`` is the capability and
``project-context-runtime`` is only the library that holds its durable records.
``SCHEMA_OWNERS`` below is therefore the single place that knows which skill owns
which schema, and every test derives its paths from it.

Two copies can silently diverge, which is precisely the failure the promoted
location exists to prevent. These tests pin them together: change the runtime's
schema and the promoted copy must be updated in the same commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from models import OperationState, SemanticIndexStatus, derive_operation_id
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMOTED = REPO_ROOT / "openspec/contracts/project-context-refresh/schemas"

# schema file name -> name of the skill whose install_assets/ ships it.
SCHEMA_OWNERS = {
    "context-refresh-manifest.schema.json": "project-context-runtime",
    "context-refresh-operation.schema.json": "project-context-runtime",
    "context-refresh-types.schema.json": "project-context-runtime",
    "context-checkpoint.schema.json": "project-context-refresh",
    "context-convergence-record.schema.json": "project-context-refresh",
    "context-drift-gate.schema.json": "project-context-refresh",
}

SCHEMA_NAMES = tuple(sorted(SCHEMA_OWNERS))

OWNING_SKILLS = tuple(sorted(set(SCHEMA_OWNERS.values())))

DRIFT_GATE = "context-drift-gate.schema.json"

CONVERGENCE_RECORD = "context-convergence-record.schema.json"

SHARED_TYPES = "context-refresh-types.schema.json"


def install_assets_dir(skill: str) -> Path:
    """The install-asset schema directory shipped by ``skill``."""
    return REPO_ROOT / "skills" / skill / "install_assets/openspec/schemas"


def install_asset(name: str) -> Path:
    """The install-asset copy of ``name``, resolved through its owning skill."""
    return install_assets_dir(SCHEMA_OWNERS[name]) / name


def promoted_gate_schema() -> dict:
    return json.loads((PROMOTED / DRIFT_GATE).read_text(encoding="utf-8"))


def promoted_convergence_schema() -> dict:
    return json.loads((PROMOTED / CONVERGENCE_RECORD).read_text(encoding="utf-8"))


def convergence_validator() -> Draft202012Validator:
    """A validator for the promoted convergence record with local ``$ref``s.

    The record ``$ref``s ``GitRevision``/``Sha256``/``RepositoryPath`` out of the
    shared types schema instead of restating them. Building the registry from the
    promoted directory keeps the resolution offline *and* proves the two promoted
    schemas resolve against each other — a record that silently failed to resolve
    its ``$ref`` would accept any string where a revision is required.
    """
    resources = []
    for name in (CONVERGENCE_RECORD, SHARED_TYPES):
        doc = json.loads((PROMOTED / name).read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012)))
    registry = Registry().with_resources(resources)
    return Draft202012Validator(promoted_convergence_schema(), registry=registry)


def convergence_record(**overrides: object) -> dict:
    """A minimal valid convergence record, mutated by keyword for negative cases."""
    merged = "a" * 40
    record = {
        "schema_version": 1,
        "operation_id": derive_operation_id("agentic-coding-tools", merged),
        "merged_revision": merged,
        "refresh_revision": merged,
        "refresh_status": "degraded",
        "producers": [{"producer_id": "documentation.inventory", "status": "fresh", "owner": None}],
        "semantic_index": {
            "status": "pending",
            # The convergence commit moves main's tip, so the index is requested
            # for a revision that does not exist yet at merged_revision.
            "requested_revision": "b" * 40,
            "operation_id": None,
            "fallback": "exact search",
        },
        "merged_pull_requests": [{"number": 279, "origin": "openspec", "cleanup": "completed"}],
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_install_asset_exists(name: str) -> None:
    """Every schema this test claims to guard is actually shipped by its owner.

    Without this the byte-compare below would raise ``FileNotFoundError`` rather
    than name the missing file, and a schema promoted but never installed would
    read as an unrelated crash.
    """
    path = install_asset(name)
    assert path.is_file(), (
        f"{name} is missing from {path.parent.relative_to(REPO_ROOT)}. "
        f"SCHEMA_OWNERS says {SCHEMA_OWNERS[name]} ships it; install it there "
        "(that copy is what install.sh puts into consumer repositories)."
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
    runtime = install_asset(name).read_bytes()
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
    Draft202012Validator.check_schema(doc)


def test_no_unpromoted_runtime_schemas() -> None:
    """A newly added install-asset schema must be promoted too, not skipped.

    Without this, SCHEMA_OWNERS above would quietly go stale: another schema
    could land in some skill's install_assets/ and never reach the stable
    location. The glob covers every owning skill, so adding a schema to either
    tree is caught.
    """
    installed = {
        (skill, path.name)
        for skill in OWNING_SKILLS
        for path in install_assets_dir(skill).glob("*.schema.json")
    }
    assert installed == {(skill, name) for name, skill in SCHEMA_OWNERS.items()}, (
        "install_assets/ schema set changed. Promote the new/removed schema to "
        "openspec/contracts/project-context-refresh/schemas/ and update "
        "SCHEMA_OWNERS plus the table in openspec/contracts/README.md."
    )


def test_gate_semantic_status_is_not_a_semantic_index_status() -> None:
    """Design D6: the gate's ``not-attempted`` is deliberately a fourth value.

    ``SemanticIndexStatus`` members describe the outcome of an actual probe. The
    deterministic gate never probes, so reusing ``not-configured`` would assert a
    probe found no configuration. Pinning the ``const`` against the live enum
    means widening ``SemanticIndexStatus`` to include ``not-attempted`` — which
    would let a stale index be reported as a current one — breaks this test
    instead of passing silently.
    """
    status = promoted_gate_schema()["properties"]["semantic"]["properties"]["status"]
    assert status["const"] == "not-attempted"
    probe_outcomes = {member.value for member in SemanticIndexStatus}
    assert status["const"] not in probe_outcomes, (
        "context-drift-gate's semantic.status must not be a SemanticIndexStatus "
        f"value; SemanticIndexStatus currently has {sorted(probe_outcomes)}."
    )


def test_convergence_record_is_in_the_byte_compare_set() -> None:
    """The convergence record is guarded like every other context-refresh schema.

    ``SCHEMA_OWNERS`` drives the parametrized presence and byte-compare tests
    above, so this is the assertion that keeps the record inside them: dropping
    the entry to silence a drift failure fails here instead.
    """
    assert CONVERGENCE_RECORD in SCHEMA_NAMES
    assert SCHEMA_OWNERS[CONVERGENCE_RECORD] == "project-context-refresh"
    assert install_asset(CONVERGENCE_RECORD).is_file()
    assert (PROMOTED / CONVERGENCE_RECORD).is_file()


def test_convergence_refresh_status_keeps_not_run_out_of_the_operation_states() -> None:
    """Design D6: ``not-run`` is a fourth value, not a spelling of ``failed``.

    The apparatus row of D6 commits the cleanup output with no refresh at all.
    Collapsing that into ``failed`` would make a successful partial convergence
    indistinguishable from a producer crash, so the enum is the three terminal
    ri-06 operation states plus ``not-run``. Deriving the expectation from the
    live ``OperationState`` means widening that enum breaks this test rather
    than silently leaving the record unable to express a new state.
    """
    statuses = promoted_convergence_schema()["properties"]["refresh_status"]["enum"]
    terminal_states = {
        OperationState.SUCCEEDED.value,
        OperationState.DEGRADED.value,
        OperationState.FAILED.value,
    }
    assert "not-run" not in {member.value for member in OperationState}
    assert set(statuses) == terminal_states | {"not-run"}
    assert len(statuses) == len(set(statuses))


def test_convergence_semantic_index_revision_is_independent_of_merged_revision() -> None:
    """Design D7: the index is requested for a revision that is not the merge SHA.

    The convergence commit changes main's tip, so indexing ``merged_revision``
    would be stale on arrival. The two fields must therefore be separately
    settable — a schema that constrained them to be equal, or that reused one
    property for both, would force the stale behaviour D7 rejects.
    """
    validator = convergence_validator()
    record = convergence_record()
    assert record["semantic_index"]["requested_revision"] != record["merged_revision"]
    validator.validate(record)

    # Both fields resolve the shared GitRevision definition rather than
    # restating it, so a non-revision is rejected on either side. Without a
    # resolving $ref the strings below would validate.
    for mutate in (
        lambda doc: doc.update(merged_revision="not-a-revision"),
        lambda doc: doc["semantic_index"].update(requested_revision="not-a-revision"),
    ):
        broken = convergence_record()
        mutate(broken)
        assert not validator.is_valid(broken)


def test_convergence_semantic_index_mirrors_the_live_semantic_index_status() -> None:
    """The record cannot report an index state the runtime can never produce."""
    schema = promoted_convergence_schema()
    statuses = schema["properties"]["semantic_index"]["properties"]["status"]["enum"]
    assert set(statuses) == {member.value for member in SemanticIndexStatus}


def test_gate_architecture_freshness_separates_unverifiable_from_not_configured() -> None:
    """Design D4: unverifiable evidence blocks, absent tooling does not.

    Collapsing the two would reintroduce fail-open architecture freshness — a
    missing or malformed provenance file would be reported as 'the owner is not
    installed' and would stop failing the gate.
    """
    architecture = promoted_gate_schema()["properties"]["architecture"]["properties"]
    freshness = architecture["freshness"]["enum"]
    assert "unverifiable" in freshness
    assert "not-configured" in freshness
    assert len(freshness) == len(set(freshness))
    # 'provenance' is reported separately so 'stale' and 'no baseline at all'
    # are never conflated into one value (design D4).
    assert set(architecture["provenance"]["enum"]) == {"present", "missing", "malformed"}
