"""The Enablement Consistency Gate, proven by mutation rather than by observation.

Every other check in this change fails on an unmodified tree. This one does not,
and deliberately: its job is to catch a flip nobody has made, so making it red
today would mean making `main` red for a condition nobody caused. "It fails
today" is therefore unavailable as evidence that the gate works, and this file is
the substitute.

Each test constructs the tree state the gate exists to reject — the default
declared `True`, against evidence that is absent, stale by exactly one of design
decision D12's six expiry conditions, failing, or schema-invalid — and asserts a
non-zero exit that *names the condition*. Two controls sit beside them and are
what make the rejections mean anything:

- `test_a_current_passing_report_authorizes_an_enabled_default` — with every
  condition satisfied the gate exits `0`. Without this, a gate hardcoded to
  reject every enabled default would pass all the mutations below and the file
  would prove nothing.
- `test_disabling_the_default_restores_a_rejected_tree_to_passing` — the spec's
  remedy. Expiry withdraws authorization; it does not create a state with no way
  out.

The mutants are driven off one prepared, fully-authorizing report so that each
one differs from an accepted tree in exactly one respect. A mutant that failed
for two reasons would not tell you the condition under test is live.

**Two families of mutant, and the second exists because the first was not
enough.** The provenance mutants perturb where the report came FROM — its
corpus digest, its harness identity, its embedder, its indexed revision. Every
one of them was watched failing, and the gate still authorized an enabled
default from a report that measured nothing: a hand-written document carrying
the current digest, the current harness version, a matching fingerprint, a
reachable revision and `verdict: "pass"`, with `gates: []`, `per_consumer: []`,
`cases: []` and `cases_declared: 0`, was accepted as schema-valid and printed
seven met conditions on its way to exit `0`. Nothing here perturbed what the
report SAID, so nothing here was ever going to catch it. The content mutants at
the foot of this file close that, against both layers: the report contract's
`minItems`, which makes the empty body unwritable, and
`report_describes_corpus`, which re-derives the declared denominator from the
file on disk rather than trusting the emitter to have been its last author.

Without this file the gate is decoration. Weakening any assertion here is
therefore a change to what the gate means, not a change to a test.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
RESPONSES = CORPUS_ROOT / "responses"
SEMANTIC_CONTEXT = REPO_ROOT / "skills" / "context-engineering" / "scripts" / "semantic_context.py"
HARNESS_SOURCE = SRC / "context_eval"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval import enablement_gate  # noqa: E402
from context_eval import report as report_module  # noqa: E402
from context_eval.__main__ import (  # noqa: E402
    EXIT_GATE_FAILURE,
    EXIT_PASS,
    EXIT_REPORT_UNUSABLE,
)
from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, Corpus  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402
from context_eval.verdict import CaseOutcome, MeasurementContext, compose_verdict  # noqa: E402

CONTRACT_PROVIDER_KIND = "local"
REPO_SLUG = "agentic_coding_tools"

#: The declaration as ri-12's helper ships it. Asserted rather than assumed: if
#: the constant is ever reshaped, the flip below would silently stop flipping
#: anything and every mutant would test a disabled default.
DECLARATION_OFF = f"{enablement_gate.DEFAULT_CONSTANT}: bool = False"
DECLARATION_ON = f"{enablement_gate.DEFAULT_CONSTANT}: bool = True"


def _head_revision() -> str:
    """The revision the mutants' reports claim to have been measured at."""
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


HEAD = _head_revision()

#: A syntactically valid revision no repository contains.
UNREACHABLE_REVISION = hashlib.sha256(b"no such commit").hexdigest()[:40]

#: A fingerprint that is not the one the report recorded. Derived, never a model
#: identifier: the harness forbids those as literals anywhere.
OTHER_FINGERPRINT = hashlib.sha256(b"a differently configured embedder").hexdigest()


# --------------------------------------------------------------------------
# building the evidence
#
# These four helpers are deliberately a copy of the ones in
# `test_cli_exit_codes.py` rather than a shared import. Sharing them would mean
# either importing another test module's privates or adding a package-level
# conftest, and this work package's write scope covers neither. The duplication
# is small, and each copy is pinned to the corpus and the composer rather than to
# the other copy.
# --------------------------------------------------------------------------


