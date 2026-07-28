"""The corpus is the evidence; these tests are what stop it rotting silently.

Every number this evaluation gates on is judged against hand labels, and a hand
label is only worth something while the thing it names still exists. The
archived evaluation this corpus is rescued from
(``openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/``) had no
such check: its labels were verified once, by hand, on 2026-07-19, and nothing
would have noticed a renamed file afterwards.

Four properties, each of which was an actual failure mode of the artifact this
replaces:

* **Declared, never inferred.** Every consumer ri-12 ships must appear in the
  manifest with an explicit ``utility_applicable`` boolean and a non-empty case
  slice. A consumer with neither is a corpus *error* — silent absence is
  indistinguishable from an oversight, and ``quick-task``'s legitimate exemption
  has to be readable as a decision (design D3, D7).
* **Every labeled path resolves.** ``expected_files``, ``must_touch``, and every
  ``evidence_spans`` entry name a file that exists, at a line range inside it.
* **Schema-valid.** Manifest and cases are validated here against the *promoted*
  contracts, deliberately without going through the loader, so a loader that
  forgot to validate cannot hide a malformed corpus.
* **Digest-stable.** Two independent loads agree; one changed corpus byte
  disagrees. That digest is what ri-13's enablement gate uses to decide a report
  still describes the corpus it claims to (design D12).

Two tests here are green before the corpus exists, and correctly so:
``test_archived_eval_set_is_the_rescue_source`` and
``test_archived_expected_files_still_exist`` are statements about the *source*
material and the current tree, not about the rescue. They are preconditions —
if the archived set stopped having ten labeled tasks, or its labels stopped
resolving, the rescue would be copying something other than what this change
claims to be rescuing.

Vocabulary is derived, never retyped: the six consumer ids come from the
``consumer="…"`` declarations in the skills that issue the requests, and the
context budget comes from ``ContextBudget``'s own field defaults in ri-12's
module. Restating either here would let this corpus drift from the runtime it
is supposed to be measuring and still pass.
"""

from __future__ import annotations

import ast
import json
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]

PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
MANIFEST = CORPUS_ROOT / "manifest.yaml"
CASES_DIR = CORPUS_ROOT / "cases"

SCHEMA_DIR = REPO_ROOT / "openspec/contracts/semantic-context-evaluation/schemas"
CORPUS_SCHEMA = SCHEMA_DIR / "context-eval-corpus.schema.json"
CASE_SCHEMA = SCHEMA_DIR / "context-eval-case.schema.json"

#: The artifact the ten labeled tasks are rescued from (design D10).
ARCHIVED_EVAL_SET = (
    REPO_ROOT
    / "openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/eval-set.yaml"
)

SKILLS_ROOT = REPO_ROOT / "skills"
SEMANTIC_CONTEXT = SKILLS_ROOT / "context-engineering/scripts/semantic_context.py"

#: The four service conditions the corpus must prove restore exact search
#: (design D12, spec ``Fail-Closed Regression Cases``). Each is a
#: ``(trigger, reason)`` pair, because ri-12's state mapping is total: a case
#: asserting only the trigger would pass on the wrong cause.
REQUIRED_FAIL_CLOSED_PAIRS = (
    ("stale", "revision_not_indexed"),
    ("mismatched", "index_revision_differs"),
    ("out_of_scope", "scope_rejected"),
    ("unavailable", "unknown_state"),
)

#: Integers so structurally ubiquitous in Python that asserting their absence
#: would forbid indexing and iteration rather than forbid a hardcoded threshold.
#: Everything else declared in the manifest is checked. The corpus's gate-bearing
#: numbers are deliberately chosen outside this set so the check has teeth; the
#: two thresholds that unavoidably *are* 0 or 1 are documented in the corpus
#: README as the residual gap.
UBIQUITOUS_LITERALS = frozenset({0, 1})

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _load() -> Any:
    """Load the corpus, turning apparatus problems into ordinary failures.

    A missing loader or an unloadable corpus is reported as a test *failure*
    rather than a collection error, so the RED state of task 2.1 reads as "these
    N properties are unproven" instead of one opaque import traceback.
    """
    try:
        from context_eval.loader import load_corpus
    except Exception as exc:  # noqa: BLE001 - any import problem is the same failure
        pytest.fail(f"context_eval.loader is not importable: {exc!r}")
    try:
        return load_corpus(CORPUS_ROOT, schema_dir=SCHEMA_DIR)
    except Exception as exc:  # noqa: BLE001 - any load problem is the same failure
        pytest.fail(f"the corpus at {CORPUS_ROOT} did not load: {exc!r}")


