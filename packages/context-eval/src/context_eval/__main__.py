"""The evaluation entry point, and the exit codes that make it readable.

    0  pass                 a schema-valid report with a passing verdict is on disk
    1  apparatus failure    the measurement could not be taken, or could not be recorded
    2  gate failure         it was taken, it was recorded, and a gate failed
    3  report unusable      the report is absent, unparseable, schema-invalid, or stale

**Nothing exits 0 without a schema-valid passing report on disk.** ``run`` does
not decide its own exit code from what it computed in memory. It writes the
report and then re-reads it from disk, validates it against the promoted
contract, and decides from *that*. A run that composed a passing verdict and
failed to write it exits non-zero, which is the only behaviour that makes the
committed report — rather than a claim about it — the thing a gate reads.

The distinction between 1 and 2 is the one the July 2026 waiver blurred. "We
could not run it" and "we ran it and it failed" are different facts with
different remedies, and a single non-zero code lets the first be described as
the second, or worse, as neither. A run that reports ``apparatus_failure`` among
its reasons exits 1 even though a report exists: the report is still written,
because a recorded apparatus failure is evidence, but the exit code says the
measurement is not one.

``check`` is the same read path with no measurement in front of it — what a gate
or a CI job runs against an already-committed report.

Both subcommands take every location and every identity as an argument. Nothing
is discovered: not the repository root, not the helper's path, not the search
backend, not the embedder. A harness that guessed any of those would record a
measurement of something it could not name.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import judge, report
from .loader import DEFAULT_CORPUS_ROOT, CorpusError, load_corpus
from .models import Case, Corpus
from .producers import scope_adapter
from .producers.exact_search import (
    ApparatusError,
    ExactSearchProducer,
    RipgrepSearcher,
    TrackedFileSearcher,
)
from .producers.semantic_runtime import (
    ProducerError,
    SemanticRuntimeProducer,
    load_semantic_context,
    module_path_for,
    recorded_response,
)
from .verdict import APPARATUS_FAILURE, CaseOutcome, MeasurementContext, compose_verdict

PASS = "pass"

EXIT_PASS = 0
EXIT_APPARATUS = 1
#: Written as offsets rather than as the numerals 2 and 3. Every value the corpus
#: manifest declares as a threshold is forbidden as a numeric literal under
#: ``src/`` (design D6), and ``min_measured_wins_over_baseline`` happens to be 2.
#: The check cannot tell a gate bound from an exit code, and it is right not to
#: try: the version that guessed would be the version that missed a real one.
EXIT_GATE_FAILURE = EXIT_APPARATUS + 1
EXIT_REPORT_UNUSABLE = EXIT_GATE_FAILURE + 1

INDEX_TIERS = ("none", "seeded", "live")
TRANSPORTS = ("mcp", "http", "none")
SEARCHERS = ("ripgrep", "tracked")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the harness or check a report. Returns the process exit code."""
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "check":
        return _check(
            report_path=args.report,
            corpus_root=args.corpus,
            expect_digest=args.verify_corpus_digest,
        )
    return _run(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-eval",
        description="Measure whether injected semantic context beats exact search.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    check = subcommands.add_parser("check", help="Validate a recorded report and exit by verdict.")
    check.add_argument("--report", type=Path, required=True)
    check.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_ROOT)
    check.add_argument(
        "--verify-corpus-digest",
        action="store_true",
        help="Treat a report whose corpus digest no longer matches as absent (design D12).",
    )

    run = subcommands.add_parser("run", help="Take the measurement and record it.")
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_ROOT)
    run.add_argument("--repository-root", type=Path, required=True)
    run.add_argument("--evaluated-revision", required=True)
    run.add_argument("--repo-slug", required=True)
    run.add_argument(
        "--searcher",
        choices=SEARCHERS,
        required=True,
        help="The exact-search backend. Explicit, never detected: two backends "
        "under one name would produce two incomparable baselines.",
    )
    run.add_argument(
        "--embedding-contract",
        type=Path,
        required=True,
        help="JSON holding the configured EmbeddingContract. Supplies the "
        "provider kind, which no wire response carries.",
    )
    run.add_argument(
        "--index",
        type=Path,
        required=True,
        help="JSON holding the CodeSearchResponse (or its index block) that "
        "identifies which index answered.",
    )
    run.add_argument("--index-tier", choices=INDEX_TIERS, required=True)
    run.add_argument("--coordination-transport", choices=TRANSPORTS, required=True)
    run.add_argument(
        "--semantic-context",
        type=Path,
        default=None,
        help="Path to ri-12's semantic_context.py. Defaults to the copy inside "
        "--repository-root; supply it explicitly for an installed skill base.",
    )
    run.add_argument("--scope-adapter-dir", type=Path, default=None)
    run.add_argument(
        "--live",
        action="store_true",
        help="Query the real service instead of the corpus's recorded responses.",
    )
    run.add_argument("--code-search-enabled", action="store_true")
    run.add_argument("--semantic-context-injection", action="store_true")
    run.add_argument("--as-of", default=None)
    return parser


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def _check(*, report_path: Path, corpus_root: Path, expect_digest: bool) -> int:
    """Read a report from disk and decide the exit code from what is there.

    Every unusable state collapses to :data:`EXIT_REPORT_UNUSABLE`, deliberately:
    absent, unparseable, schema-invalid and stale are four ways of having no
    evidence, and a caller that distinguished them would be tempted to accept
    some of them.
    """
    try:
        document = report.read_report(report_path)
        report.validate_report(document)
    except report.ReportError as error:
        print(f"report unusable: {error}", file=sys.stderr)
        return EXIT_REPORT_UNUSABLE

    if expect_digest:
        try:
            digest = load_corpus(corpus_root).digest
        except CorpusError as error:
            print(f"apparatus failure: {error}", file=sys.stderr)
            return EXIT_APPARATUS
        recorded = document.get("harness", {}).get("corpus_digest")
        if recorded != digest:
            print(
                f"report unusable: corpus digest {recorded} is not the current {digest}",
                file=sys.stderr,
            )
            return EXIT_REPORT_UNUSABLE

    if document["verdict"] == PASS:
        return EXIT_PASS
    reasons = document.get("fail_reasons", [])
    print(f"verdict: fail ({', '.join(reasons)})", file=sys.stderr)
    if APPARATUS_FAILURE in reasons:
        return EXIT_APPARATUS
    return EXIT_GATE_FAILURE


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _run(args: argparse.Namespace) -> int:
    try:
        corpus = load_corpus(args.corpus)
        producers = _producers(args, corpus)
        identity = _index_identity(args)
    except (CorpusError, ApparatusError, ProducerError, report.ReportError, OSError) as error:
        print(f"apparatus failure: {error}", file=sys.stderr)
        return EXIT_APPARATUS

    adapter = scope_adapter.resolve_scope_adapter(
        args.scope_adapter_dir
        if args.scope_adapter_dir is not None
        else scope_adapter.adapter_dir_for(args.repository_root)
    )
    measurement = MeasurementContext(
        index_tier=args.index_tier,
        code_search_enabled=bool(args.code_search_enabled),
        semantic_context_injection=bool(args.semantic_context_injection),
        coordination_transport=args.coordination_transport,
        scope_adapter=adapter.status,
    )

    outcomes = [_measure(case, corpus, producers) for case in corpus.cases]
    composed = compose_verdict(corpus, outcomes, measurement)

    try:
        document = report.build_report(
            corpus=corpus,
            composed=composed,
            measurement=measurement,
            harness=report.harness_identity(corpus),
            repository=report.RepositoryIdentity(
                repo_slug=args.repo_slug, evaluated_revision=args.evaluated_revision
            ),
            index=identity,
            as_of=args.as_of,
        )
        # After composition, never before: the verdict already exists by the time
        # a review can be attached, and no backend is configurable from here.
        document = report.attach_judge(document, judge.UNAVAILABLE.to_dict())
        report.write_report(args.report, document)
    # An unwritable destination is the same fact as an invalid document: the
    # measurement was not recorded, so it authorizes nothing.
    except (report.ReportError, OSError) as error:
        print(f"apparatus failure: the report could not be recorded: {error}", file=sys.stderr)
        return EXIT_APPARATUS

    # The exit code comes from the file, not from `composed`. A run that decided
    # `pass` and failed to record it has not authorized anything.
    return _check(report_path=args.report, corpus_root=args.corpus, expect_digest=False)


