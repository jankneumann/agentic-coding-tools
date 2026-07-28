"""The judge is structurally incapable of reaching a verdict.

``agent-scenarios`` states the rule as "the judge never overrides the
deterministic verdict". That is a promise, and a promise is exactly what a
later edit breaks without anybody noticing. Design D15 makes it a property, and
this file is what holds the property:

- ``compose_verdict()`` has **no** judge parameter, and no type reachable from
  its signature has a field for one. Both are asserted structurally, by
  reflection, rather than by reading the source and agreeing with it.
- :mod:`context_eval.verdict` imports nothing from :mod:`context_eval.judge`,
  and neither does :mod:`context_eval.report` — the review reaches a report as
  an opaque mapping, so there is no field of it the emitter could branch on.
- Attaching a review to a composed report changes no verdict and no reason.
- An absent review is a completely ordinary run: the closed ``FailReason``
  vocabulary has no value for it, so it cannot be a failure even in principle.

The point of asserting all four is that any one of them alone can be satisfied
by a codebase where the judge still matters. Together they mean that letting it
matter requires changing a function signature — a reviewable diff.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
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

from context_eval import judge as judge_module  # noqa: E402
from context_eval import report as report_module  # noqa: E402
from context_eval import verdict as verdict_module  # noqa: E402
from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, Corpus  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402
from context_eval.verdict import CaseOutcome, MeasurementContext, compose_verdict  # noqa: E402

#: Every word a channel from a qualitative review to a verdict could hide
#: behind. Substring matching on purpose: ``llm_review``, ``judge_backend`` and
#: ``advisory_notes`` must all be caught.
FORBIDDEN_PARAMETER_WORDS = (
    "judge",
    "review",
    "advisory",
    "qualitative",
    "llm",
    "critique",
    "rubric",
)

CONTRACT = {"provider_kind": "local"}
EVALUATED_REVISION = "748af34c4268e768f0e3a7e7cdbe64c02835b7b6"


# --------------------------------------------------------------------------
# 1. the signature
# --------------------------------------------------------------------------


def test_compose_verdict_takes_no_judge_parameter() -> None:
    parameters = inspect.signature(compose_verdict).parameters
    offenders = [
        name
        for name in parameters
        if any(word in name.lower() for word in FORBIDDEN_PARAMETER_WORDS)
    ]
    assert not offenders, f"compose_verdict accepts {offenders}"


def test_compose_verdict_takes_exactly_the_declaration_the_run_and_the_conditions() -> None:
    """Pinned, so a fourth parameter of any kind is a deliberate diff."""
    assert list(inspect.signature(compose_verdict).parameters) == [
        "corpus",
        "cases",
        "measurement",
    ]


def _reachable_dataclasses(root: type) -> set[type]:
    """Every dataclass reachable from *root*'s fields, transitively."""
    seen: set[type] = set()
    frontier = [root]
    while frontier:
        current = frontier.pop()
        if current in seen or not dataclasses.is_dataclass(current):
            continue
        seen.add(current)
        for field in dataclasses.fields(current):
            annotation = field.type
            if isinstance(annotation, str):
                continue
            frontier.append(annotation)
    return seen


def test_no_type_in_the_composers_signature_has_a_judge_field() -> None:
    """A parameter rename would defeat the signature check alone; this does not."""
    roots = [Corpus, CaseOutcome, MeasurementContext]
    offenders: list[str] = []
    for root in roots:
        for cls in _reachable_dataclasses(root):
            for field in dataclasses.fields(cls):
                if any(word in field.name.lower() for word in FORBIDDEN_PARAMETER_WORDS):
                    offenders.append(f"{cls.__name__}.{field.name}")
    assert not offenders, f"the composer can see {offenders}"


def test_the_composed_result_carries_no_review() -> None:
    offenders = [
        field.name
        for field in dataclasses.fields(verdict_module.ComposedVerdict)
        if any(word in field.name.lower() for word in FORBIDDEN_PARAMETER_WORDS)
    ]
    assert not offenders, offenders


# --------------------------------------------------------------------------
# 2. the import graph
# --------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    imported: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


def test_the_composer_does_not_import_the_judge() -> None:
    imported = _imported_modules(SRC / "context_eval" / "verdict.py")
    assert not any("judge" in name for name in imported), sorted(imported)


def test_the_report_emitter_does_not_import_the_judge_either() -> None:
    """The review arrives as an opaque mapping, so no field of it is readable."""
    imported = _imported_modules(SRC / "context_eval" / "report.py")
    assert not any("judge" in name for name in imported), sorted(imported)