def _raw_manifest() -> dict[str, Any]:
    if not MANIFEST.is_file():
        pytest.fail(f"corpus manifest is missing: {MANIFEST}")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _raw_cases() -> dict[str, dict[str, Any]]:
    """Every case file named by the manifest, parsed straight from disk."""
    manifest = _raw_manifest()
    parsed: dict[str, dict[str, Any]] = {}
    for rel in manifest.get("cases", []):
        path = CORPUS_ROOT / rel
        if not path.is_file():
            pytest.fail(f"manifest lists a case file that does not exist: {rel}")
        parsed[rel] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not parsed:
        pytest.fail("the manifest declares no cases")
    return parsed


def _archived_tasks() -> list[dict[str, Any]]:
    document = yaml.safe_load(ARCHIVED_EVAL_SET.read_text(encoding="utf-8"))
    return list(document["tasks"])


def _ri12_consumers() -> tuple[str, ...]:
    """The consumer ids, read from the skills that declare them.

    A skill's directory name is also its ``consumer`` id, and each of the six
    consumers carries a ``consumer="<its own name>"`` line in its SKILL.md. That
    self-identification is the runtime fact; the list is derived from it so a
    seventh consumer is a corpus failure the day it ships.
    """
    found = set()
    for skill_md in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        name = skill_md.parent.name
        if f'consumer="{name}"' in skill_md.read_text(encoding="utf-8"):
            found.add(name)
    if not found:
        pytest.fail("no skill declares a consumer id; the derivation is broken")
    return tuple(sorted(found))


def _ri12_budget_defaults() -> dict[str, int]:
    """``ContextBudget``'s field defaults, read out of ri-12's source by AST.

    Parsed rather than imported: ``packages/`` must not depend on ``skills/``,
    and an AST read cannot be satisfied by an environment variable override.
    """
    tree = ast.parse(SEMANTIC_CONTEXT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ContextBudget":
            defaults: dict[str, int] = {}
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.value, ast.Constant
                ):
                    target = statement.target
                    if isinstance(target, ast.Name) and isinstance(statement.value.value, int):
                        defaults[target.id] = statement.value.value
            return defaults
    pytest.fail(f"ContextBudget not found in {SEMANTIC_CONTEXT}")


def _validator(schema_path: Path) -> Draft202012Validator:
    if not schema_path.is_file():
        pytest.fail(f"promoted schema is missing: {schema_path}")
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _violates_scope(file_path: str, scope: Any) -> bool:
    """Deny-precedence scope test, using the repo's own glob semantics.

    ``fnmatch`` is what ``scope_checker.py`` itself uses, and its ``*`` crosses
    ``/``, so ``agent-coordinator/src/**`` matches nested paths. Deny is
    evaluated first and wins outright — an adversarial body whose leaked hit sits
    *inside* ``read_allow`` and is excluded only by a deny glob (see
    ``ADV-DENY-PRECEDENCE``) is the shape a prefix comparison cannot express.
    """
    if any(fnmatch(file_path, glob) for glob in scope.deny):
        return True
    return not any(fnmatch(file_path, glob) for glob in scope.read_allow)


def _numeric_literals(module: Path) -> set[float]:
    """Every int/float literal in a module, booleans excluded."""
    literals: set[float] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if not isinstance(node.value, bool):
                literals.add(node.value)
    return literals


# --------------------------------------------------------------------------
# preconditions on the rescue source (green before the corpus exists)
# --------------------------------------------------------------------------


def test_archived_eval_set_is_the_rescue_source() -> None:
    """The archived set still holds the ten labeled tasks being rescued."""
    assert ARCHIVED_EVAL_SET.is_file(), f"rescue source is missing: {ARCHIVED_EVAL_SET}"
    tasks = _archived_tasks()
    assert [task["id"] for task in tasks] == [f"T{n}" for n in range(1, 11)]