def _semantic_arm(case: Case) -> Arm:
    spans = tuple(
        RenderedHit(span.file_path, span.start_line, span.end_line)
        for span in case.labels.evidence_spans
    )
    expectation = case.expectation
    if expectation is None:
        return Arm(arm="semantic", status="injected", hits=spans)
    if expectation.status == "fallback":
        return fallback_arm("semantic", str(expectation.trigger), str(expectation.reason))
    wanted = expectation.rendered_hits or len(spans)
    return Arm(
        arm="semantic",
        status="injected",
        hits=tuple(spans[index % len(spans)] for index in range(wanted)),
    )


def _measurement(**overrides: Any) -> MeasurementContext:
    fields: dict[str, Any] = {
        "index_tier": "live",
        "code_search_enabled": True,
        "semantic_context_injection": True,
        "coordination_transport": "http",
        "scope_adapter": "resolved",
    }
    fields.update(overrides)
    return MeasurementContext(**fields)


def _document(corpus: Corpus, measurement: MeasurementContext) -> dict[str, Any]:
    outcomes = [
        CaseOutcome(
            case_id=case.case_id,
            consumer=case.consumer,
            scored=True,
            semantic=_semantic_arm(case),
            baseline=fallback_arm("baseline", "no_context", "index_returned_no_hits"),
            request_body=(
                None
                if not case.scope.read_allow
                else {
                    "scope": {
                        "kind": "explicit",
                        "read_allow": list(case.scope.read_allow),
                        "deny": list(case.scope.deny),
                    }
                }
            ),
        )
        for case in corpus.cases
    ]
    composed = compose_verdict(corpus, outcomes, measurement)
    response = json.loads((RESPONSES / "adv-leaked-hit.json").read_text(encoding="utf-8"))
    document = report_module.build_report(
        corpus=corpus,
        composed=composed,
        measurement=measurement,
        harness=report_module.harness_identity(corpus),
        repository=report_module.RepositoryIdentity(repo_slug=REPO_SLUG, evaluated_revision=HEAD),
        index=report_module.index_identity_from_response(
            response,
            tier=measurement.index_tier,
            contract={"provider_kind": CONTRACT_PROVIDER_KIND},
        ),
    )
    # The recorded response is a fixture and names a fixture revision. The gate's
    # reachability condition is about the tree under test, so the prepared
    # evidence claims the revision this checkout is actually at — otherwise every
    # mutant below would fail for that reason as well as its own.
    document["index"]["indexed_revision"] = HEAD
    report_module.validate_report(document)
    return document


@dataclass(frozen=True)
class Evidence:
    """One prepared report per outcome the gate has to tell apart."""

    passing: dict[str, Any]
    failing: dict[str, Any]
    apparatus: dict[str, Any]


@pytest.fixture(scope="module")
def evidence() -> Evidence:
    corpus = load_corpus(CORPUS_ROOT)
    passing = _document(corpus, _measurement())
    assert passing["verdict"] == "pass", (
        "the prepared evidence does not authorize anything, so no mutation of it "
        "could demonstrate the gate rejecting a single condition"
    )
    failing = _document(corpus, _measurement(index_tier="none"))
    assert failing["verdict"] == "fail"
    apparatus = _document(corpus, _measurement(scope_adapter="degraded"))
    assert "apparatus_failure" in apparatus["fail_reasons"]
    return Evidence(passing=passing, failing=failing, apparatus=apparatus)


# --------------------------------------------------------------------------
# building the tree state
# --------------------------------------------------------------------------


def _helper_with_default(tmp_path: Path, *, enabled: bool) -> Path:
    """ri-12's real helper, copied, with only the default declaration changed."""
    source = SEMANTIC_CONTEXT.read_text(encoding="utf-8")
    assert source.count(DECLARATION_OFF) == 1, (
        f"{SEMANTIC_CONTEXT} no longer declares {enablement_gate.DEFAULT_CONSTANT} "
        f"as `{DECLARATION_OFF}`; this file would be flipping nothing"
    )
    if enabled:
        source = source.replace(DECLARATION_OFF, DECLARATION_ON)
    tmp_path.mkdir(parents=True, exist_ok=True)
    destination = tmp_path / "semantic_context.py"
    destination.write_text(source, encoding="utf-8")
    return destination


