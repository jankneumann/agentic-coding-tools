"""The report is validated on write, and its provenance is derived.

Three properties, and each of them is something the archived evaluation did not
have:

**A report that does not satisfy its contract is never written.** Not written
and flagged, not written with a warning — the durable path is what a gate reads,
so an invalid document must not be there at all. Every mutation below (a gate
declared optional, a missing index block, a missing corpus digest, a pass
carrying failure reasons) is asserted to be *unwritable*, which is the only form
of "cannot happen" that survives a hurried afternoon.

**Provenance is complete.** The tests named ``provenance`` assert the report
names the revision the serving index was built from, the full embedding
configuration that produced it, and the service state at measurement time.
``wp-measure`` runs exactly ``-k provenance`` against this file.

**Identity is derived, never asserted.** ``embedder_from_contract`` reads a
configured contract and ``index_identity_from_response`` reads the response's own
index block; no model identifier appears anywhere in the harness, and the last
test in this file holds the two new modules to that standard using the same
detector phase 3 wrote.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
RESPONSES = CORPUS_ROOT / "responses"
REPORT_SCHEMA = (
    REPO_ROOT
    / "openspec"
    / "contracts"
    / "semantic-context-evaluation"
    / "schemas"
    / "context-eval-report.schema.json"
)

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval import report as report_module  # noqa: E402
from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, Corpus  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402
from context_eval.verdict import CaseOutcome, MeasurementContext, compose_verdict  # noqa: E402

#: The modules this file holds to the no-model-literal rule. Phase 3's detector
#: covers ``producers/`` and ``scoring/``; these two are new surface where an
#: embedder identity could plausibly be typed by hand.
IDENTITY_MODULES = ("report.py", "verdict.py", "judge.py")

#: Copied from ``test_determinism.py``. Narrow and deliberately incomplete: a
#: tripwire for the obvious mistake, kept honest by its positive control.
MODEL_ID_PATTERNS = (
    re.compile(r"sentence-transformers/"),
    re.compile(r"\btext-embedding-"),
    re.compile(r"\ball-(?:MiniLM|mpnet)\b", re.IGNORECASE),
    re.compile(r"\b(?:bge|gte|e5|nomic-embed|voyage)-[a-z0-9]", re.IGNORECASE),
    re.compile(r"\b(?:gpt|claude|gemini|grok|kimi|llama|mistral)-[0-9]"),
)

EVALUATED_REVISION = "748af34c4268e768f0e3a7e7cdbe64c02835b7b6"
REPO_SLUG = "agentic_coding_tools"


# --------------------------------------------------------------------------
# a complete run, reused from the composition tests' shape
# --------------------------------------------------------------------------


def _corpus() -> Corpus:
    return load_corpus(CORPUS_ROOT)


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


def _span_hits(case: Case) -> tuple[RenderedHit, ...]:
    return tuple(
        RenderedHit(span.file_path, span.start_line, span.end_line)
        for span in case.labels.evidence_spans
    )


def _semantic_arm(case: Case) -> Arm:
    expectation = case.expectation
    if expectation is None:
        return Arm(arm="semantic", status="injected", hits=_span_hits(case))
    if expectation.status == "fallback":
        return fallback_arm("semantic", str(expectation.trigger), str(expectation.reason))
    spans = _span_hits(case)
    wanted = expectation.rendered_hits or len(spans)
    return Arm(
        arm="semantic",
        status="injected",
        hits=tuple(spans[index % len(spans)] for index in range(wanted)),
    )


def _outcome(case: Case) -> CaseOutcome:
    return CaseOutcome(
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


#: The provider kind is the one field the wire's index block never carries, so
#: it arrives from the configured contract. It is an ``EmbeddingProviderKind``
#: value, not a model identifier.
CONTRACT = {"provider_kind": "local"}


def _index(**overrides: Any) -> report_module.IndexIdentity:
    response = json.loads((RESPONSES / "adv-leaked-hit.json").read_text(encoding="utf-8"))
    identity = report_module.index_identity_from_response(
        response, tier="live", contract=CONTRACT
    )
    if not overrides:
        return identity
    import dataclasses

    return dataclasses.replace(identity, **overrides)


def _report(corpus: Corpus, **overrides: Any) -> dict[str, Any]:
    outcomes = [_outcome(case) for case in corpus.cases]
    measurement = overrides.pop("measurement", _measurement())
    composed = compose_verdict(corpus, outcomes, measurement)
    fields: dict[str, Any] = {
        "corpus": corpus,
        "composed": composed,
        "measurement": measurement,
        "harness": report_module.harness_identity(corpus),
        "repository": report_module.RepositoryIdentity(
            repo_slug=REPO_SLUG, evaluated_revision=EVALUATED_REVISION
        ),
        "index": _index(),
    }
    fields.update(overrides)
    return report_module.build_report(**fields)


# --------------------------------------------------------------------------
# schema validity on write
# --------------------------------------------------------------------------


def test_a_composed_run_produces_a_schema_valid_report(tmp_path: Path) -> None:
    document = _report(_corpus())
    written = report_module.write_report(tmp_path / "report.json", document)
    assert written.is_file()
    report_module.validate_report(report_module.read_report(written))


def test_a_failing_run_produces_a_schema_valid_report(tmp_path: Path) -> None:
    """A fail must be as writable as a pass, or "could not measure" is unwritable."""
    document = _report(_corpus(), measurement=_measurement(index_tier="none"))
    assert document["verdict"] == "fail"
    assert document["fail_reasons"]
    report_module.write_report(tmp_path / "report.json", document)


def test_an_invalid_report_is_never_written(tmp_path: Path) -> None:
    document = _report(_corpus())
    del document["index"]
    destination = tmp_path / "report.json"

    with pytest.raises(report_module.ReportError):
        report_module.write_report(destination, document)
    assert not destination.exists(), "an invalid report reached the durable path"


def test_a_report_without_an_environment_block_is_unwritable(tmp_path: Path) -> None:
    document = _report(_corpus())
    del document["environment"]
    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "report.json", document)


def test_a_report_without_a_corpus_digest_is_unwritable(tmp_path: Path) -> None:
    """The digest is what makes stale evidence detectable (design D12)."""
    document = _report(_corpus())
    del document["harness"]["corpus_digest"]
    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "report.json", document)


def test_an_optional_gate_is_unwritable(tmp_path: Path) -> None:
    """``required`` is ``const: true``: "we didn't gate on that one" is not a document."""
    document = _report(_corpus())
    document["gates"][0]["required"] = False
    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "report.json", document)


def test_a_passing_report_carrying_failure_reasons_is_unwritable(tmp_path: Path) -> None:
    document = _report(_corpus())
    assert document["verdict"] == "pass"
    document["fail_reasons"] = ["unmeasured"]
    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "report.json", document)


def test_a_failing_report_with_no_reasons_is_unwritable(tmp_path: Path) -> None:
    document = _report(_corpus(), measurement=_measurement(index_tier="none"))
    del document["fail_reasons"]
    with pytest.raises(report_module.ReportError):
        report_module.write_report(tmp_path / "report.json", document)


def test_a_verdict_outside_the_closed_enum_is_unwritable(tmp_path: Path) -> None:
    for invented in ("waived", "blocked", "skipped", "partial", "unmeasured"):
        document = _report(_corpus())
        document["verdict"] = invented
        with pytest.raises(report_module.ReportError):
            report_module.write_report(tmp_path / "report.json", document)


# --------------------------------------------------------------------------
# provenance — wp-measure runs `-k provenance` against this file
# --------------------------------------------------------------------------


def test_report_provenance_names_the_index_and_its_embedding_configuration() -> None:
    document = _report(_corpus())
    index = document["index"]
    assert index["tier"] in ("none", "seeded", "live")
    assert index["indexed_revision"]
    assert index["namespace_kind"] and index["namespace_key"]

    embedder = index["embedder"]
    for required in ("provider_kind", "model_id", "dimension", "fingerprint"):
        assert embedder[required], required
    assert re.fullmatch(r"[0-9a-f]{64}", embedder["fingerprint"])


def test_report_provenance_records_the_service_state_at_measurement_time() -> None:
    for enabled in (True, False):
        document = _report(_corpus(), measurement=_measurement(code_search_enabled=enabled))
        assert document["environment"]["code_search_enabled"] is enabled
    for adapter in ("resolved", "degraded"):
        document = _report(_corpus(), measurement=_measurement(scope_adapter=adapter))
        assert document["environment"]["scope_adapter"] == adapter


def test_report_provenance_carries_the_harness_version_and_corpus_digest() -> None:
    corpus = _corpus()
    document = _report(corpus)
    assert document["harness"]["corpus_digest"] == corpus.digest
    assert document["harness"]["version"]
    assert document["harness"]["name"] == "context-eval"


def test_report_provenance_records_the_evaluated_revision_and_declared_budget() -> None:
    corpus = _corpus()
    document = _report(corpus)
    assert document["repository"]["evaluated_revision"] == EVALUATED_REVISION
    assert document["budget"] == {
        "max_hits": corpus.budget.max_hits,
        "max_files": corpus.budget.max_files,
        "max_total_lines": corpus.budget.max_total_lines,
        "max_hit_lines": corpus.budget.max_hit_lines,
    }


def test_report_provenance_declares_the_denominator_from_the_manifest() -> None:
    corpus = _corpus()
    document = _report(corpus)
    assert document["corpus"]["cases_declared"] == len(corpus.cases)
    assert document["corpus"]["gates_declared"] == len(corpus.gates)
    assert document["corpus"]["consumers_declared"] == len(corpus.consumers)
    assert len(document["cases"]) == len(corpus.cases)


def test_an_as_of_timestamp_is_recorded_verbatim() -> None:
    supplied = "2026-07-28T00:00:00Z"
    document = _report(_corpus(), as_of=supplied)
    assert document["as_of"] == supplied


# --------------------------------------------------------------------------
# self-describing gates and consumers
# --------------------------------------------------------------------------


def test_every_gate_carries_its_thresholds_and_its_measurements() -> None:
    corpus = _corpus()
    document = _report(corpus)
    declared = {gate.id: dict(gate.thresholds) for gate in corpus.gates}
    for gate in document["gates"]:
        assert gate["thresholds"] == declared[gate["id"]]
        assert gate["measured"]


def test_every_declared_consumer_appears_with_its_applicability() -> None:
    corpus = _corpus()
    document = _report(corpus)
    recorded = {entry["consumer"]: entry for entry in document["per_consumer"]}
    assert set(recorded) == {slice_.consumer for slice_ in corpus.consumers}
    for slice_ in corpus.consumers:
        entry = recorded[slice_.consumer]
        assert entry["utility_applicable"] is slice_.utility_applicable
        if not slice_.utility_applicable:
            assert entry["utility_not_applicable_reason"]


def test_an_unscored_case_carries_its_reason_and_no_arms(tmp_path: Path) -> None:
    corpus = _corpus()
    outcomes = [_outcome(case) for case in corpus.cases]
    outcomes[0] = CaseOutcome(
        case_id=outcomes[0].case_id,
        consumer=outcomes[0].consumer,
        scored=False,
        unscored_reason="timeout",
    )
    composed = compose_verdict(corpus, outcomes, _measurement())
    document = _report(corpus, composed=composed)

    entry = next(case for case in document["cases"] if case["case_id"] == outcomes[0].case_id)
    assert entry["scored"] is False
    assert entry["unscored_reason"] == "timeout"
    assert "arms" not in entry
    report_module.write_report(tmp_path / "report.json", document)


# --------------------------------------------------------------------------
# derived identity
# --------------------------------------------------------------------------


def test_embedder_identity_is_read_from_the_configured_contract() -> None:
    class Contract:
        provider_kind = "local"
        model_id = "a-model-the-test-supplies"
        dimension = 384
        fingerprint = "f" * 64

    embedder = report_module.embedder_from_contract(Contract())
    assert embedder.model_id == Contract.model_id
    assert embedder.dimension == Contract.dimension


def test_an_incomplete_embedding_contract_is_an_error_not_a_default() -> None:
    with pytest.raises(report_module.ReportError):
        report_module.embedder_from_contract({"provider_kind": "local"})


def test_index_identity_is_read_from_the_response_that_answered() -> None:
    response = json.loads((RESPONSES / "adv-leaked-hit.json").read_text(encoding="utf-8"))
    identity = report_module.index_identity_from_response(
        response, tier="live", contract=CONTRACT
    )
    assert identity.indexed_revision == response["index"]["source_revision"]
    assert identity.namespace_kind == response["index"]["namespace"]["kind"]
    assert identity.embedder.model_id == response["index"]["embedder_model"]


def test_no_model_identifier_appears_in_the_verdict_report_or_judge_modules() -> None:
    offenders: list[str] = []
    for name in IDENTITY_MODULES:
        module = SRC / "context_eval" / name
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for pattern in MODEL_ID_PATTERNS:
                    if pattern.search(node.value):
                        offenders.append(f"{name}:{node.lineno}: {pattern.pattern}")
    assert not offenders, "\n".join(offenders)


def test_the_model_literal_detector_still_detects() -> None:
    """Positive control, so a detector that stopped detecting fails loudly."""
    for identifier in (
        "sentence-transformers/all-MiniLM-L6-v2",
        "text-embedding-3-small",
        "bge-large-en-v1.5",
    ):
        assert any(pattern.search(identifier) for pattern in MODEL_ID_PATTERNS), identifier


# --------------------------------------------------------------------------
# the contract this file validates against is the promoted one
# --------------------------------------------------------------------------


def test_the_emitter_validates_against_the_promoted_contract() -> None:
    """Not the change-local authoring copy, which moves when this change archives."""
    assert report_module.DEFAULT_REPORT_SCHEMA == REPORT_SCHEMA
    assert REPORT_SCHEMA.is_file()


def test_the_report_verdict_enum_has_exactly_two_members() -> None:
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    assert schema["$defs"]["Verdict"]["enum"] == ["pass", "fail"]