def test_archived_expected_files_still_exist() -> None:
    """Every file the archived labels name still resolves in this tree.

    Verified individually at ``748af34c``; re-checked here on every run, because
    a moved path silently turns a labeled case into an unwinnable one.
    """
    missing = sorted(
        {
            path
            for task in _archived_tasks()
            for path in task["expected_files"]
            if not (REPO_ROOT / path).is_file()
        }
    )
    assert not missing, f"archived labels name files that no longer exist: {missing}"


# --------------------------------------------------------------------------
# schema validity
# --------------------------------------------------------------------------


def test_manifest_validates_against_the_corpus_schema() -> None:
    errors = sorted(_validator(CORPUS_SCHEMA).iter_errors(_raw_manifest()), key=str)
    assert not errors, "\n".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)


def test_every_case_validates_against_the_case_schema() -> None:
    validator = _validator(CASE_SCHEMA)
    problems: list[str] = []
    for rel, case in _raw_cases().items():
        for error in validator.iter_errors(case):
            problems.append(f"{rel} {list(error.absolute_path)}: {error.message}")
    assert not problems, "\n".join(sorted(problems))


# --------------------------------------------------------------------------
# declared, never inferred
# --------------------------------------------------------------------------


def test_every_ri12_consumer_has_a_slice_with_explicit_utility_applicable() -> None:
    """A consumer with no slice and no explicit statement is a corpus error."""
    corpus = _load()
    slices = {slice_.consumer: slice_ for slice_ in corpus.consumers}
    problems: list[str] = []
    for consumer in _ri12_consumers():
        slice_ = slices.get(consumer)
        if slice_ is None:
            problems.append(f"{consumer}: declared by no consumer slice")
            continue
        if not isinstance(slice_.utility_applicable, bool):
            problems.append(f"{consumer}: utility_applicable is not an explicit boolean")
        if not slice_.cases:
            problems.append(f"{consumer}: declares an empty case slice")
    assert not problems, "\n".join(problems)


def test_no_slice_declares_an_unknown_consumer() -> None:
    corpus = _load()
    known = set(_ri12_consumers())
    unknown = sorted({s.consumer for s in corpus.consumers} - known)
    assert not unknown, f"corpus declares consumers no skill identifies as: {unknown}"


def test_every_case_is_claimed_by_exactly_one_slice() -> None:
    corpus = _load()
    claims: dict[str, list[str]] = {}
    for slice_ in corpus.consumers:
        for case_id in slice_.cases:
            claims.setdefault(case_id, []).append(slice_.consumer)

    problems: list[str] = []
    for case in corpus.cases:
        owners = claims.get(case.case_id, [])
        if len(owners) != 1:
            problems.append(f"{case.case_id}: claimed by {owners or 'no consumer'}")
        elif owners[0] != case.consumer:
            problems.append(
                f"{case.case_id}: file says consumer={case.consumer}, slice says {owners[0]}"
            )
    dangling = sorted(set(claims) - {case.case_id for case in corpus.cases})
    problems.extend(f"{case_id}: claimed by a slice but has no case file" for case_id in dangling)
    assert not problems, "\n".join(problems)


def test_every_case_file_is_listed_by_the_manifest() -> None:
    """An unlisted case file is a silent omission; the list is the denominator."""
    listed = {(CORPUS_ROOT / rel).resolve() for rel in _raw_manifest().get("cases", [])}
    on_disk = {path.resolve() for path in CASES_DIR.glob("*.yaml")}
    unlisted = sorted(str(p.relative_to(CORPUS_ROOT)) for p in on_disk - listed)
    assert not unlisted, f"case files exist but are not declared: {unlisted}"


def test_quick_task_declares_utility_inapplicable_with_a_reason() -> None:
    """Its SKILL.md documents that it never has a declared scope (design D7)."""
    corpus = _load()
    slices = {slice_.consumer: slice_ for slice_ in corpus.consumers}
    slice_ = slices.get("quick-task")
    assert slice_ is not None, "quick-task has no slice"
    assert slice_.utility_applicable is False
    assert slice_.utility_not_applicable_reason

    by_id = {case.case_id: case for case in corpus.cases}
    non_fail_closed = [c for c in slice_.cases if by_id[c].expectation is None]
    assert not non_fail_closed, (
        f"quick-task declares utility inapplicable but carries utility cases: {non_fail_closed}"
    )


