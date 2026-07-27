"""The tracked convergence record, against the published contract (ri-11 D9).

``.git-context/context-refresh-manifest.json`` is gitignored on purpose: ri-07
guarantees that a repeat refresh at one revision produces no repository diff, and
that directory is per-worktree and freely cleaned. Tracking it would undo both.
What lands instead is this record -- git-native, reviewable, append-only, one
JSON object per line -- pinning the manifest by ``sha256`` rather than copying it.

Everything here validates against the *promoted* contract at
``openspec/contracts/project-context-refresh/schemas/``, loaded independently of
the driver, so the driver cannot pass by grading its own homework.

Two fields carry the design and are asserted, not assumed:

* ``semantic_index.requested_revision`` on the completed record is deliberately a
  DIFFERENT revision from ``merged_revision``. The convergence commit moves
  main's tip, so indexing the pre-convergence revision would be stale on arrival
  and a correct system would then index a second time.
* ``refresh_status`` carries ``not-run`` alongside the three ri-06 operation
  states, because D6's apparatus row commits cleanup output with no refresh at
  all. Collapsing that into ``failed`` would make a successful partial
  convergence indistinguishable from a producer crash.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_SUITE_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SUITE_DIR.parents[1]
_REPO_ROOT = _SKILLS_DIR.parent
for _extra in (
    # The suite directory itself, so the scripted git environment in
    # ``test_convergence_outcomes`` can be reused here. Deliberately not a
    # ``conftest`` helper: ``skills/tests/`` resolves a bare ``conftest`` import
    # to whichever conftest pytest loaded first, so a generically-named shared
    # module there is a collision waiting to happen.
    _SUITE_DIR,
    _SKILLS_DIR / "merge-pull-requests" / "scripts",
    _SKILLS_DIR / "project-context-runtime" / "scripts",
    _SKILLS_DIR / "shared",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import main_convergence as mc  # noqa: E402

PROMOTED = _REPO_ROOT / "openspec" / "contracts" / "project-context-refresh" / "schemas"
RECORD_SCHEMA = PROMOTED / "context-convergence-record.schema.json"

MERGED_SHA = "a" * 40
CONVERGED_SHA = "c" * 40


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    """A validator built straight from the promoted contract, not from the driver."""
    resources = []
    schema = json.loads(RECORD_SCHEMA.read_text(encoding="utf-8"))
    for path in sorted(PROMOTED.glob("*.schema.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        resources.append((data["$id"], Resource.from_contents(data, default_specification=DRAFT202012)))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def _identity() -> mc.ConvergenceIdentity:
    return mc.ConvergenceIdentity(
        repository_id="agentic-coding-tools",
        merged_revision=MERGED_SHA,
        operation_id="pcr-" + "1" * 24,
    )


REFRESH_SUMMARY = {
    "operation_id": "pcr-" + "1" * 24,
    "outcome": "degraded",
    "manifest_path": ".git-context/context-refresh-manifest.json",
    "manifest_sha256": "d" * 64,
    "semantic_index": {
        "status": "pending",
        "requested_revision": MERGED_SHA,
        "operation_id": None,
        "registry_record_id": None,
        "indexed_revision": None,
        "fallback": {
            "kind": "exact-search",
            "reason": "Semantic indexing was deferred by the caller.",
        },
    },
    "producer_results": [
        {
            "producer_id": "documentation.inventory",
            "producer_version": "1",
            "status": "fresh",
            "owner": "docs-team",
        },
        {
            "producer_id": "architecture",
            "producer_version": "1",
            "status": "not-configured",
            "owner": None,
        },
    ],
}


def _prs():  # noqa: ANN202
    return (
        mc.MergedPullRequest(number=43, origin="dependabot"),
        mc.MergedPullRequest(number=42, origin="openspec", change_id="c-1", cleanup="completed"),
    )


# --------------------------------------------------------------------------- #
# Shape against the published contract
# --------------------------------------------------------------------------- #
def test_the_in_flight_record_validates(validator: Draft202012Validator) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    assert record["convergence_commit"] is None
    assert record["schema_version"] == 1


def test_the_completed_record_validates_and_names_the_convergence_commit(
    validator: Draft202012Validator,
) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
        convergence_commit=CONVERGED_SHA,
        semantic_index=mc.SemanticIndexRecord(
            status="pending",
            requested_revision=CONVERGED_SHA,
            operation_id="pcr-" + "2" * 24,
            fallback="exact-search: index enqueued for the pushed revision",
        ),
    )

    validator.validate(record)
    assert record["convergence_commit"] == CONVERGED_SHA


def test_the_enqueued_index_revision_is_not_the_merged_revision(
    validator: Draft202012Validator,
) -> None:
    """D7: the convergence commit moves main's tip, so the pre-convergence
    revision would be stale the moment it finished indexing."""
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
        convergence_commit=CONVERGED_SHA,
        semantic_index=mc.SemanticIndexRecord(
            status="pending", requested_revision=CONVERGED_SHA, fallback="exact-search"
        ),
    )

    validator.validate(record)
    assert record["semantic_index"]["requested_revision"] == CONVERGED_SHA
    assert record["semantic_index"]["requested_revision"] != record["merged_revision"]


@pytest.mark.parametrize("status", ["succeeded", "degraded", "failed", "not-run"])
def test_every_refresh_status_including_not_run_validates(
    validator: Draft202012Validator, status: str
) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status=status,
        summary=None if status == "not-run" else REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    assert record["refresh_status"] == status


def test_producers_are_joined_with_their_owners(validator: Draft202012Validator) -> None:
    """The ri-06 ProducerResult carries no owner; ownership lives on the registry
    spec, so the record is where the two are joined."""
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    by_id = {p["producer_id"]: p for p in record["producers"]}
    assert by_id["documentation.inventory"]["owner"] == "docs-team"
    assert by_id["documentation.inventory"]["status"] == "fresh"
    assert by_id["architecture"]["owner"] is None
    # Producer order is the record's, not the registry's: an iteration-order
    # dependency would make two runs over one tree render different bytes.
    ids = [p["producer_id"] for p in record["producers"]]
    assert ids == sorted(ids)
    assert ids != [p["producer_id"] for p in REFRESH_SUMMARY["producer_results"]]


def test_the_manifest_is_pinned_by_digest_not_copied(validator: Draft202012Validator) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    assert record["manifest_path"] == ".git-context/context-refresh-manifest.json"
    assert record["manifest_sha256"] == "d" * 64


def test_a_refresh_that_emitted_no_manifest_records_nulls(
    validator: Draft202012Validator,
) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="failed",
        summary=None,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    assert record["manifest_path"] is None
    assert record["manifest_sha256"] is None
    assert record["producers"] == []


def test_merged_pull_requests_are_ordered_deterministically(
    validator: Draft202012Validator,
) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    validator.validate(record)
    assert [pr["number"] for pr in record["merged_pull_requests"]] == [42, 43]


def test_two_builds_of_one_input_are_byte_identical() -> None:
    kwargs = dict(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    first = mc.render_record_line(mc.build_record(**kwargs))
    second = mc.render_record_line(mc.build_record(**kwargs))

    assert first == second


def test_warnings_are_bounded_to_the_contract_limit(validator: Draft202012Validator) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
        warnings=("x" * 5000,),
    )

    validator.validate(record)
    assert len(record["warnings"][0]) <= 500


def test_validate_record_rejects_a_malformed_record() -> None:
    with pytest.raises(mc.ConvergenceApparatusError):
        mc.validate_record({"schema_version": 1, "operation_id": "not-an-operation-id"})


def test_validate_record_accepts_a_well_formed_record() -> None:
    mc.validate_record(
        mc.build_record(
            identity=_identity(),
            refresh_revision=MERGED_SHA,
            refresh_status="degraded",
            summary=REFRESH_SUMMARY,
            merged_pull_requests=_prs(),
        )
    )


# --------------------------------------------------------------------------- #
# Append-only file semantics
# --------------------------------------------------------------------------- #
def test_append_writes_exactly_one_line_per_record(tmp_path: Path) -> None:
    record = mc.build_record(
        identity=_identity(),
        refresh_revision=MERGED_SHA,
        refresh_status="degraded",
        summary=REFRESH_SUMMARY,
        merged_pull_requests=_prs(),
    )

    path = mc.append_record(tmp_path, record)
    mc.append_record(tmp_path, record)

    assert path == tmp_path / mc.CONVERGENCE_RECORD_PATH
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_every_appended_line_validates_independently(
    tmp_path: Path, validator: Draft202012Validator
) -> None:
    for status in ("succeeded", "not-run"):
        mc.append_record(
            tmp_path,
            mc.build_record(
                identity=_identity(),
                refresh_revision=MERGED_SHA,
                refresh_status=status,
                summary=REFRESH_SUMMARY if status == "succeeded" else None,
                merged_pull_requests=_prs(),
            ),
        )

    path = tmp_path / mc.CONVERGENCE_RECORD_PATH
    for line in path.read_text(encoding="utf-8").splitlines():
        validator.validate(json.loads(line))


def test_append_preserves_existing_content(tmp_path: Path) -> None:
    path = tmp_path / mc.CONVERGENCE_RECORD_PATH
    path.parent.mkdir(parents=True)
    path.write_text('{"pre-existing": true}\n', encoding="utf-8")

    mc.append_record(
        tmp_path,
        mc.build_record(
            identity=_identity(),
            refresh_revision=MERGED_SHA,
            refresh_status="succeeded",
            summary=REFRESH_SUMMARY,
            merged_pull_requests=_prs(),
        ),
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"pre-existing": True}
    assert len(lines) == 2


def test_the_record_lands_in_the_convergence_commit_and_validates(
    tmp_path: Path, validator: Draft202012Validator
) -> None:
    """End to end: one pass appends exactly one line and stages it."""
    from test_convergence_outcomes import _FakeRepo, _NoStore  # noqa: PLC0415

    fake = _FakeRepo()
    result = mc.converge(
        tmp_path,
        runner=fake,
        store=_NoStore(),
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(),
        active_agent_checker=lambda root: (True, []),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
        semantic_enqueuer=lambda repository, revision: mc.SemanticIndexRecord(
            status="pending",
            requested_revision=revision,
            operation_id="pcr-" + "2" * 24,
            fallback="exact-search",
        ),
    )

    assert result.status is mc.ConvergenceStatus.CONVERGED
    path = tmp_path / mc.CONVERGENCE_RECORD_PATH
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    committed = json.loads(lines[0])
    validator.validate(committed)

    # The line inside the commit cannot name the commit that contains it, and
    # must not pretend otherwise by naming some other revision instead.
    assert committed["convergence_commit"] is None
    assert committed["merged_revision"] == MERGED_SHA

    # The record file is staged, so it lands in the single convergence commit.
    assert any(
        "git add" in " ".join(call) and mc.CONVERGENCE_RECORD_PATH in " ".join(call)
        for call in fake.calls
    )

    # The returned (completed) record closes the loop the committed line cannot.
    validator.validate(result.record)
    assert result.record["convergence_commit"] == "c" * 40
    assert result.record["semantic_index"]["requested_revision"] == "c" * 40


def test_a_blocked_pass_emits_no_record(tmp_path: Path) -> None:
    from test_convergence_outcomes import _FakeRepo, _NoStore  # noqa: PLC0415

    fake = _FakeRepo()
    mc.converge(
        tmp_path,
        runner=fake,
        store=_NoStore(),
        environ={},
        merged_revision=MERGED_SHA,
        merged_pull_requests=_prs(),
        active_agent_checker=lambda root: (False, ["agent-a"]),
        lock_acquirer=lambda **kw: {"status": "ok"},
        lock_releaser=lambda **kw: {"status": "ok"},
    )

    assert not (tmp_path / mc.CONVERGENCE_RECORD_PATH).exists()