def _contract(tmp_path: Path, fingerprint: str) -> Path:
    """The configured embedding contract, as the gate reads it."""
    path = tmp_path / "embedding-contract.json"
    path.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
    return path


def _argv(
    *,
    helper: Path,
    report_path: Path,
    corpus: Path = CORPUS_ROOT,
    contract: Path | None = None,
    harness_source: Path | None = None,
) -> list[str]:
    argv = [
        "--repository-root",
        str(REPO_ROOT),
        "--semantic-context",
        str(helper),
        "--report",
        str(report_path),
        "--corpus",
        str(corpus),
    ]
    if contract is not None:
        argv += ["--embedding-contract", str(contract)]
    if harness_source is not None:
        argv += ["--harness-source", str(harness_source)]
    return argv


def _recorded_fingerprint(document: dict[str, Any]) -> str:
    return str(document["index"]["embedder"]["fingerprint"])


def _authorizing(tmp_path: Path, evidence: Evidence) -> list[str]:
    """Every condition satisfied. Each mutant below is this, minus one thing."""
    document = deepcopy(evidence.passing)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


# --------------------------------------------------------------------------
# the mutations, one per condition
# --------------------------------------------------------------------------

Mutation = Callable[[Path, Evidence], list[str]]


def _no_report(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(a) Nothing was ever measured. The state of this tree today."""
    document = deepcopy(evidence.passing)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=tmp_path / "report.json",  # never written
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


def _schema_invalid_report(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(d) It claims to pass, and it is not a report.

    Written raw, because `write_report` validates before it opens the file — an
    invalid report can only reach the durable path past the emitter.
    """
    document = deepcopy(evidence.passing)
    fingerprint = _recorded_fingerprint(document)
    del document["index"]
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(document), encoding="utf-8")
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, fingerprint),
    )


def _failing_report(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(c) It was measured, it is current, and it says no."""
    document = deepcopy(evidence.failing)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


def _moved_corpus(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.1) A case or a threshold changed, so the digest moved."""
    document = deepcopy(evidence.passing)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS_ROOT, copied)
    manifest = copied / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n# a threshold argument someone had\n",
        encoding="utf-8",
    )
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        corpus=copied,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


def _other_harness_version(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.2) The software that measured this is not the software here."""
    document = deepcopy(evidence.passing)
    document["harness"]["version"] = f"{document['harness']['version']}+not-this-one"
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


def _changed_fingerprint(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.3) The embedder was reconfigured after the measurement."""
    document = deepcopy(evidence.passing)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, OTHER_FINGERPRINT),
    )


def _unreachable_revision(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.4) The measurement describes a tree this one does not descend from."""
    document = deepcopy(evidence.passing)
    document["index"]["indexed_revision"] = UNREACHABLE_REVISION
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


def _harness_source_copy(tmp_path: Path, *, modified: bool) -> Path:
    """A copy of the harness's own source, optionally with one file changed.

    A copy rather than the real tree: mutating `src/` in place during a test run
    would have the suite measuring a harness that no longer exists on disk by the
    time it finishes, and a same-second restore can leave the mutant's bytecode
    behind where `inspect.getsource` will not show it. The digest is over
    corpus-relative paths and file bytes, so an unmodified copy digests
    identically to the original — which is what makes the modified one a
    single-variable mutation.
    """
    destination = tmp_path / ("mutated-src" if modified else "pristine-src")
    shutil.copytree(
        HARNESS_SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    if modified:
        target = destination / "scoring" / "relevance.py"
        assert target.is_file(), "the mutated file must be one the harness actually scores with"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# a scorer somebody changed\n",
            encoding="utf-8",
        )
    return destination


def _changed_harness_source(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.2b) The code that measured this is not the code here, whatever it is called.

    The mutation is a real edit to a real scorer, not a rewritten field in the
    report. `harness.version` would be untouched by such an edit — that is the
    entire defect this condition exists to close — so a mutant that rewrote the
    recorded digest instead would prove only that string comparison works.
    """
    document = deepcopy(evidence.passing)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
        harness_source=_harness_source_copy(tmp_path, modified=True),
    )