def test_all_declared_gates_are_required_and_tiered() -> None:
    corpus = _load()
    kinds = {gate.kind for gate in corpus.gates}
    assert kinds == {
        "retrieval_quality",
        "coding_context_utility",
        "scope_compliance",
        "fail_closed_regression",
    }
    for gate in corpus.gates:
        assert gate.required is True, f"{gate.id}: gates are unconditionally required"
        assert gate.thresholds, f"{gate.id}: a gate judged against nothing passes everything"
        assert gate.min_index_tier in {"none", "seeded", "live"}


# --------------------------------------------------------------------------
# every labeled path resolves
# --------------------------------------------------------------------------


def test_every_labeled_path_exists_in_the_repository() -> None:
    corpus = _load()
    problems: list[str] = []
    for case in corpus.cases:
        labeled = [
            *((path, "expected_files") for path in case.labels.expected_files),
            *((path, "must_touch") for path in case.labels.must_touch),
            *((span.file_path, "evidence_spans") for span in case.labels.evidence_spans),
        ]
        for path, field in labeled:
            if not (REPO_ROOT / path).is_file():
                problems.append(f"{case.case_id}.labels.{field}: {path} does not exist")
    assert not problems, "\n".join(problems)


def test_every_evidence_span_lies_inside_its_file() -> None:
    corpus = _load()
    problems: list[str] = []
    for case in corpus.cases:
        for span in case.labels.evidence_spans:
            target = REPO_ROOT / span.file_path
            if not target.is_file():
                continue  # reported by the labeled-path test
            if span.end_line < span.start_line:
                problems.append(f"{case.case_id}: {span.file_path} end_line < start_line")
                continue
            line_count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            if span.end_line > line_count:
                problems.append(
                    f"{case.case_id}: {span.file_path} span ends at {span.end_line} "
                    f"but the file has {line_count} lines"
                )
    assert not problems, "\n".join(problems)


def test_every_recorded_response_file_exists_and_parses() -> None:
    corpus = _load()
    problems: list[str] = []
    for case in corpus.cases:
        if case.recorded_response is None:
            continue
        path = CORPUS_ROOT / case.recorded_response.path
        if not path.is_file():
            problems.append(f"{case.case_id}: recorded response missing: {path}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{case.case_id}: recorded response is not JSON: {exc}")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------
# the measurable behaviours the corpus has to contain
# --------------------------------------------------------------------------


def test_fail_closed_regression_conditions_are_all_covered() -> None:
    """Each of D12's four conditions has a case expecting zero rendered hits."""
    corpus = _load()
    observed = {
        (case.expectation.trigger, case.expectation.reason)
        for case in corpus.cases
        if case.expectation is not None and case.expectation.status == "fallback"
    }
    missing = [pair for pair in REQUIRED_FAIL_CLOSED_PAIRS if pair not in observed]
    assert not missing, f"no fail-closed case asserts: {missing}"

    leaking = [
        case.case_id
        for case in corpus.cases
        if case.expectation is not None
        and case.expectation.status == "fallback"
        and case.expectation.rendered_hits != 0
    ]
    assert not leaking, f"a fallback that renders hits is not a fallback: {leaking}"


def test_adversarial_scope_cases_carry_an_out_of_scope_recorded_hit() -> None:
    """The scope gate is only evidence if the server is allowed to misbehave."""
    corpus = _load()
    adversarial = [
        case
        for case in corpus.cases
        if case.recorded_response is not None and case.recorded_response.adversarial
    ]
    assert adversarial, "no adversarial case: the scope gate would prove only that the server behaved"

    problems: list[str] = []
    for case in adversarial:
        body = json.loads((CORPUS_ROOT / case.recorded_response.path).read_text(encoding="utf-8"))
        outside = [
            result["file_path"]
            for result in body.get("results", [])
            if _violates_scope(result["file_path"], case.scope)
        ]
        if not outside:
            problems.append(
                f"{case.case_id}: marked adversarial but every recorded hit is in scope"
            )
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------
# thresholds are corpus data
# --------------------------------------------------------------------------