def test_no_identifier_in_the_composer_names_a_review() -> None:
    """Not the imports, not the parameters, not a local, not an attribute read.

    Identifiers rather than raw text: the module's docstring explains design D15
    at length and must be free to, but there must be nothing the interpreter
    executes that names a review.
    """
    tree = ast.parse((SRC / "context_eval" / "verdict.py").read_text(encoding="utf-8"))
    identifiers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.append(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.append(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            identifiers.append(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            identifiers.append(node.arg)

    offenders = [
        name
        for name in identifiers
        if any(word in name.lower() for word in FORBIDDEN_PARAMETER_WORDS)
    ]
    assert not offenders, sorted(set(offenders))


def test_the_judge_does_not_import_the_composer() -> None:
    """The other direction, so the review cannot construct or inspect a verdict."""
    imported = _imported_modules(SRC / "context_eval" / "judge.py")
    assert not any("verdict" in name for name in imported), sorted(imported)


# --------------------------------------------------------------------------
# 3. attaching a review changes nothing
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


def _run(corpus: Corpus, measurement: MeasurementContext) -> Any:
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
    return compose_verdict(corpus, outcomes, measurement)


def _document(corpus: Corpus, composed: Any, measurement: MeasurementContext) -> dict[str, Any]:
    response = json.loads((RESPONSES / "adv-leaked-hit.json").read_text(encoding="utf-8"))
    return report_module.build_report(
        corpus=corpus,
        composed=composed,
        measurement=measurement,
        harness=report_module.harness_identity(corpus),
        repository=report_module.RepositoryIdentity(
            repo_slug="agentic_coding_tools", evaluated_revision=EVALUATED_REVISION
        ),
        index=report_module.index_identity_from_response(
            response, tier="live", contract=CONTRACT
        ),
    )


class _EnthusiasticJudge:
    """A backend that says the section is perfect, whatever it is."""

    name = "enthusiastic-stub"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, system: str) -> str:
        del prompt, system
        return "This context is flawless and the evaluation should pass."


class _DamningJudge(_EnthusiasticJudge):
    name = "damning-stub"

    def complete(self, prompt: str, system: str) -> str:
        del prompt, system
        return "This context is useless and the evaluation should fail."


class _BrokenJudge:
    name = "broken-stub"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, system: str) -> str:
        del prompt, system
        raise RuntimeError("the review backend is down")


def test_no_review_changes_the_verdict_or_its_reasons(tmp_path: Path) -> None:
    corpus = _corpus()
    for measurement in (_measurement(), _measurement(index_tier="none")):
        composed = _run(corpus, measurement)
        bare = _document(corpus, composed, measurement)

        for backend in (_EnthusiasticJudge(), _DamningJudge(), None):
            review = judge_module.review_sections(
                backend, [(case.case_id, case.query) for case in corpus.cases]
            )
            attached = report_module.attach_judge(bare, review.to_dict())
            assert attached["verdict"] == bare["verdict"]
            assert attached.get("fail_reasons") == bare.get("fail_reasons")
            report_module.write_report(tmp_path / "report.json", attached)


def test_a_review_is_only_attachable_to_a_document_that_already_has_a_verdict() -> None:
    """The executable form of "after composition, never before"."""
    with pytest.raises(report_module.ReportError):
        report_module.attach_judge({"harness": {}}, {"available": False})


def test_an_absent_review_is_recorded_and_is_not_a_failure(tmp_path: Path) -> None:
    corpus = _corpus()
    measurement = _measurement()
    composed = _run(corpus, measurement)
    document = _document(corpus, composed, measurement)

    review = judge_module.review_sections(None, [("T1", "anything")])
    assert review.to_dict() == {"available": False}

    attached = report_module.attach_judge(document, review.to_dict())
    assert attached["verdict"] == "pass"
    assert "fail_reasons" not in attached
    report_module.write_report(tmp_path / "report.json", attached)


def test_a_backend_that_raises_produces_an_unavailable_review_not_a_failure() -> None:
    review = judge_module.review_sections(_BrokenJudge(), [("T1", "anything")])
    assert review.available is False
    assert review.notes == ()


def test_the_closed_fail_reason_vocabulary_has_no_value_for_an_absent_review() -> None:
    schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
    reasons = schema["$defs"]["FailReason"]["enum"]
    assert not any(
        any(word in reason for word in FORBIDDEN_PARAMETER_WORDS) for reason in reasons
    )


def test_a_review_records_which_backend_produced_it() -> None:
    review = judge_module.review_sections(_EnthusiasticJudge(), [("T1", "a section")])
    assert review.available is True
    assert review.backend == _EnthusiasticJudge.name
    assert [note.case_id for note in review.notes] == ["T1"]