def _report_omitting_a_declared_gate(tmp_path: Path, evidence: Evidence) -> list[str]:
    """(b.5) Current, schema-valid, passing — and silent about a declared gate.

    The smallest mutation that reaches `report_describes_corpus` without also
    tripping the schema: three of four gates is a perfectly legal array, and the
    corpus is what says a fourth was owed. Written through `write_report`, which
    is the point — this document is one the emitter would accept.
    """
    document = deepcopy(evidence.passing)
    document["gates"] = document["gates"][1:]
    report_path = report_module.write_report(tmp_path / "report.json", document)
    return _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )


#: Condition, mutation, and the exit code the gate owes it. The code matters:
#: "we have no usable evidence" (3) and "we measured and it failed" (2) are
#: different facts with different remedies, and the July 2026 waiver is what
#: collapsing them looks like.
MUTATIONS: tuple[tuple[str, Mutation, int], ...] = (
    (enablement_gate.REPORT_PRESENT, _no_report, EXIT_REPORT_UNUSABLE),
    (enablement_gate.SCHEMA_VALID, _schema_invalid_report, EXIT_REPORT_UNUSABLE),
    (enablement_gate.CORPUS_DIGEST_CURRENT, _moved_corpus, EXIT_REPORT_UNUSABLE),
    (enablement_gate.HARNESS_VERSION_CURRENT, _other_harness_version, EXIT_REPORT_UNUSABLE),
    (enablement_gate.HARNESS_FINGERPRINT_CURRENT, _changed_harness_source, EXIT_REPORT_UNUSABLE),
    (enablement_gate.EMBEDDER_FINGERPRINT_CURRENT, _changed_fingerprint, EXIT_REPORT_UNUSABLE),
    (enablement_gate.INDEXED_REVISION_REACHABLE, _unreachable_revision, EXIT_REPORT_UNUSABLE),
    (
        enablement_gate.REPORT_DESCRIBES_CORPUS,
        _report_omitting_a_declared_gate,
        EXIT_REPORT_UNUSABLE,
    ),
    (enablement_gate.VERDICT_PASS, _failing_report, EXIT_GATE_FAILURE),
)


# --------------------------------------------------------------------------
# controls — without these the mutations prove nothing
# --------------------------------------------------------------------------


def test_the_gate_reads_the_declaration_ri12_actually_ships() -> None:
    assert enablement_gate.declared_default(SEMANTIC_CONTEXT) is False