def test_thresholds_are_not_readable_from_the_scoring_modules() -> None:
    """No manifest number may appear as a literal anywhere under ``src/``.

    ``run_eval.py:159-161`` hardcoded ``>= 7`` and ``>= 2``; a threshold that
    lives in code cannot be reviewed as a diff against the evidence it gates
    (design D6).
    """
    manifest = _raw_manifest()
    declared: set[float] = {manifest["k"], *manifest["budget"].values()}
    for gate in manifest["gates"]:
        declared.update(gate["thresholds"].values())
    checkable = {value for value in declared if value not in UBIQUITOUS_LITERALS}
    assert checkable, "every declared number is exempt; the check would prove nothing"

    problems: list[str] = []
    for module in sorted(SRC.rglob("*.py")):
        found = sorted(checkable & _numeric_literals(module))
        if found:
            problems.append(f"{module.relative_to(REPO_ROOT)}: hardcodes {found}")
    assert not problems, "\n".join(problems)


def test_budget_matches_ri12_runtime_defaults() -> None:
    """Both arms are rendered under ri-12's own bounds, not a restatement of them."""
    assert _raw_manifest()["budget"] == _ri12_budget_defaults()


# --------------------------------------------------------------------------
# digest
# --------------------------------------------------------------------------


def test_corpus_digest_is_stable_across_two_independent_loads() -> None:
    assert _load().digest == _load().digest


def test_corpus_digest_changes_when_a_corpus_byte_changes(tmp_path: Path) -> None:
    """The digest is what makes a stale report detectable (design D12)."""
    try:
        from context_eval.loader import load_corpus
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"context_eval.loader is not importable: {exc!r}")

    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS_ROOT, copied)
    before = load_corpus(copied, schema_dir=SCHEMA_DIR).digest

    target = copied / _raw_manifest()["cases"][0]
    text = target.read_text(encoding="utf-8")
    marker = "query:"
    assert marker in text, f"{target} has no query to perturb"
    target.write_text(text.replace(marker, "query: perturbed ", 1), encoding="utf-8")

    after = load_corpus(copied, schema_dir=SCHEMA_DIR).digest
    assert before != after, "one changed corpus byte left the digest unmoved"


# --------------------------------------------------------------------------
# the rescue kept its identity
# --------------------------------------------------------------------------


def test_rescued_cases_retain_their_original_identifiers() -> None:
    """T1..T10 keep id, query, expected files, category, rationale, and baseline.

    Comparability with the evaluation these ten came from is the entire reason
    to rescue them rather than write ten fresh ones.
    """
    corpus = _load()
    by_id = {case.case_id: case for case in corpus.cases}
    problems: list[str] = []

    for task in _archived_tasks():
        case = by_id.get(task["id"])
        if case is None:
            problems.append(f"{task['id']}: rescued case is missing from the corpus")
            continue
        if case.query != task["query"]:
            problems.append(f"{case.case_id}: query changed")
        if list(case.labels.expected_files) != list(task["expected_files"]):
            problems.append(f"{case.case_id}: expected_files changed")
        if case.category != task["category"]:
            problems.append(f"{case.case_id}: category changed")
        if case.rationale != task["rationale"]:
            problems.append(f"{case.case_id}: rationale changed")
        baseline = case.exact_search_baseline
        if baseline is None or baseline.ripgrep_baseline != task["ripgrep_baseline"]:
            problems.append(f"{case.case_id}: ripgrep_baseline changed")
    assert not problems, "\n".join(problems)


def test_rescued_cases_record_the_artifact_they_came_from() -> None:
    corpus = _load()
    by_id = {case.case_id: case for case in corpus.cases}
    expected_origin = str(ARCHIVED_EVAL_SET.relative_to(REPO_ROOT))
    problems: list[str] = []
    for task in _archived_tasks():
        case = by_id.get(task["id"])
        if case is None:
            continue  # reported by the identifier test
        if case.provenance is None:
            problems.append(f"{case.case_id}: no provenance block")
        elif case.provenance.rescued_from != expected_origin:
            problems.append(
                f"{case.case_id}: rescued_from is {case.provenance.rescued_from}, "
                f"expected {expected_origin}"
            )
    assert not problems, "\n".join(problems)
