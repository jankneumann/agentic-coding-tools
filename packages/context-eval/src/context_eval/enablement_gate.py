"""The Enablement Consistency Gate: a declared default, and the evidence for it.

One question, asked at build time and nowhere else: **is the injection default
this tree declares authorized by the evidence this tree carries?**

    0  authorized, or nothing is claimed (the default is disabled)
    1  apparatus failure — the gate could not read what it needed to decide
    2  the evidence is current and schema-valid, and its verdict is not a pass
    3  the evidence is absent or has expired

**This gate adds nothing at runtime, deliberately.** ri-12 already fails closed
per request: ``STATE_FALLBACKS`` maps every non-ready service state to an
explicit exact-search fallback, ``UNKNOWN_STATE_FALLBACK`` makes that mapping
total over states nobody has invented yet, and ``collect_semantic_context``
returns a fallback rather than raising. A second runtime path that re-disabled
injection from a report's contents would be a second authority for one decision,
which is exactly what design decision D12 rejects. What ri-12 *cannot* notice is
that the justification for the default has gone stale — a corpus that moved, a
threshold someone edited, an embedder that was swapped, an index built from a
revision this tree does not descend from. That is the whole of this module's
job, and it is a comparison between two committed artifacts.

**It short-circuits when the default is disabled, and that is the mechanism.**
D12 reads "any of these ⇒ the gate requires ``INJECTION_DEFAULT_ENABLED`` is
``False``", and the spec's expiry scenario says disabling the default restores
the check to passing. So a disabled default claims nothing, needs no evidence,
and passes. The corollary is that this gate is correctly green on a tree where
nobody enabled anything, and cannot be watched failing there — which is why
``tests/test_enablement_gate_mutation.py`` exists and why it is not optional.

**A failure always names the condition.** "Enablement not authorized" with no
reason is a gate people learn to route around; every unmet condition is printed
with its id and the values that disagreed.

**Identity is derived, not asserted — including the harness's own.** The report
records both the harness's declared ``version`` and a digest of the harness's
*source*, and this gate compares both. The declared version was the one expiry
condition an operator could satisfy by writing a number down: a fix to a scorer
leaves ``pyproject.toml`` untouched, so a report the harness demonstrably no
longer reproduces kept counting as current evidence. A content digest makes a
behavioural change to the measuring code invalidate its own evidence, which is
what D12 says it wants and what the corpus digest has always done for the corpus.

**Neither half is nameable from the command line, and that is deliberate.** The
first version of the digest fix shipped ``--harness-version`` and
``--harness-source`` beside each other, which handed back exactly the property it
had just taken away: a report naming a mutated source tree and a version nobody
has expires under CI's invocation and authorizes under an invocation carrying
both flags. Two overrides that together reconstitute an identity are one
override. ``harness_source`` survives as a keyword-only argument of
:func:`evaluate` and :func:`main` — reachable from a test, which is what lets the
condition be watched rejecting a modified copy, and not reachable from an
operator, which is the whole of the guarantee.

**Provenance is not evidence.** D12's six conditions all ask whether the report
is *current*; none of them asked whether it is *about anything*. A hand-written
document carrying the right digest, the right harness identity, a matching
embedder fingerprint, a reachable indexed revision and ``verdict: "pass"``, with
``gates: []``, ``per_consumer: []``, ``cases: []`` and ``cases_declared: 0``, was
accepted as schema-valid and printed seven met conditions on its way to exit 0 —
the same category of error as the waived spike report whose automated check was
``'Verdict' in t and 'hit@5' in t``. :data:`REPORT_DESCRIBES_CORPUS` re-derives
the declared denominator from the artifact rather than trusting that the emitter
was the last thing to touch it, and the report contract now sets ``minItems`` on
``gates``, ``per_consumer`` and ``cases`` so the empty body is unwritable at all.
Two layers, because they fail independently: the schema does not run on a file
somebody edited by hand, and the gate does not run on a file nobody committed.

**And a conclusion is not evidence either.** The same error survived that fix
one layer further in. Every condition above interrogates what surrounds the
report's conclusion — where it came from, whether it accounts for the declared
corpus — and the conclusion itself stayed a string this gate read. A three-field
edit of the committed report (``verdict`` ``fail`` to ``pass``, ``fail_reasons``
deleted, ``indexed_revision`` filled in) printed nine met conditions and returned
``0`` while the same file recorded two required gates failing at
``index.tier: "none"`` against a declared ``min_index_tier: "live"``, five of six
consumers failing, and seven of nineteen cases scored. ``compose_verdict()``
cannot produce such a document — which is exactly why a text editor can.
:data:`VERDICT_CONSISTENT` re-derives the composer's pass invariant from the body
through :func:`report.body_consistency`, and the report contract now refuses a
passing verdict over a failing gate. The same helper is the one
``context_eval.__main__.check`` calls, because a second implementation of "does
this document agree with itself" would eventually answer differently from this
one and no reader would know which answer governed.

**What none of this detects, stated plainly so nobody has to discover it.** A
report whose numbers were invented rather than measured — every declared case
``scored`` with fabricated arms, every gate passing with fabricated ``measured``
values, every consumer passing with fabricated metrics, at tier ``live`` and a
reachable revision — is schema-valid, self-consistent, and **authorizes**. It was
built by hand and watched exiting ``0`` here. Every condition in this module
compares the artifact against something else that is also in the repository: the
corpus, the harness source, git, a supplied contract. Someone who can edit the
report can compute all of those, so no condition of that shape can ever
distinguish a measurement from a claim about one.

The conditions still buy something real, and it is worth being precise about
what. They raise the cost from *editing three fields of a committed failure* to
*forging an entire coherent measurement*, and — more usefully — they make honest
drift impossible to mistake for evidence, which is the failure that actually
happens: a corpus that moved, a scorer that changed, an index built from a
revision this tree does not descend from. Deliberate forgery is not what a build
gate can close. The only construction that would is the gate re-running the
harness over the report's own recorded inputs and comparing the composed document
to the committed one; that is a different change, and it needs the exact-search
baseline pinned to ``repository.evaluated_revision`` first, because today the
baseline arm reads the working tree.

The declared default is read by parsing the source, not by importing it. Two
reasons, and the second is the load-bearing one: importing would run ri-12's
module in the gate's process for a single boolean, and parsing lets the gate
require that the constant is assigned **exactly once**, at module level, from a
literal. The spec asks for "a single machine-readable declaration"; a default
that could be reassigned in a branch, or computed from an environment lookup,
would be back to being inferred rather than declared.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import report
from .__main__ import EXIT_APPARATUS, EXIT_GATE_FAILURE, EXIT_PASS, EXIT_REPORT_UNUSABLE
from .loader import CorpusError, load_corpus
from .models import Corpus

#: The one declaration the whole gate reads (design D11).
DEFAULT_CONSTANT = "INJECTION_DEFAULT_ENABLED"

#: Locations relative to the repository root. Defaults, never discovery: each is
#: overridable on the command line, and the root itself is always supplied.
SEMANTIC_CONTEXT_RELATIVE = Path("skills/context-engineering/scripts/semantic_context.py")
REPORT_RELATIVE = Path("docs/evaluation/semantic-context/report.json")
CORPUS_RELATIVE = Path("packages/context-eval/corpus")

PASS_VERDICT = "pass"

#: A git probe must not be able to hang a build.
GIT_TIMEOUT_SECONDS = 15

#: Design D12's expiry conditions, in the order D12 states them. Any one of them
#: renders the evidence absent, and absent evidence authorizes nothing.
CORPUS_DIGEST_CURRENT = "corpus_digest_current"
HARNESS_VERSION_CURRENT = "harness_version_current"
EMBEDDER_FINGERPRINT_CURRENT = "embedder_fingerprint_current"

#: The content half of "is this the software that measured it?", and the reason
#: the declared-version half is not enough on its own. ``harness.version`` is a
#: string somebody writes into ``pyproject.toml``: it is the only D12 condition
#: an operator can satisfy by assertion, and a fix to a scorer leaves it
#: untouched, so a report the harness demonstrably no longer reproduces went on
#: counting as current evidence. This compares a digest of the harness's own
#: source, exactly as ``corpus_digest_current`` compares a digest of the corpus.
HARNESS_FINGERPRINT_CURRENT = "harness_fingerprint_current"
INDEXED_REVISION_REACHABLE = "indexed_revision_reachable"
SCHEMA_VALID = "schema_valid"
VERDICT_PASS = "verdict_pass"

#: Not one of D12's original six either, and the narrowest statement of the
#: defect this gate keeps re-learning: the field that authorizes was the one
#: field nothing derived. ``verdict_pass`` reads ``document["verdict"]``, and
#: :data:`REPORT_DESCRIBES_CORPUS` re-derives only the DENOMINATOR — the counts,
#: the case ids, the gate ids, the consumer names. A document may therefore
#: account for the whole declared corpus and still contradict its own conclusion.
#: This condition re-derives the OUTCOME: ``compose_verdict()`` returns ``pass``
#: only when every declared case was scored, every required gate passed and every
#: precondition held, so a report recording ``pass`` over rows that record
#: failure describes a run that cannot have happened.
VERDICT_CONSISTENT = "verdict_consistent"

#: Not one of D12's original six, and added because those six were all
#: **provenance**. A hand-written document carrying the current corpus digest,
#: the current harness identity, a matching embedder fingerprint, a reachable
#: indexed revision and ``verdict: "pass"`` satisfied every one of them while
#: carrying ``gates: []``, ``per_consumer: []``, ``cases: []`` and
#: ``cases_declared: 0`` — and this gate printed seven met conditions and
#: returned 0. Provenance says the evidence is *current*; nothing in it says the
#: evidence is *about anything*.
REPORT_DESCRIBES_CORPUS = "report_describes_corpus"

EXPIRY_CONDITIONS: tuple[str, ...] = (
    CORPUS_DIGEST_CURRENT,
    HARNESS_VERSION_CURRENT,
    HARNESS_FINGERPRINT_CURRENT,
    EMBEDDER_FINGERPRINT_CURRENT,
    INDEXED_REVISION_REACHABLE,
    SCHEMA_VALID,
    REPORT_DESCRIBES_CORPUS,
    VERDICT_CONSISTENT,
    VERDICT_PASS,
)

#: The base case D12 does not number because it is the state the others reduce
#: to: there is no report at all.
REPORT_PRESENT = "report_present"

CONDITIONS: tuple[str, ...] = (REPORT_PRESENT, *EXPIRY_CONDITIONS)

#: Every condition except the verdict describes evidence that is missing rather
#: than evidence that speaks against enablement. The distinction is the same one
#: the CLI's exit codes draw, and it is the one the July 2026 waiver blurred:
#: "we have no measurement" and "we measured and it failed" are different facts.
#: A self-contradicting document is the first of those, not the second: nothing
#: composed it, so there is no measurement it reports.
EVIDENCE_ABSENT_CONDITIONS: tuple[str, ...] = tuple(
    condition for condition in CONDITIONS if condition != VERDICT_PASS
)


class EnablementGateError(Exception):
    """The gate could not read what it needs to decide. Never a verdict."""


@dataclass(frozen=True)
class Condition:
    """One expiry condition, and why it holds or does not."""

    condition: str
    met: bool
    detail: str

    def __str__(self) -> str:
        return f"{self.condition}: {self.detail}"


@dataclass(frozen=True)
class Outcome:
    """What the gate decided, and every condition it decided it from."""

    default_enabled: bool
    conditions: tuple[Condition, ...]

    @property
    def unmet(self) -> tuple[Condition, ...]:
        return tuple(condition for condition in self.conditions if not condition.met)

    @property
    def authorized(self) -> bool:
        """A disabled default claims nothing and is therefore always authorized."""
        return not self.default_enabled or not self.unmet

    @property
    def evidence_absent(self) -> bool:
        return any(condition.condition in EVIDENCE_ABSENT_CONDITIONS for condition in self.unmet)


# ---------------------------------------------------------------------------
# the declared default
# ---------------------------------------------------------------------------


def declared_default(module_path: Path) -> bool:
    """The value of :data:`DEFAULT_CONSTANT` in *module_path*, read by parsing.

    Requires exactly one module-level assignment from a literal ``bool``. A
    second assignment, an assignment inside a branch, or a value computed from
    anything at all is an error rather than a reading: the requirement is that
    the effective default is *one declaration*, and a gate that quietly took the
    last of several would let the declaration stop being the decision.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
    except OSError as error:
        raise EnablementGateError(f"cannot read the declared default from {module_path}") from error
    try:
        tree = ast.parse(source, filename=str(module_path))
    except SyntaxError as error:
        raise EnablementGateError(f"{module_path} does not parse: {error}") from error

    values: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if _names_the_constant(node.target) and node.value is not None:
                values.append(node.value)
        elif isinstance(node, ast.Assign):
            if any(_names_the_constant(target) for target in node.targets):
                values.append(node.value)

    nested = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and node not in tree.body
        and _assigns_the_constant(node)
    ]
    if nested:
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} is assigned somewhere other than module level in "
            f"{module_path} (line {nested[0].lineno}); the effective default must be "
            f"one declaration, not the outcome of a branch"
        )
    if len(values) != 1:
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} is declared {len(values)} times at module level in "
            f"{module_path}; exactly one declaration is required"
        )
    value = values[0]
    if not isinstance(value, ast.Constant) or not isinstance(value.value, bool):
        raise EnablementGateError(
            f"{DEFAULT_CONSTANT} in {module_path} is not a literal bool; a default "
            f"computed at import time is inferred rather than declared"
        )
    return value.value


