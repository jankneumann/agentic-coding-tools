"""Build, validate, and write the one artifact that may authorize enablement.

Three rules govern this module, and each is a mechanism rather than a habit.

**Schema-validated on write.** :func:`write_report` validates before it opens
the file, so an invalid report is never written — not written-then-checked, not
written with a warning. The report is the only document that can authorize
enabling semantic context injection by default, and a document that does not
satisfy its contract must not exist at the durable path at all. A run whose
report cannot be written is an apparatus failure, which the CLI reports as such.

**The judge is attached after composition.** :func:`build_report` has no judge
parameter, exactly as ``compose_verdict()`` has none, and this module imports
nothing from :mod:`context_eval.judge`. Attaching a review is
:func:`attach_judge`, which takes an opaque mapping and can only add a key to a
document whose ``verdict`` already exists (design D15).

**Embedder identity is derived, never written.** :func:`embedder_from_contract`
reads the configured ``EmbeddingContract`` and
:func:`index_identity_from_response` reads ``CodeSearchResponse.index``. No
model identifier appears in this file, or anywhere else in the harness, and a
test asserts it (design D6). Identity that a harness can assert is identity a
harness can be wrong about.

The per-arm numbers a report carries are computed here by calling phase 3's
scorers — the same functions the gates were judged with. Recomputing them with a
second implementation would let the report and the verdict disagree about the
same run, which is the one contradiction a reader has no way to resolve.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .loader import DEFAULT_SCHEMA_DIR
from .models import Budget, Case, Corpus
from .scoring import relevance, scope, utility
from .scoring.arms import Arm
from .verdict import (
    DEGRADED,
    INDEX_TIERS,
    LIVE_TIER,
    CaseOutcome,
    ComposedVerdict,
    MeasurementContext,
)

REPORT_SCHEMA_NAME = "context-eval-report.schema.json"
DEFAULT_REPORT_SCHEMA = DEFAULT_SCHEMA_DIR / REPORT_SCHEMA_NAME

#: The report shape this module writes. Pinned so a consumer that has not been
#: taught a later shape refuses the document rather than misreading it.
SCHEMA_VERSION = 1

HARNESS_NAME = "context-eval"

PASS = "pass"
FAIL = "fail"

#: The report is indented so a diff between two runs is readable. A STRING
#: rather than a count, because ``test_thresholds_are_not_readable_from_the_
#: scoring_modules`` forbids every declared threshold value as a numeric literal
#: anywhere under ``src/`` and one of them happens to be 2. That check cannot
#: distinguish a formatting width from a gate bound, and it is right not to try:
#: the version that guessed would be the version that missed a real one.
JSON_INDENT = "  "

#: ``packages/context-eval``, by named parents rather than by index — the
#: positional form is what made the archived evaluation unreproducible.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent

#: The harness's own source tree, which :func:`harness_fingerprint` digests.
SOURCE_ROOT = Path(__file__).resolve().parent

_DIGEST_FIELD_SEPARATOR = "\x00"
_DIGEST_RECORD_SEPARATOR = "\n"

#: What the harness IS. The digest covers files with this suffix and nothing
#: else, exactly as the corpus digest covers corpus files: an identity that moved
#: for anything that happened to be sitting in the directory would produce false
#: EXPIRIES, and a gate that sends an operator to re-run a full evaluation
#: because macOS Finder wrote a `.DS_Store` is a gate people learn to route
#: around. Bytecode is excluded by construction rather than by a rule — a
#: `.cpython-312.pyc` is not a `.py` — and so are coverage reports, editor swap
#: files, and everything else nobody wrote.
#:
#: The cost is that a non-Python file the harness READ would be invisible to its
#: own identity. There is none today, and
#: ``test_the_harness_source_holds_nothing_the_digest_would_miss`` fails the day
#: one arrives, so the decision is forced rather than silently taken.
_SOURCE_SUFFIX = ".py"


class ReportError(Exception):
    """The report cannot be built or is not valid against its contract."""


# ---------------------------------------------------------------------------
# provenance, all of it read from somewhere rather than written here
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Embedder:
    """The embedding configuration that produced the serving index."""

    provider_kind: str
    model_id: str
    dimension: int
    fingerprint: str
    policy_fingerprint: str | None = None
    pipeline_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "provider_kind": self.provider_kind,
            "model_id": self.model_id,
            "dimension": self.dimension,
            "fingerprint": self.fingerprint,
        }
        if self.policy_fingerprint:
            document["policy_fingerprint"] = self.policy_fingerprint
        if self.pipeline_fingerprint:
            document["pipeline_fingerprint"] = self.pipeline_fingerprint
        return document


@dataclass(frozen=True)
class IndexIdentity:
    """Which index answered, and what it was built by."""

    tier: str
    indexed_revision: str | None
    namespace_kind: str
    namespace_key: str
    embedder: Embedder
    index_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "tier": self.tier,
            "indexed_revision": self.indexed_revision,
            "namespace_kind": self.namespace_kind,
            "namespace_key": self.namespace_key,
            "embedder": self.embedder.to_dict(),
        }
        if self.index_id:
            document["index_id"] = self.index_id
        return document


@dataclass(frozen=True)
class Harness:
    """What produced this report, and against which corpus.

    ``version`` is a string a person writes into ``pyproject.toml``.
    ``fingerprint`` is a digest of the source that actually ran. Both are
    recorded because they answer different questions, and the second exists
    because the first was the one expiry condition an operator could satisfy by
    assertion: a behavioural change to the measuring code left the declared
    version untouched, so a report the harness no longer reproduces went on
    counting as current evidence. Identity a harness can assert is identity a
    harness can be wrong about — the same rule this module already applies to the
    embedder (design D6), applied to the harness itself.
    """

    name: str
    version: str
    corpus_digest: str
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "corpus_digest": self.corpus_digest,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class RepositoryIdentity:
    """The tree the measurement was taken over."""

    repo_slug: str
    evaluated_revision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_slug": self.repo_slug,
            "evaluated_revision": self.evaluated_revision,
        }


def _attribute(source: object, name: str) -> Any:
    """Read *name* from an object or a mapping, without knowing which it is.

    The embedding contract is a dataclass in one caller and a decoded JSON body
    in another, and the report must not care: what matters is that the value came
    from the configuration, not from this file.
    """
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def _agree(name: str, configured: Any, served: Any) -> Any:
    """One value from two witnesses, or an error saying they disagree.

    A report whose configured embedder differs from the one that answered is
    describing two different indexes at once, and there is no honest way to pick
    a winner: the measurement was taken through the second and the expiry check
    will be made against the first.
    """
    if configured is None:
        return served
    if served is None:
        return configured
    if str(configured) != str(served):
        raise ReportError(
            f"the configured embedding contract and the index that answered disagree "
            f"about {name}: {configured!r} vs {served!r}"
        )
    return served


def embedder_identity(contract: object, index: Mapping[str, Any]) -> Embedder:
    """Embedder identity from the configured contract AND the index that answered.

    Both witnesses, because neither is sufficient alone. ``EmbeddingProviderKind``
    exists only in the contract — the wire's index block never carries it — while
    the model, dimension and fingerprints of the index that actually served are
    only knowable from the response. Where both speak, they must agree.

    Every field is *derived*. A missing one is an error rather than a default: a
    report that invented an embedder identity would compare equal to a real one
    at expiry time, and the enablement gate would accept evidence about an index
    nobody built (design D12).
    """
    provider_kind = _enum_value(_attribute(contract, "provider_kind"))
    model_id = _agree("model_id", _attribute(contract, "model_id"), index.get("embedder_model"))
    dimension = _agree("dimension", _attribute(contract, "dimension"), index.get("embedding_dim"))
    fingerprint = _agree(
        "fingerprint",
        _attribute(contract, "fingerprint"),
        index.get("embedder_fingerprint"),
    )

    missing = [
        name
        for name, value in (
            ("provider_kind", provider_kind),
            ("model_id", model_id),
            ("dimension", dimension),
            ("fingerprint", fingerprint),
        )
        if value is None
    ]
    if missing:
        raise ReportError(f"the embedding configuration declares no {missing!r}")

    return Embedder(
        provider_kind=str(provider_kind),
        model_id=str(model_id),
        dimension=int(dimension),
        fingerprint=str(fingerprint),
        policy_fingerprint=_optional_str(
            index.get("policy_fingerprint") or _attribute(contract, "policy_fingerprint")
        ),
        pipeline_fingerprint=_optional_str(
            index.get("pipeline_fingerprint") or _attribute(contract, "pipeline_fingerprint")
        ),
    )


def embedder_from_contract(contract: object) -> Embedder:
    """The configured contract alone, when no index answered to cross-check it."""
    return embedder_identity(contract, {})


def index_identity_from_response(
    response: Mapping[str, Any], *, tier: str, contract: object
) -> IndexIdentity:
    """Read which index answered from ``CodeSearchResponse.index``.

    The response is the only witness to what actually served. Taking the index's
    identity from the run's own configuration instead would record what the
    harness intended to query rather than what answered it — which is why the
    contract is here too, and only to supply the provider kind the wire has no
    field for and to be checked against what came back.
    """
    index = response.get("index")
    if not isinstance(index, Mapping):
        raise ReportError("the response carries no index block to read identity from")

    namespace = index.get("namespace")
    if not isinstance(namespace, Mapping):
        raise ReportError("the response's index block carries no namespace")

    return IndexIdentity(
        tier=tier,
        indexed_revision=_optional_str(index.get("source_revision")),
        namespace_kind=str(namespace.get("kind")),
        namespace_key=str(namespace.get("key")),
        embedder=embedder_identity(contract, index),
        index_id=_optional_str(index.get("index_id")),
    )


def _enum_value(value: Any) -> Any:
    """``EmbeddingProviderKind.LOCAL`` -> ``"local"``, and a string unchanged."""
    inner = getattr(value, "value", None)
    return inner if isinstance(inner, str) else value


def harness_identity(
    corpus: Corpus,
    *,
    version: str | None = None,
    fingerprint: str | None = None,
) -> Harness:
    """Name the harness and the corpus a report was produced against."""
    return Harness(
        name=HARNESS_NAME,
        version=version if version is not None else installed_version(),
        corpus_digest=corpus.digest,
        fingerprint=fingerprint if fingerprint is not None else harness_fingerprint(),
    )


def harness_fingerprint(source_root: Path | str | None = None) -> str:
    """A digest over the harness's own source, keyed by relative path and sorted.

    The same construction ``loader._digest`` uses for the corpus, and for the
    same reason. The corpus digest exists because an operator who edits a
    threshold must invalidate every report judged against the old one; this
    exists because an operator who edits a *scorer* must invalidate every report
    the new scorer would no longer produce. Until it did, the harness-expiry
    check compared a version string nobody is obliged to change, and a fix to the
    measuring code left its own stale evidence looking current — which is exactly
    how a committed report that HEAD could no longer reproduce went undetected.

    Bytes rather than parsed content, exactly as the corpus digest does:
    reformatting moves the digest, which is conservative in the only direction
    that is safe. Only ``*.py`` is covered, because the digest must move for
    every change to the harness and for nothing else: bytecode is derived from
    sources already hashed, and a `.DS_Store` or a coverage report changes no
    behaviour while producing a false expiry — the failure mode that teaches
    people to route around a gate. Nothing here reads a clock, a random source,
    or an unordered set, so two processes agree.

    Args:
        source_root: The tree to digest. Injected rather than discovered so the
            gate can be pointed at a mutated copy and watched rejecting it —
            a condition nobody has seen fire is a condition nobody has tested.
    """
    root = Path(source_root) if source_root is not None else SOURCE_ROOT
    if not root.is_dir():
        raise ReportError(f"the harness source is not a directory: {root}")
    files = _source_files(root)
    if not files:
        raise ReportError(f"the harness source at {root} holds no files to fingerprint")
    records = sorted(
        _DIGEST_FIELD_SEPARATOR.join(
            (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        )
        for path in files
    )
    stream = _DIGEST_RECORD_SEPARATOR.join(records)
    return hashlib.sha256(stream.encode("utf-8")).hexdigest()


def _source_files(root: Path) -> Iterable[Path]:
    return [path for path in root.rglob(f"*{_SOURCE_SUFFIX}") if path.is_file()]


def installed_version() -> str:
    """The harness version, from package metadata or from its own manifest.

    Both readings describe the software that ran. A literal here would keep
    claiming a version the tree no longer has, and the enablement gate compares
    this value against the installed harness to decide whether the evidence has
    expired.
    """
    try:
        from importlib.metadata import version

        return version(HARNESS_NAME)
    except Exception:  # noqa: BLE001 - an uninstalled package is the normal case here
        pass

    import tomllib

    manifest = PACKAGE_ROOT / "pyproject.toml"
    try:
        declared = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["version"]
    except Exception as error:  # noqa: BLE001
        raise ReportError(f"the harness version is unreadable from {manifest}") from error
    return str(declared)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


# ---------------------------------------------------------------------------
# per-case arm results
# ---------------------------------------------------------------------------


def _arm_result(case: Case, arm: Arm, budget: Budget, k: int) -> dict[str, Any]:
    """One arm's measurements, in the report contract's shape.

    The scorers are the phase 3 ones, called rather than reimplemented. Where a
    case carries no label for a measure — every fail-closed case labels no
    expected files, no required files and no evidence spans — the measure takes
    the value its own definition gives an arm that delivered nothing: no top-k
    hit, no coverage, no density, and the censored read cost. That is not a skip:
    the case IS scored, and it contributes those values to every mean it belongs
    to.
    """
    labels = case.labels
    return {
        "rendered_files": list(arm.rendered_files),
        "rendered_lines": arm.rendered_lines,
        "hit_at_k": (
            relevance.hit_at_k(arm, labels.expected_files, k) if labels.expected_files else False
        ),
        "answer_coverage": (
            utility.answer_coverage(arm, labels.must_touch) if labels.must_touch else 0.0
        ),
        "evidence_density": (
            utility.evidence_density(arm, labels.evidence_spans)
            if labels.evidence_spans
            else 0.0
        ),
        "steps_to_evidence": (
            utility.steps_to_evidence(arm, labels.evidence_spans, budget)
            if labels.evidence_spans
            else budget.max_files + 1
        ),
        "scope_violations": list(scope.scope_violations(arm, case.scope)),
    }


def _semantic_arm_result(case: Case, arm: Arm, budget: Budget, k: int) -> dict[str, Any]:
    document = _arm_result(case, arm, budget, k)
    document["status"] = arm.status
    if arm.fallback_trigger is not None:
        document["fallback_trigger"] = arm.fallback_trigger
    if arm.fallback_reason is not None:
        document["fallback_reason"] = arm.fallback_reason
    return document


def _case_result(case: Case, outcome: CaseOutcome, corpus: Corpus) -> dict[str, Any]:
    document: dict[str, Any] = {
        "case_id": outcome.case_id,
        "consumer": outcome.consumer,
        "scored": outcome.scored,
    }
    if not outcome.scored:
        document["unscored_reason"] = outcome.unscored_reason
        return document

    semantic = outcome.semantic
    baseline = outcome.baseline
    if semantic is None or baseline is None:  # pragma: no cover - CaseOutcome forbids it
        raise ReportError(f"{outcome.case_id} is scored without both arms")

    arms: dict[str, Any] = {
        "semantic": _semantic_arm_result(case, semantic, corpus.budget, corpus.k),
        "baseline": _arm_result(case, baseline, corpus.budget, corpus.k),
    }
    if outcome.naive_phrase is not None:
        arms["naive_phrase"] = _arm_result(case, outcome.naive_phrase, corpus.budget, corpus.k)
    document["arms"] = arms
    return document


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------


def build_report(
    *,
    corpus: Corpus,
    composed: ComposedVerdict,
    measurement: MeasurementContext,
    harness: Harness,
    repository: RepositoryIdentity,
    index: IndexIdentity,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Assemble the report document. Keyword-only, and with no judge parameter.

    Args:
        corpus: The declaration the run was measured against.
        composed: What ``compose_verdict()`` returned. The verdict arrives here
            already decided; nothing in this function can change it.
        measurement: The conditions the run was taken under.
        harness: Name, version, corpus digest.
        repository: The evaluated tree.
        index: Which index answered and what built it.
        as_of: The evaluation's single timestamp, supplied as an explicit input
            and recorded verbatim. Nothing in the harness reads a clock and
            nothing branches on this value (design D16).
    """
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verdict": composed.verdict,
        "harness": harness.to_dict(),
        "repository": repository.to_dict(),
        "index": index.to_dict(),
        "environment": {
            "code_search_enabled": measurement.code_search_enabled,
            "semantic_context_injection": measurement.semantic_context_injection,
            "coordination_transport": measurement.coordination_transport,
            "scope_adapter": measurement.scope_adapter,
        },
        "budget": {
            "max_hits": corpus.budget.max_hits,
            "max_files": corpus.budget.max_files,
            "max_total_lines": corpus.budget.max_total_lines,
            "max_hit_lines": corpus.budget.max_hit_lines,
        },
        "corpus": {
            "corpus_id": corpus.corpus_id,
            "k": corpus.k,
            "cases_declared": composed.cases_declared,
            "cases_scored": composed.cases_scored,
            "gates_declared": len(corpus.gates),
            "consumers_declared": len(corpus.consumers),
        },
        "gates": [_gate_result(gate) for gate in composed.gates],
        "per_consumer": [_consumer_result(entry) for entry in composed.per_consumer],
        "cases": _case_results(corpus, composed.cases),
    }
    if composed.verdict == FAIL:
        document["fail_reasons"] = list(composed.fail_reasons)
    if as_of is not None:
        document["as_of"] = as_of
    return document