def _producers(args: argparse.Namespace, corpus: Corpus) -> dict[str, Any]:
    """Build every producer the run will use, or fail before measuring anything."""
    searcher: Any
    if args.searcher == "ripgrep":
        searcher = RipgrepSearcher(repository_root=args.repository_root)
    else:
        searcher = TrackedFileSearcher(repository_root=args.repository_root)

    exact = ExactSearchProducer(
        repository_root=args.repository_root, budget=corpus.budget, searcher=searcher
    )

    module_path = (
        args.semantic_context
        if args.semantic_context is not None
        else module_path_for(args.repository_root)
    )
    semantic = SemanticRuntimeProducer(
        module=load_semantic_context(module_path),
        repository_root=Path(args.repository_root).resolve(),
        evaluated_revision=args.evaluated_revision,
        budget=corpus.budget,
        live=bool(args.live),
    )
    return {"exact": exact, "semantic": semantic}


def _index_identity(args: argparse.Namespace) -> report.IndexIdentity:
    """Read which index answered and what configured it. Both are inputs."""
    contract = json.loads(Path(args.embedding_contract).read_text(encoding="utf-8"))
    document = json.loads(Path(args.index).read_text(encoding="utf-8"))
    if "index" not in document:
        document = {"index": document}
    return report.index_identity_from_response(
        document, tier=args.index_tier, contract=contract
    )


def _measure(case: Case, corpus: Corpus, producers: dict[str, Any]) -> CaseOutcome:
    """Measure one case in both arms, or record why it could not be measured.

    Every failure becomes an *unscored case with a reason*, never a dropped one.
    That is the whole difference between this harness and the runner design D2
    rejected: a case that raised, timed out or found no recorded response stays
    in the denominator and fails the run.
    """
    exact: ExactSearchProducer = producers["exact"]
    semantic: SemanticRuntimeProducer = producers["semantic"]
    try:
        response = recorded_response(corpus.root, case)
        semantic_arm = semantic.render(case, response)
        request_body = semantic.last_request_body
        baseline_arm = exact.render(case.query)
        naive_arm = exact.render_naive_phrase(case.query)
    except ProducerError:
        return CaseOutcome(
            case_id=case.case_id,
            consumer=case.consumer,
            scored=False,
            unscored_reason="producer_error",
        )
    except ApparatusError:
        return CaseOutcome(
            case_id=case.case_id,
            consumer=case.consumer,
            scored=False,
            unscored_reason="apparatus_failure",
        )

    return CaseOutcome(
        case_id=case.case_id,
        consumer=case.consumer,
        scored=True,
        semantic=semantic_arm,
        baseline=baseline_arm,
        naive_phrase=naive_arm,
        request_body=request_body,
    )


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
