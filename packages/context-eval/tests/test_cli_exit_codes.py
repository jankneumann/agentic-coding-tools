"""Nothing exits 0 without a schema-valid passing report on disk.

The four codes are the mechanism that keeps "we could not run it" and "we ran it
and it failed" from being described as the same event — which is precisely what
the July 2026 waiver did, and what a single non-zero code invites:

    0  a schema-valid report with a passing verdict is on disk
    1  the measurement could not be taken, or could not be recorded
    2  it was taken, recorded, and a gate failed
    3  the report is absent, unparseable, schema-invalid, or stale

Every test here drives ``main()`` and asserts the returned code. The
``exit 0`` cases are the load-bearing ones: a report that is absent, a report
that is corrupt, and a report whose corpus digest has moved must all fail to
produce a success, and a run that decided ``pass`` in memory must not exit 0
unless the file it wrote says so too.

One end-to-end ``run`` is included, over a reduced corpus copied into ``tmp_path``
and a checkout the test creates. It is offline by construction — the semantic arm
comes from the corpus's recorded responses through ri-12's own decision tree —
so it exercises the whole path (producers, composition, emission, re-read) with
no coordinator, no database and no embedder. Its expected outcome is a *failing*
report, and that is the honest result for a run with no live index: the point is
that the failure is recorded rather than waived.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
RESPONSES = CORPUS_ROOT / "responses"
SEMANTIC_CONTEXT = REPO_ROOT / "skills" / "context-engineering" / "scripts" / "semantic_context.py"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval import report as report_module  # noqa: E402
from context_eval.__main__ import (  # noqa: E402
    EXIT_APPARATUS,
    EXIT_GATE_FAILURE,
    EXIT_PASS,
    EXIT_REPORT_UNUSABLE,
    main,
)
from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case, Corpus  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit, fallback_arm  # noqa: E402
from context_eval.verdict import CaseOutcome, MeasurementContext, compose_verdict  # noqa: E402

CONTRACT = {"provider_kind": "local"}
EVALUATED_REVISION = "748af34c4268e768f0e3a7e7cdbe64c02835b7b6"
REPO_SLUG = "agentic_coding_tools"


def test_the_four_exit_codes_are_distinct() -> None:
    codes = (EXIT_PASS, EXIT_APPARATUS, EXIT_GATE_FAILURE, EXIT_REPORT_UNUSABLE)
    assert codes == (0, 1, 2, 3)
    assert len(set(codes)) == len(codes)


# --------------------------------------------------------------------------
# building reports to check
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
    return report_module.build_report(
        corpus=corpus,
        composed=composed,
        measurement=measurement,
        harness=report_module.harness_identity(corpus),
        repository=report_module.RepositoryIdentity(
            repo_slug=REPO_SLUG, evaluated_revision=EVALUATED_REVISION
        ),
        index=report_module.index_identity_from_response(
            response, tier=measurement.index_tier, contract=CONTRACT
        ),
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


def _write(path: Path, document: dict[str, Any]) -> Path:
    return report_module.write_report(path, document)


# --------------------------------------------------------------------------
# check: 0 / 1 / 2 / 3
# --------------------------------------------------------------------------


def test_a_passing_report_on_disk_exits_zero(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    destination = _write(tmp_path / "report.json", _document(corpus, _measurement()))
    assert main(["check", "--report", str(destination)]) == EXIT_PASS


def test_a_gate_failure_exits_two(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    document = _document(corpus, _measurement(index_tier="none"))
    assert document["verdict"] == "fail"
    destination = _write(tmp_path / "report.json", document)
    assert main(["check", "--report", str(destination)]) == EXIT_GATE_FAILURE


def test_a_recorded_apparatus_failure_exits_one(tmp_path: Path) -> None:
    """Recorded, not waived: the report is written and the exit code says why."""
    corpus = load_corpus(CORPUS_ROOT)
    document = _document(corpus, _measurement(scope_adapter="degraded"))
    assert "apparatus_failure" in document["fail_reasons"]
    destination = _write(tmp_path / "report.json", document)
    assert main(["check", "--report", str(destination)]) == EXIT_APPARATUS


def test_an_absent_report_exits_three(tmp_path: Path) -> None:
    assert main(["check", "--report", str(tmp_path / "nothing.json")]) == EXIT_REPORT_UNUSABLE


def test_an_unparseable_report_exits_three(tmp_path: Path) -> None:
    destination = tmp_path / "report.json"
    destination.write_text("{ this is not json", encoding="utf-8")
    assert main(["check", "--report", str(destination)]) == EXIT_REPORT_UNUSABLE


def test_a_schema_invalid_report_exits_three(tmp_path: Path) -> None:
    """Even when it claims to pass. Especially when it claims to pass."""
    corpus = load_corpus(CORPUS_ROOT)
    document = _document(corpus, _measurement())
    assert document["verdict"] == "pass"
    del document["index"]
    destination = tmp_path / "report.json"
    destination.write_text(json.dumps(document), encoding="utf-8")
    assert main(["check", "--report", str(destination)]) == EXIT_REPORT_UNUSABLE


def test_a_report_claiming_a_verdict_outside_the_enum_exits_three(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    document = _document(corpus, _measurement())
    document["verdict"] = "waived"
    destination = tmp_path / "report.json"
    destination.write_text(json.dumps(document), encoding="utf-8")
    assert main(["check", "--report", str(destination)]) == EXIT_REPORT_UNUSABLE


def test_a_report_against_a_moved_corpus_is_stale_and_exits_three(tmp_path: Path) -> None:
    """The mechanism that replaces a waiver field (design D12)."""
    corpus = load_corpus(CORPUS_ROOT)
    destination = _write(tmp_path / "report.json", _document(corpus, _measurement()))

    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS_ROOT, copied)
    manifest = copied / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n# a threshold argument someone had\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "check",
                "--report",
                str(destination),
                "--corpus",
                str(copied),
                "--verify-corpus-digest",
            ]
        )
        == EXIT_REPORT_UNUSABLE
    )
    # And the same report against its own corpus still passes, so the check
    # above is about the digest and not about something else being broken.
    assert (
        main(
            [
                "check",
                "--report",
                str(destination),
                "--corpus",
                str(CORPUS_ROOT),
                "--verify-corpus-digest",
            ]
        )
        == EXIT_PASS
    )


# --------------------------------------------------------------------------
# run: end to end, offline, and never exiting 0 on a report it did not write
# --------------------------------------------------------------------------


def _reduced_corpus(tmp_path: Path) -> Path:
    """A copy of the real corpus holding only the recorded-response cases.

    Those are the cases measurable with no coordinator, no database and no
    embedder, which is what makes this test hermetic. The gates, the budget and
    the thresholds are the real ones, so the run exercises the real composition.
    """
    copied = tmp_path / "corpus"
    shutil.copytree(CORPUS_ROOT, copied)
    manifest = yaml.safe_load((copied / "manifest.yaml").read_text(encoding="utf-8"))

    keep = {
        "implement-feature": ["ADV-LEAKED-HIT", "FC-NO-INDEX-AT-REVISION"],
        "validate-feature": ["FC-SCOPE-REJECTED", "ADV-ALL-HITS-FILTERED"],
        "parallel-review-implementation": ["FC-UNKNOWN-STATE", "ADV-DENY-PRECEDENCE"],
        "iterate-on-implementation": ["FC-REVISION-MISMATCH"],
        "quick-task": ["FC-QUICK-TASK-NO-DECLARED-SCOPE"],
        "debugging-and-error-recovery": ["FC-DEBUG-ADHOC-NO-SCOPE"],
    }
    manifest["consumers"] = [
        {**slice_, "cases": keep[slice_["consumer"]]}
        for slice_ in manifest["consumers"]
        if slice_["consumer"] in keep
    ]
    manifest["cases"] = [
        f"cases/{case_id}.yaml" for ids in keep.values() for case_id in sorted(ids)
    ]
    (copied / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), "utf-8")
    return copied


def _checkout(tmp_path: Path) -> Path:
    """A tiny git checkout for the exact-search arm to run over."""
    root = tmp_path / "checkout"
    (root / "agent-coordinator" / "src").mkdir(parents=True)
    (root / "openspec").mkdir()
    (root / "agent-coordinator" / "src" / "agents_config.py").write_text(
        "def choose_model(work_package):\n    return work_package.model\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def _run_argv(tmp_path: Path, corpus: Path, checkout: Path, report_path: Path) -> list[str]:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(CONTRACT), encoding="utf-8")
    index = tmp_path / "index.json"
    index.write_text(
        (RESPONSES / "adv-leaked-hit.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return [
        "run",
        "--report", str(report_path),
        "--corpus", str(corpus),
        "--repository-root", str(checkout),
        "--evaluated-revision", EVALUATED_REVISION,
        "--repo-slug", REPO_SLUG,
        "--searcher", "tracked",
        "--embedding-contract", str(contract),
        "--index", str(index),
        "--index-tier", "none",
        "--coordination-transport", "http",
        "--semantic-context", str(SEMANTIC_CONTEXT),
    ]


def test_an_offline_run_records_a_schema_valid_failing_report(tmp_path: Path) -> None:
    corpus = _reduced_corpus(tmp_path)
    checkout = _checkout(tmp_path)
    destination = tmp_path / "report.json"

    code = main(_run_argv(tmp_path, corpus, checkout, destination))
    assert code in (EXIT_APPARATUS, EXIT_GATE_FAILURE), code
    assert destination.is_file(), "a run must record what it measured"

    document = report_module.read_report(destination)
    report_module.validate_report(document)
    assert document["verdict"] == "fail"
    assert document["fail_reasons"]
    # Every declared case appears, scored or not — nothing dropped out.
    assert len(document["cases"]) == document["corpus"]["cases_declared"]


def test_a_run_that_cannot_load_its_corpus_exits_one(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    destination = tmp_path / "report.json"
    argv = _run_argv(tmp_path, tmp_path / "no-such-corpus", checkout, destination)
    assert main(argv) == EXIT_APPARATUS
    assert not destination.exists()


def test_a_run_whose_helper_path_is_wrong_exits_one(tmp_path: Path) -> None:
    """Loud, not degraded: a harness that measured a different helper than the
    one it names would produce evidence about software nobody ran."""
    corpus = _reduced_corpus(tmp_path)
    checkout = _checkout(tmp_path)
    destination = tmp_path / "report.json"
    argv = _run_argv(tmp_path, corpus, checkout, destination)
    argv[argv.index("--semantic-context") + 1] = str(tmp_path / "not-a-module.py")
    assert main(argv) == EXIT_APPARATUS
    assert not destination.exists()


def test_a_run_that_cannot_record_its_report_exits_one(tmp_path: Path) -> None:
    """The invariant, from the other side: no report, no success."""
    corpus = _reduced_corpus(tmp_path)
    checkout = _checkout(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory\n", encoding="utf-8")

    argv = _run_argv(tmp_path, corpus, checkout, blocked / "report.json")
    assert main(argv) == EXIT_APPARATUS


def test_run_decides_its_exit_code_from_the_file_and_not_from_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete the report between writing it and checking it: the run must not pass.

    This is the mutation the whole design is against, run as a test: a harness
    that returned an exit code from the verdict it computed would exit 0 here.
    """
    corpus = load_corpus(CORPUS_ROOT)
    destination = tmp_path / "report.json"
    _write(destination, _document(corpus, _measurement()))
    assert main(["check", "--report", str(destination)]) == EXIT_PASS

    destination.unlink()
    assert main(["check", "--report", str(destination)]) == EXIT_REPORT_UNUSABLE


def test_the_cli_is_reachable_as_a_module(tmp_path: Path) -> None:
    """``python -m context_eval`` is the entry point every caller uses."""
    completed = subprocess.run(
        [sys.executable, "-m", "context_eval", "check", "--report", str(tmp_path / "absent.json")],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert completed.returncode == EXIT_REPORT_UNUSABLE, completed.stderr