def _names_the_constant(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == DEFAULT_CONSTANT


def _assigns_the_constant(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> bool:
    if isinstance(node, ast.Assign):
        return any(_names_the_constant(target) for target in node.targets)
    return _names_the_constant(node.target)


# ---------------------------------------------------------------------------
# the expiry conditions
# ---------------------------------------------------------------------------


def _verdict_condition(document: dict[str, Any]) -> Condition:
    verdict = document.get("verdict")
    if verdict == PASS_VERDICT:
        return Condition(VERDICT_PASS, True, "the recorded verdict is a pass")
    reasons = ", ".join(str(reason) for reason in document.get("fail_reasons", [])) or "none given"
    return Condition(
        VERDICT_PASS,
        False,
        f"the recorded verdict is {verdict!r} ({reasons}); it never authorized anything",
    )


def _consistent_verdict_condition(document: dict[str, Any]) -> Condition:
    """The report's conclusion follows from the report's own body.

    Re-derived rather than read, through the one helper
    ``context_eval.__main__.check`` also calls. Every other condition here is a
    comparison against something outside the document — the corpus on disk, the
    installed harness, the configured embedder, git. This one is entirely
    internal, and it is the only one that can notice a document nothing composed.

    One-way, deliberately: see :class:`report.BodyConsistency`, which enumerates
    what it derives and what it cannot. A recorded ``fail`` over a body with no
    visible failure is a legitimately composed report, because
    ``missing_required_gate`` and a case the corpus never declared are decided
    against the CORPUS and leave every row in the document intact; refusing such
    a report would make those outcomes unreportable, and
    :data:`REPORT_DESCRIBES_CORPUS` is the condition that catches them, because
    it is the one holding the corpus. A degraded scope adapter is not among them:
    the report records it, so the derivation reads it.
    """
    consistency = report.body_consistency(document)
    if consistency.consistent:
        return Condition(
            VERDICT_CONSISTENT,
            True,
            f"the recorded verdict {consistency.recorded_verdict!r} is the one this "
            f"body composes to",
        )
    return Condition(
        VERDICT_CONSISTENT,
        False,
        "the report contradicts itself, so nothing composed it: "
        + "; ".join(consistency.contradictions),
    )


def _load_corpus(corpus_root: Path) -> Corpus:
    """The declaration the report claims to describe. Loaded once, used twice.

    The digest condition needs it and so does
    :func:`_describes_corpus_condition`, and loading it twice would let the two
    conditions disagree about which corpus they were comparing against.
    """
    try:
        return load_corpus(corpus_root)
    except CorpusError as error:
        raise EnablementGateError(f"the corpus at {corpus_root} does not load: {error}") from error


def _corpus_digest_condition(document: dict[str, Any], corpus: Corpus) -> Condition:
    current = corpus.digest
    recorded = document.get("harness", {}).get("corpus_digest")
    if recorded == current:
        return Condition(CORPUS_DIGEST_CURRENT, True, f"the corpus digest is still {current}")
    return Condition(
        CORPUS_DIGEST_CURRENT,
        False,
        f"the report was judged against corpus {recorded}, and {corpus.root} now "
        f"digests to {current}: a case or a threshold changed",
    )


def _describes_corpus_condition(document: dict[str, Any], corpus: Corpus) -> Condition:
    """The report's BODY accounts for the corpus its provenance claims.

    Every other condition interrogates provenance or one verdict field, and all
    of them hold of a document that measured nothing: a digest and a version are
    copied in a text editor, and ``gates: []`` / ``per_consumer: []`` /
    ``cases: []`` is what an empty body looks like. ``compose_verdict()`` does
    guarantee the declared denominator — but it guarantees it about a value in
    memory, and this gate re-reads an editable file from disk. A guarantee that
    does not travel with the artifact is not a guarantee about the artifact, so
    it is re-derived here, against the only document a gate ever actually reads.

    Deliberately a comparison against the corpus rather than an internal
    consistency check. A report can be perfectly self-consistent about a corpus
    nobody declared.
    """
    declared_cases = tuple(case.case_id for case in corpus.cases)
    declared_gates = tuple(gate.id for gate in corpus.gates)
    declared_consumers = tuple(slice_.consumer for slice_ in corpus.consumers)

    counts = document.get("corpus", {})
    cases = document.get("cases", [])
    gates = document.get("gates", [])
    per_consumer = document.get("per_consumer", [])

    reported_cases = [str(entry.get("case_id")) for entry in cases]
    scored = sum(1 for entry in cases if entry.get("scored") is True)

    complaints: list[str] = []
    for label, recorded, expected in (
        ("cases_declared", counts.get("cases_declared"), len(declared_cases)),
        ("gates_declared", counts.get("gates_declared"), len(declared_gates)),
        ("consumers_declared", counts.get("consumers_declared"), len(declared_consumers)),
    ):
        if recorded != expected:
            complaints.append(f"it records {label}={recorded!r} and the corpus declares {expected}")

    absent_cases = [case_id for case_id in declared_cases if case_id not in set(reported_cases)]
    if absent_cases:
        complaints.append(f"it carries no result for declared cases {absent_cases}")
    if len(reported_cases) != len(declared_cases):
        complaints.append(
            f"it carries {len(reported_cases)} case results for "
            f"{len(declared_cases)} declared cases"
        )
    if scored != counts.get("cases_scored"):
        complaints.append(
            f"it claims cases_scored={counts.get('cases_scored')!r} while "
            f"{scored} of its case results are marked scored"
        )

    reported_gates = {str(entry.get("id")) for entry in gates}
    absent_gates = [gate_id for gate_id in declared_gates if gate_id not in reported_gates]
    if absent_gates:
        complaints.append(f"the corpus declares gates {absent_gates} that it does not report")

    reported_consumers = {str(entry.get("consumer")) for entry in per_consumer}
    absent_consumers = [name for name in declared_consumers if name not in reported_consumers]
    if absent_consumers:
        complaints.append(
            f"the corpus declares consumers {absent_consumers} that it does not report"
        )

    if complaints:
        return Condition(
            REPORT_DESCRIBES_CORPUS,
            False,
            "the report does not describe the corpus it names: " + "; ".join(complaints),
        )
    return Condition(
        REPORT_DESCRIBES_CORPUS,
        True,
        f"the report accounts for all {len(declared_cases)} declared cases, "
        f"{len(declared_gates)} gates and {len(declared_consumers)} consumers",
    )


def _harness_version_condition(document: dict[str, Any]) -> Condition:
    """The installed version, read from the package. Never supplied by a caller.

    There is no override parameter here at all, and the asymmetry with
    :func:`_harness_fingerprint_condition` is the point: a source tree can be
    copied and mutated, so pointing the digest at one is how the condition gets
    tested, while a version string can only be asserted, which is how the
    condition got defeated.
    """
    try:
        current = report.installed_version()
    except report.ReportError as error:
        raise EnablementGateError(str(error)) from error
    recorded = document.get("harness", {}).get("version")
    if recorded == current:
        return Condition(HARNESS_VERSION_CURRENT, True, f"the harness is still {current}")
    return Condition(
        HARNESS_VERSION_CURRENT,
        False,
        f"the report was produced by harness {recorded}, and the installed harness "
        f"is {current}: the software that measured this is not the software here",
    )


def _harness_fingerprint_condition(document: dict[str, Any], source_root: Path | None) -> Condition:
    try:
        current = report.harness_fingerprint(source_root)
    except report.ReportError as error:
        raise EnablementGateError(str(error)) from error
    recorded = document.get("harness", {}).get("fingerprint")
    if recorded == current:
        return Condition(
            HARNESS_FINGERPRINT_CURRENT, True, f"the harness source still digests to {current}"
        )
    return Condition(
        HARNESS_FINGERPRINT_CURRENT,
        False,
        f"the report was produced by harness source {recorded}, and the source here "
        f"digests to {current}: the code that measured this has changed, whatever "
        f"version it still calls itself",
    )


def _embedder_fingerprint_condition(
    document: dict[str, Any], contract_path: Path | None
) -> Condition:
    recorded = document.get("index", {}).get("embedder", {}).get("fingerprint")
    if contract_path is None:
        return Condition(
            EMBEDDER_FINGERPRINT_CURRENT,
            False,
            f"the report records embedder fingerprint {recorded}, and no configured "
            f"embedding contract was supplied (--embedding-contract) to compare it "
            f"against; an unchecked fingerprint is not a matching one",
        )
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EnablementGateError(
            f"the embedding contract at {contract_path} is unreadable: {error}"
        ) from error
    current = contract.get("fingerprint") if isinstance(contract, dict) else None
    if current is None:
        raise EnablementGateError(
            f"the embedding contract at {contract_path} declares no fingerprint"
        )
    if recorded == current:
        return Condition(
            EMBEDDER_FINGERPRINT_CURRENT, True, f"the embedding fingerprint is still {current}"
        )
    return Condition(
        EMBEDDER_FINGERPRINT_CURRENT,
        False,
        f"the report was measured through embedder {recorded}, and the configured "
        f"contract fingerprints to {current}: a matching model name alone does not "
        f"restore the evidence",
    )


def _indexed_revision_condition(document: dict[str, Any], repository_root: Path) -> Condition:
    revision = document.get("index", {}).get("indexed_revision")
    if not revision:
        return Condition(
            INDEXED_REVISION_REACHABLE,
            False,
            "the report records no indexed revision, so nothing ties the measurement "
            "to a tree this one descends from",
        )
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", revision, "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EnablementGateError(
            f"cannot ask git whether {revision} is reachable from {repository_root}: {error}"
        ) from error
    if completed.returncode == 0:
        return Condition(
            INDEXED_REVISION_REACHABLE, True, f"{revision} is an ancestor of the evaluated tree"
        )
    return Condition(
        INDEXED_REVISION_REACHABLE,
        False,
        f"{revision} is not reachable from HEAD in {repository_root}: the measurement "
        f"describes a tree this one does not descend from",
    )


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def evaluate(
    *,
    repository_root: Path,
    semantic_context: Path,
    report_path: Path,
    corpus_root: Path,
    embedding_contract: Path | None = None,
    harness_source: Path | None = None,
) -> Outcome:
    """Decide whether the declared default is authorized by the recorded evidence."""
    enabled = declared_default(semantic_context)
    if not enabled:
        return Outcome(default_enabled=False, conditions=())

    try:
        document = report.read_report(report_path)
    except report.ReportError as error:
        return Outcome(True, (Condition(REPORT_PRESENT, False, str(error)),))
    present = Condition(REPORT_PRESENT, True, f"a report is readable at {report_path}")

    try:
        report.validate_report(document)
    except report.ReportError as error:
        # Nothing below can be read from a document that is not a report: every
        # field the remaining conditions compare is a field the schema is what
        # guarantees the shape of.
        return Outcome(True, (present, Condition(SCHEMA_VALID, False, str(error))))
    valid = Condition(SCHEMA_VALID, True, "the report satisfies its published contract")

    corpus = _load_corpus(corpus_root)
    return Outcome(
        True,
        (
            present,
            valid,
            _corpus_digest_condition(document, corpus),
            _harness_version_condition(document),
            _harness_fingerprint_condition(document, harness_source),
            _embedder_fingerprint_condition(document, embedding_contract),
            _indexed_revision_condition(document, repository_root),
            _describes_corpus_condition(document, corpus),
            _consistent_verdict_condition(document),
            _verdict_condition(document),
        ),
    )


def main(argv: Sequence[str] | None = None, *, harness_source: Path | None = None) -> int:
    """Run the gate. Returns the process exit code.

    ``harness_source`` is keyword-only and has no command-line spelling. It is
    the seam that lets the fingerprint condition be pointed at a mutated copy of
    the harness and watched rejecting it; an operator reaching this function has
    a shell, not a Python call, and must not be able to name the tree their own
    evidence is compared against.
    """
    args = _parser().parse_args(list(argv) if argv is not None else None)
    root: Path = args.repository_root
    semantic_context: Path = args.semantic_context or root / SEMANTIC_CONTEXT_RELATIVE
    report_path: Path = args.report or root / REPORT_RELATIVE
    corpus_root: Path = args.corpus or root / CORPUS_RELATIVE

    try:
        outcome = evaluate(
            repository_root=root,
            semantic_context=semantic_context,
            report_path=report_path,
            corpus_root=corpus_root,
            embedding_contract=args.embedding_contract,
            harness_source=harness_source,
        )
    except EnablementGateError as error:
        print(f"apparatus failure: {error}", file=sys.stderr)
        return EXIT_APPARATUS

    if not outcome.default_enabled:
        print(
            f"{DEFAULT_CONSTANT} is False in {semantic_context}: semantic context "
            f"injection is off by default, so no evidence is required."
        )
        return EXIT_PASS

    if outcome.authorized:
        print(f"{DEFAULT_CONSTANT} is True, authorized by {report_path}:")
        for condition in outcome.conditions:
            print(f"  met: {condition}")
        return EXIT_PASS

    print(
        f"{DEFAULT_CONSTANT} is True in {semantic_context}, and the evidence at "
        f"{report_path} does not authorize it.",
        file=sys.stderr,
    )
    for condition in outcome.unmet:
        print(f"  unmet condition: {condition}", file=sys.stderr)
    print(
        "Enablement is authorized only by a current, schema-valid, passing report. "
        f"Either retake the measurement or restore {DEFAULT_CONSTANT} to False.",
        file=sys.stderr,
    )
    return EXIT_REPORT_UNUSABLE if outcome.evidence_absent else EXIT_GATE_FAILURE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-eval-enablement-gate",
        description=(
            "Check the declared semantic-context injection default against the "
            "evaluation report that authorizes it."
        ),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        required=True,
        help="The tree under test. Every other location defaults relative to it.",
    )
    parser.add_argument("--semantic-context", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument(
        "--embedding-contract",
        type=Path,
        default=None,
        help="JSON holding the configured EmbeddingContract. Without it the "
        "embedding fingerprint cannot be compared, which is an unmet condition.",
    )
    # Deliberately no --harness-version and no --harness-source. Both halves of
    # harness identity are derived here; a flag naming either one is an
    # assertion, and two of them together are an operator writing their own
    # provenance. The fingerprint's injection seam is `main(harness_source=...)`,
    # which a command line cannot reach.
    return parser


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