def test_a_current_passing_report_authorizes_an_enabled_default(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control that makes every rejection below meaningful.

    A gate that rejected every enabled default would satisfy all seven mutations
    and be worthless. This asserts the other side: with the corpus, the harness,
    the embedder, the revision, the schema and the verdict all in agreement, an
    enabled default is authorized.
    """
    assert enablement_gate.main(_authorizing(tmp_path, evidence)) == EXIT_PASS
    assert not capsys.readouterr().err


def test_a_disabled_default_needs_no_evidence(tmp_path: Path) -> None:
    """The state of this tree, and the reason the gate is green on it."""
    helper = _helper_with_default(tmp_path, enabled=False)
    argv = _argv(helper=helper, report_path=tmp_path / "absent.json")
    assert enablement_gate.main(argv) == EXIT_PASS


def test_disabling_the_default_restores_a_rejected_tree_to_passing(
    tmp_path: Path, evidence: Evidence
) -> None:
    """Expiry withdraws authorization; it does not create a state with no remedy."""
    rejected = _no_report(tmp_path, evidence)
    assert enablement_gate.main(rejected) != EXIT_PASS

    restored = list(rejected)
    restored[restored.index("--semantic-context") + 1] = str(
        _helper_with_default(tmp_path / "off", enabled=False)
    )
    assert enablement_gate.main(restored) == EXIT_PASS


# --------------------------------------------------------------------------
# the mutations
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("condition", "mutation", "expected_exit"),
    MUTATIONS,
    ids=[condition for condition, _, _ in MUTATIONS],
)
def test_an_enabled_default_is_rejected_and_the_condition_is_named(
    condition: str,
    mutation: Mutation,
    expected_exit: int,
    tmp_path: Path,
    evidence: Evidence,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = enablement_gate.main(mutation(tmp_path, evidence))
    stderr = capsys.readouterr().err

    assert exit_code != EXIT_PASS, f"{condition} did not stop enablement"
    assert exit_code == expected_exit
    assert condition in stderr, (
        f"the gate rejected the tree without naming {condition}; "
        f"an unexplained failure is a gate people learn to route around:\n{stderr}"
    )
    assert "unmet condition" in stderr
    assert enablement_gate.DEFAULT_CONSTANT in stderr


def test_an_unverifiable_embedding_fingerprint_is_unmet_not_skipped(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """No configured contract means no comparison, and no comparison means no match.

    The alternative — passing the condition when there is nothing to check it
    against — would make the one expiry condition that needs an external input
    the one an operator can switch off by omission.
    """
    argv = _authorizing(tmp_path, evidence)
    del argv[argv.index("--embedding-contract") : argv.index("--embedding-contract") + 2]

    assert enablement_gate.main(argv) == EXIT_REPORT_UNUSABLE
    assert enablement_gate.EMBEDDER_FINGERPRINT_CURRENT in capsys.readouterr().err


def test_a_recorded_apparatus_failure_does_not_authorize_enablement(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """"Could not measure" is a `fail` with a reason, and it authorizes nothing."""
    document = deepcopy(evidence.apparatus)
    report_path = report_module.write_report(tmp_path / "report.json", document)
    argv = _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )
    assert enablement_gate.main(argv) == EXIT_GATE_FAILURE
    assert enablement_gate.VERDICT_PASS in capsys.readouterr().err


# --------------------------------------------------------------------------
# the mutation set itself
# --------------------------------------------------------------------------


def test_every_condition_the_gate_declares_is_mutated() -> None:
    """A condition dropped from the gate, or added without a mutant, is caught here.

    The gate's own condition list is design decision D12's six expiry conditions
    plus the base case they reduce to. If one of them stopped being checked, the
    parametrization above would still be green — nothing else in the suite would
    notice, because the gate is green on this tree either way.
    """
    mutated = {condition for condition, _, _ in MUTATIONS}
    assert mutated == set(enablement_gate.CONDITIONS)
    assert len(enablement_gate.EXPIRY_CONDITIONS) == len(set(enablement_gate.EXPIRY_CONDITIONS))
    assert set(enablement_gate.EXPIRY_CONDITIONS) < mutated


# --------------------------------------------------------------------------
# content mutations — what the report SAYS, not where it came from
#
# Reproduced against the pre-fix gate before any of this was written: all six
# documents below were accepted by `write_report` as schema-valid AND authorized
# an enabled default, `enablement_gate.main() -> 0`, with seven conditions
# printed as met. They are separated into two groups because the two layers fail
# independently and each needs its own witness: the schema does not run on a file
# somebody edited by hand, and the gate does not run on a file nobody committed.
# --------------------------------------------------------------------------

BodyMutation = Callable[[dict[str, Any]], None]


def _empty_body(document: dict[str, Any]) -> None:
    """The review's exact reproduction: current provenance, nothing measured."""
    document["gates"] = []
    document["per_consumer"] = []
    document["cases"] = []
    document["corpus"]["cases_declared"] = 0
    document["corpus"]["cases_scored"] = 0
    document["corpus"]["gates_declared"] = 0
    document["corpus"]["consumers_declared"] = 0


def _no_gates(document: dict[str, Any]) -> None:
    document["gates"] = []


def _no_cases(document: dict[str, Any]) -> None:
    document["cases"] = []


def _no_consumers(document: dict[str, Any]) -> None:
    document["per_consumer"] = []


def _no_cases_declared(document: dict[str, Any]) -> None:
    document["corpus"]["cases_declared"] = 0


#: Bodies the report contract itself refuses, so they never reach a durable path.
UNWRITABLE_BODIES: tuple[tuple[str, BodyMutation], ...] = (
    ("an empty body", _empty_body),
    ("no gates", _no_gates),
    ("no cases", _no_cases),
    ("no consumers", _no_consumers),
    ("nothing declared", _no_cases_declared),
)


def _omit_a_gate(document: dict[str, Any]) -> None:
    document["gates"] = document["gates"][1:]


def _omit_a_consumer(document: dict[str, Any]) -> None:
    document["per_consumer"] = document["per_consumer"][1:]


def _omit_a_case(document: dict[str, Any]) -> None:
    document["cases"] = document["cases"][1:]


def _overstate_cases_scored(document: dict[str, Any]) -> None:
    """A denominator claim nothing in the body backs."""
    document["corpus"]["cases_scored"] = 0


#: Bodies the schema cannot fault — every array is non-empty and every count is
#: positive — and which describe a corpus other than the declared one.
MISDESCRIBING_BODIES: tuple[tuple[str, BodyMutation], ...] = (
    ("a declared gate omitted", _omit_a_gate),
    ("a declared consumer omitted", _omit_a_consumer),
    ("a declared case omitted", _omit_a_case),
    ("a cases_scored count nothing backs", _overstate_cases_scored),
)


def _raw_report(tmp_path: Path, document: dict[str, Any]) -> Path:
    """Write past the emitter, because a hand-edited file takes no other route."""
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("label", "mutation"),
    UNWRITABLE_BODIES,
    ids=[label for label, _ in UNWRITABLE_BODIES],
)
def test_a_report_that_measured_nothing_is_unwritable(
    label: str, mutation: BodyMutation, tmp_path: Path, evidence: Evidence
) -> None:
    """Layer one: the empty body cannot reach the durable path at all.

    `write_report` validates before it opens the file, so the assertion is that
    the document never becomes a file — not that it is written and then
    complained about. `GateResult` already forbids a gate that passed while
    measuring nothing; this is the same prohibition one level up, where the
    report itself is what measured nothing.
    """
    document = deepcopy(evidence.passing)
    mutation(document)

    destination = tmp_path / "report.json"
    with pytest.raises(report_module.ReportError):
        report_module.write_report(destination, document)
    assert not destination.exists(), f"{label} reached the durable path"