def _case_results(corpus: Corpus, outcomes: Sequence[CaseOutcome]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for outcome in outcomes:
        try:
            case = corpus.case_by_id(outcome.case_id)
        except KeyError as error:
            # A result for a case the corpus never declared. The composer has
            # already failed the run for it; the report still has to be writable
            # so the evidence of the mismatch survives.
            raise ReportError(f"{outcome.case_id} is not a declared case") from error
        results.append(_case_result(case, outcome, corpus))
    return results


def _gate_result(gate: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": gate.id,
        "kind": gate.kind,
        "required": gate.required,
        "min_index_tier": gate.min_index_tier,
        "verdict": gate.verdict,
        "thresholds": dict(gate.thresholds),
        "measured": dict(gate.measured),
    }
    if gate.fail_reasons:
        document["fail_reasons"] = list(gate.fail_reasons)
    return document


def _consumer_result(entry: utility.ConsumerUtility) -> dict[str, Any]:
    document: dict[str, Any] = {
        "consumer": entry.consumer,
        "utility_applicable": entry.utility_applicable,
        "cases_declared": entry.cases_declared,
        "cases_scored": entry.cases_scored,
        "verdict": entry.verdict,
    }
    if entry.utility_not_applicable_reason:
        document["utility_not_applicable_reason"] = entry.utility_not_applicable_reason.strip()
    if entry.metrics is not None:
        document["metrics"] = dict(entry.metrics)
    if entry.fail_reasons:
        document["fail_reasons"] = list(entry.fail_reasons)
    return document


def attach_judge(document: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    """Attach an advisory review to a report that already has a verdict.

    Refuses to attach to a document with no verdict, which is the executable
    form of "after composition, never before". The review is an opaque mapping:
    this module never reads a field of it, so there is no value it could carry
    that this function could act on.
    """
    if "verdict" not in document:
        raise ReportError("a review may only be attached to a report that already has a verdict")
    attached = dict(document)
    attached["judge"] = dict(review)
    return attached


# ---------------------------------------------------------------------------
# the document agreeing with itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BodyConsistency:
    """Whether a report's conclusion follows from the body it carries.

    ``compose_verdict()`` returns ``pass`` only when every declared case was
    scored, every declared gate produced a passing result and every precondition
    held — but it guarantees that about a value in memory, and every consumer
    re-reads an editable file from disk. A guarantee that does not travel with
    the artifact is not a guarantee about the artifact, so the invariant is
    re-derived here from the only document a gate ever actually reads.

    The derivation is deliberately ONE-WAY. ``derived == "fail"`` while the
    document records ``pass`` is a contradiction: no run that produced this body
    could have composed that conclusion. The converse is not — and the reason has
    to be stated exactly, because the approximate version of it was a hole.

    EXACTLY ONE of ``compose_verdict()``'s reasons is CORPUS-RELATIVE, and it is
    the whole justification for one-wayness: the undeclared-case half of
    :data:`verdict.DENOMINATOR_MISMATCH`. ``_aligned`` strips an outcome the
    corpus never declared *before* ``build_report`` runs, so the document that
    reaches disk has nothing visibly wrong — every count agrees, every row is
    scored, and the body derives ``pass`` over a run the composer correctly
    failed. Refusing that document would make the outcome unreportable, so the
    derivation must permit ``derived == "pass"`` under a recorded ``fail``.

    Note what this paragraph does NOT say. It does not claim the enablement
    gate's ``report_describes_corpus`` catches this case — that claim was here
    for one round and was false. ``_describes_corpus_condition`` compares the
    document against the manifest, and the stripped outcome is absent from both.
    Nothing catches it, which is precisely why one-wayness is required rather
    than merely convenient.

    Every OTHER input the composer decides on is in this document, and every one
    is re-derived below: the gate rows and the consumer rows, the scored flags,
    all three declared counts against both the rows they describe and the scored
    total, ``index.tier`` against each gate's ``min_index_tier`` — and the
    ``environment`` block, whose ``scope_adapter`` and ``code_search_enabled``
    are the composer's :data:`verdict.APPARATUS_FAILURE` and
    :data:`verdict.SERVICE_DISABLED_DURING_MEASUREMENT`.

    :data:`verdict.MISSING_REQUIRED_GATE` belongs to that second list, not the
    first. It was described here as corpus-relative for one round, and it is not:
    ``build_report`` writes ``corpus.gates_declared`` from the corpus and one row
    per composed gate, both schema-required, so "a declared gate produced no row"
    is ``len(gates) != corpus.gates_declared`` — two fields already in the file.

    Twice now a reason was called underivable when the derivation had simply not
    been written — first the degraded scope adapter, then the missing gate. Both
    were schema-required fields sitting in the document. The lesson is in the
    shape of the mistake: "the composer reads it from the manifest" is a fact
    about the composer, not about the report, and the two are only the same
    question when nobody checks.
    """

    derived_verdict: str
    recorded_verdict: str | None
    #: Every way the document disagrees with itself, each naming what disagreed.
    contradictions: tuple[str, ...]
    #: Every failure the BODY records, whether or not the conclusion admits it.
    body_failures: tuple[str, ...]

    @property
    def consistent(self) -> bool:
        return not self.contradictions


def _rows(document: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = document.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _tier_satisfies(tier: Any, declared: Any) -> bool:
    """Does the index that answered reach the tier a gate says it needs?

    An ordered comparison over :data:`INDEX_TIERS`, exactly as
    ``MeasurementContext.satisfies`` makes it — the same list, so a fourth tier
    is one edit rather than a truth table somebody has to remember to extend.
    This is also why the comparison is not mirrored into the report schema: JSON
    Schema has no ordering over an enum, so expressing it there means writing out
    the tier pairs by hand, and a new tier would leave the hand-written table
    silently valid while comparing against nothing.
    """
    if tier not in INDEX_TIERS or declared not in INDEX_TIERS:
        # An unreadable tier cannot be shown to satisfy anything, and a gate that
        # passed against one is a gate nobody can check.
        return False
    return INDEX_TIERS.index(tier) >= INDEX_TIERS.index(declared)


def body_consistency(document: Mapping[str, Any]) -> BodyConsistency:
    """Re-derive the verdict from the body, and say where the two disagree.

    Every input is already in the report; nothing here reads the corpus, the
    harness, or the disk. That is the point — this asks the one question the nine
    conditions around it never asked, which is whether the document agrees with
    itself.
    """
    failures: list[str] = []
    contradictions: list[str] = []

    tier = (document.get("index") or {}).get("tier")
    environment = document.get("environment") or {}
    gates = _rows(document, "gates")

    # The two run-level preconditions, derived first because that is where
    # ``compose_verdict`` applies them: a measurement taken in the wrong state
    # measured something other than what it claims, whatever every row says. Both
    # fields are schema-required, so a schema-valid document always answers both
    # questions, and neither answer needs anything outside the file.
    if environment.get("scope_adapter") == DEGRADED:
        failures.append(
            f"it was measured through a {DEGRADED} scope adapter, which fails the "
            "run whatever the numbers say"
        )
    if environment.get("code_search_enabled") is not True and any(
        gate.get("min_index_tier") == LIVE_TIER for gate in gates
    ):
        # The sibling of the ``_tier_satisfies`` comparison below, and read from
        # the same field: ``_compose_gate`` appends ``index_tier_insufficient``
        # and ``service_disabled_during_measurement`` on adjacent lines, and for
        # one round only the first of the two was re-derived here.
        failures.append(
            "the code-search service was disabled while gates declaring a "
            f"{LIVE_TIER!r} index were measured"
        )

    for gate in gates:
        identifier = gate.get("id")
        verdict = gate.get("verdict")
        if verdict == FAIL and gate.get("required") is not False:
            reasons = ", ".join(str(reason) for reason in gate.get("fail_reasons") or ())
            failures.append(
                f"required gate {identifier!r} is recorded as a failure"
                + (f" ({reasons})" if reasons else "")
            )
        elif verdict == PASS:
            if gate.get("fail_reasons"):
                contradictions.append(
                    f"gate {identifier!r} is recorded as a pass and names "
                    f"fail_reasons {list(gate['fail_reasons'])!r}"
                )
            declared = gate.get("min_index_tier")
            if not _tier_satisfies(tier, declared):
                contradictions.append(
                    f"gate {identifier!r} is recorded as a pass at index tier "
                    f"{tier!r} while declaring it needs {declared!r}"
                )

    for entry in _rows(document, "per_consumer"):
        name = entry.get("consumer")
        if entry.get("verdict") == FAIL:
            failures.append(f"consumer {name!r} is recorded as a failure")
        elif entry.get("verdict") == PASS and entry.get("fail_reasons"):
            contradictions.append(
                f"consumer {name!r} is recorded as a pass and names "
                f"fail_reasons {list(entry['fail_reasons'])!r}"
            )

    unscored = [
        row.get("case_id")
        for row in _rows(document, "cases")
        if row.get("scored") is not True
    ]
    if unscored:
        failures.append(f"{len(unscored)} declared cases carry no measurement: {unscored!r}")

    counts = document.get("corpus") or {}

    # A declared row that produced no entry. ``compose_verdict`` learns this from
    # the manifest (:data:`verdict.MISSING_REQUIRED_GATE`), which is why it was
    # once described here as corpus-relative and underivable — but the document
    # already carries both halves of the comparison. ``build_report`` writes each
    # ``*_declared`` count from the corpus and one row per composed entry, and all
    # three counts are schema-required, so a schema-valid document always answers
    # this without the manifest.
    #
    # It also closes ONE of the two ways the live-tier premise above could be
    # edited away. Dropping every gate row that declares a live index used to
    # delete the premise along with the rows; the row counts now catch that. The
    # other way is not closed and cannot be, from this document: rewriting a
    # gate's `min_index_tier` from "live" to a lower tier defeats the premise
    # while every count still agrees. The declared tier lives in the manifest, so
    # only a corpus-relative check can see the rewrite, and the enablement gate's
    # `report_describes_corpus` does not compare it today. Stated rather than
    # claimed closed — asserting a closure nobody established is the mistake this
    # very block exists to correct.
    for key, rows, noun in (
        ("gates_declared", gates, "gate"),
        ("consumers_declared", _rows(document, "per_consumer"), "consumer"),
        ("cases_declared", _rows(document, "cases"), "case"),
    ):
        declared_rows = counts.get(key)
        if isinstance(declared_rows, int) and len(rows) != declared_rows:
            failures.append(
                f"it carries {len(rows)} {noun} rows against the "
                f"{declared_rows} it declares"
            )

    declared_cases = counts.get("cases_declared")
    scored_cases = counts.get("cases_scored")
    if isinstance(declared_cases, int) and isinstance(scored_cases, int):
        if scored_cases != declared_cases:
            failures.append(
                f"it scored {scored_cases} of the {declared_cases} cases it declares"
            )

    recorded = document.get("verdict")
    derived = FAIL if failures else PASS
    if derived == FAIL and recorded == PASS:
        contradictions.append(
            "it records verdict 'pass' over a body that records failure: "
            + "; ".join(failures)
        )

    return BodyConsistency(
        derived_verdict=derived,
        recorded_verdict=recorded if isinstance(recorded, str) else None,
        contradictions=tuple(contradictions),
        body_failures=tuple(failures),
    )


# ---------------------------------------------------------------------------
# validation and writing
# ---------------------------------------------------------------------------


def report_validator(schema_path: Path | str | None = None) -> Draft202012Validator:
    """A validator over the promoted report contract.

    The promoted copy, never the change-local authoring copy: that one moves when
    the change is archived, and a validator that followed it would stop working
    on exactly the day the report most needs to still be checkable.
    """
    path = Path(schema_path) if schema_path is not None else DEFAULT_REPORT_SCHEMA
    if not path.is_file():
        raise ReportError(f"the promoted report schema is missing: {path}")
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def validate_report(
    document: Mapping[str, Any], *, schema_path: Path | str | None = None
) -> None:
    """Raise :class:`ReportError` unless *document* satisfies the contract."""
    validator = report_validator(schema_path)
    errors = sorted(validator.iter_errors(dict(document)), key=lambda err: list(err.absolute_path))
    if errors:
        detail = "; ".join(f"{list(err.absolute_path)}: {err.message}" for err in errors)
        raise ReportError(f"report does not satisfy {REPORT_SCHEMA_NAME}: {detail}")


def write_report(
    path: Path | str,
    document: Mapping[str, Any],
    *,
    schema_path: Path | str | None = None,
) -> Path:
    """Validate, then write. An invalid report never reaches the disk.

    Not written-then-checked: the durable path is what a gate reads, and a
    document that does not satisfy its contract must not be there at all, not
    even briefly and not even accompanied by a warning nobody reads.
    """
    validate_report(document, schema_path=schema_path)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=JSON_INDENT, sort_keys=False) + "\n", encoding="utf-8"
    )
    return destination


def read_report(path: Path | str) -> dict[str, Any]:
    """Read a report from disk. A missing or unparseable file is an error."""
    source = Path(path)
    if not source.is_file():
        raise ReportError(f"no report at {source}")
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReportError(f"report at {source} is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ReportError(f"report at {source} is not an object")
    return document