@pytest.mark.parametrize(
    ("label", "mutation"),
    UNWRITABLE_BODIES,
    ids=[label for label, _ in UNWRITABLE_BODIES],
)
def test_an_unwritable_body_written_by_hand_is_still_rejected(
    label: str,
    mutation: BodyMutation,
    tmp_path: Path,
    evidence: Evidence,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Layer one, from the side that matters: the schema is also read at gate time.

    The emitter refusing to write it is not enough on its own. The gate reads a
    file, and a file can be edited by something that is not the emitter.
    """
    document = deepcopy(evidence.passing)
    mutation(document)
    argv = _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=_raw_report(tmp_path, document),
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )

    assert enablement_gate.main(argv) == EXIT_REPORT_UNUSABLE, f"{label} authorized enablement"
    assert enablement_gate.SCHEMA_VALID in capsys.readouterr().err


@pytest.mark.parametrize(
    ("label", "mutation"),
    MISDESCRIBING_BODIES,
    ids=[label for label, _ in MISDESCRIBING_BODIES],
)
def test_a_schema_valid_report_that_misdescribes_the_corpus_is_rejected(
    label: str,
    mutation: BodyMutation,
    tmp_path: Path,
    evidence: Evidence,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Layer two: every count is positive, every array non-empty, and it still lies.

    `minItems` cannot express "as many gates as the corpus declares" — that is a
    comparison between two documents, and a schema sees one at a time. These
    mutants are written through `write_report`, so each is a document the emitter
    itself would accept; only the corpus says what is missing.
    """
    document = deepcopy(evidence.passing)
    mutation(document)
    report_module.validate_report(document)  # the schema has no complaint

    report_path = report_module.write_report(tmp_path / "report.json", document)
    argv = _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_path,
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )

    assert enablement_gate.main(argv) == EXIT_REPORT_UNUSABLE, f"{label} authorized enablement"
    stderr = capsys.readouterr().err
    assert enablement_gate.REPORT_DESCRIBES_CORPUS in stderr, (
        f"the gate rejected {label} without naming the condition:\n{stderr}"
    )


def test_the_hollow_report_the_gate_used_to_authorize(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """The finding itself, as one test, end to end.

    A report carrying the CURRENT corpus digest, the CURRENT harness version, a
    matching embedder fingerprint, a reachable indexed revision and
    `verdict: "pass"` — with `gates: []`, `per_consumer: []`, `cases: []` and
    `cases_declared: 0`. Before this change the emitter accepted it and the gate
    printed seven met conditions and returned `0` against an enabled default:
    green because the evidence was empty, not because it was good. It is the same
    category of error as the July 2026 spike report's automated check
    (`'Verdict' in t and 'hit@5' in t`), which passed the very document it
    existed to block.
    """
    document = deepcopy(evidence.passing)
    _empty_body(document)

    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "emitted.json", document)

    argv = _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=_raw_report(tmp_path, document),
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
    )
    assert enablement_gate.main(argv) != EXIT_PASS
    assert "unmet condition" in capsys.readouterr().err


def test_an_unmodified_copy_of_the_harness_source_still_authorizes(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the harness-fingerprint mutant, and the reason it means anything.

    A digest that varied with where the source happened to sit would reject every
    tree, and the mutant above would be watching a tautology rather than a
    condition. The fingerprint is over relative paths and file bytes, so a
    verbatim copy digests identically — which makes the appended comment in
    `_changed_harness_source` the only variable between the two.
    """
    document = deepcopy(evidence.passing)
    pristine = _harness_source_copy(tmp_path, modified=False)
    assert report_module.harness_fingerprint(pristine) == document["harness"]["fingerprint"]

    argv = _argv(
        helper=_helper_with_default(tmp_path, enabled=True),
        report_path=report_module.write_report(tmp_path / "report.json", document),
        contract=_contract(tmp_path, _recorded_fingerprint(document)),
        harness_source=pristine,
    )
    assert enablement_gate.main(argv) == EXIT_PASS
    assert not capsys.readouterr().err


def test_a_changed_scorer_moves_the_harness_fingerprint(tmp_path: Path) -> None:
    """The property the condition rests on, asserted directly.

    `harness.version` is unchanged by every edit below — that is the defect. The
    digest is not.
    """
    pristine = _harness_source_copy(tmp_path, modified=False)
    mutated = _harness_source_copy(tmp_path, modified=True)
    assert report_module.harness_fingerprint(pristine) != report_module.harness_fingerprint(mutated)
    assert report_module.harness_fingerprint(pristine) == report_module.harness_fingerprint(
        HARNESS_SOURCE
    ), "the digest varies with location, so it identifies a path rather than a harness"


def test_the_authorizing_report_accounts_for_the_whole_corpus(evidence: Evidence) -> None:
    """The control for the two tests above, and the reason they mean anything.

    A condition that rejected every report would satisfy every content mutant
    here and would also reject the one report that should be accepted. The
    prepared evidence carries a result for every declared case, gate and
    consumer, and `test_a_current_passing_report_authorizes_an_enabled_default`
    is what proves the gate takes it.
    """
    corpus = load_corpus(CORPUS_ROOT)
    document = evidence.passing
    assert len(document["cases"]) == len(corpus.cases)
    assert document["corpus"]["cases_declared"] == len(corpus.cases)
    assert {gate["id"] for gate in document["gates"]} == {gate.id for gate in corpus.gates}
    assert {entry["consumer"] for entry in document["per_consumer"]} == {
        slice_.consumer for slice_ in corpus.consumers
    }


def test_no_rejection_is_silent(
    tmp_path: Path, evidence: Evidence, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every rejection explains itself, in one sweep over every mutant.

    A separate assertion from the parametrized one above, pointed at a different
    failure. That test names the condition it expects, so it would keep passing
    if the gate only ever printed *that* id. This one asks the weaker but broader
    question — did anything at all get explained — for every mutation, so
    deleting the reason from any single failure path is caught here even when the
    condition under test is not the one whose message was removed.
    """
    unexplained: list[str] = []
    for index, (condition, mutation, _) in enumerate(MUTATIONS):
        stream = tmp_path / str(index)
        stream.mkdir()
        assert enablement_gate.main(mutation(stream, evidence)) != EXIT_PASS
        stderr = capsys.readouterr().err
        if not any(declared in stderr for declared in enablement_gate.CONDITIONS):
            unexplained.append(f"{condition}: {stderr!r}")
    assert not unexplained, "rejections with no named condition:\n" + "\n".join(unexplained)
