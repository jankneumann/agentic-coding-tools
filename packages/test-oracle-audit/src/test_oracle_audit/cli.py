"""Command-line entry point (design D1, D15).

``test-oracle-audit [global options] <subcommand>``. Every stage writes
``<out>/<stage>.jsonl``; ``analyze`` joins them into ``<out>/analysis.json``
and ``report`` renders ``<out>/report.md``. The exit code never reflects audit
findings: it is non-zero only for usage errors and for ``report --validate``
on a schema-invalid analysis.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema

from . import records as rec
from .records import StageRecord, SuiteSpec, TestEntry

STAGE_FILE = {
    "inventory": "inventory",
    "static": "static",
    "judge": "judged",
    "mutate": "mutation",
    "refactor": "rename",
    "history": "history",
    "explain": "explain",
}
STAGE_ORDER = ("inventory", "static", "judge", "mutate", "refactor", "history", "explain")
MEASURED_STAGES = ("static", "judged", "mutation", "rename", "history")


class CommandBackend:
    """ExplainBackend that pipes the prompt to a shell command and reads its stdout."""

    def __init__(self, command: str) -> None:
        self.argv = shlex.split(command)

    def run(self, prompt: str, system: str | None = None) -> str:
        text = prompt if system is None else f"{system}\n\n{prompt}"
        done = subprocess.run(self.argv, input=text, capture_output=True, text=True, check=True)
        return done.stdout


# --- context ----------------------------------------------------------------


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(args.repo_root).resolve()
        suites = rec.load_suites(Path(args.suites_file) if args.suites_file else None)
        if args.suite not in suites:
            raise SystemExit(f"unknown suite {args.suite!r}; known: {', '.join(sorted(suites))}")
        self.suite: SuiteSpec = suites[args.suite]
        default_out = self.repo_root / "docs" / "reports" / "test-oracle-audit" / date.today().isoformat()
        self.out = Path(args.out).resolve() if args.out else default_out
        self.ledger_path = (
            Path(args.ledger).resolve()
            if args.ledger
            else self.repo_root / "docs" / "reports" / "test-oracle-audit" / "labels.json"
        )
        self.python = args.python
        self.dry_run = bool(args.dry_run)

    def path(self, stage_file: str) -> Path:
        return self.out / f"{stage_file}.jsonl"

    def write(self, stage_file: str, records: Sequence[StageRecord]) -> None:
        rec.write_records(self.path(stage_file), records)

    def read(self, stage_file: str) -> list[StageRecord]:
        return rec.read_records(self.path(stage_file))

    # Inventory is the join key for everything; recompute when absent so each
    # stage subcommand also works standalone against an empty --out.
    def inventory_records(self) -> list[StageRecord]:
        if not self.path("inventory").exists():
            run_inventory(self)
        return self.read("inventory")

    def entries(self) -> list[TestEntry]:
        return rec.to_entries(self.inventory_records())


# --- stages -----------------------------------------------------------------


def run_inventory(ctx: Context) -> None:
    from . import inventory

    ctx.write("inventory", inventory.build_inventory(ctx.suite, repo_root=ctx.repo_root, python=ctx.python))


def run_static(ctx: Context) -> None:
    from . import static_checks

    entries = ctx.entries()
    ctx.write(
        "static",
        static_checks.run_static(entries, repo_root=ctx.repo_root, source_roots=ctx.suite.source_roots),
    )


def run_judge(ctx: Context) -> None:
    from . import judged

    telemetry = ctx.out / "judged-telemetry.jsonl"

    def sink(event: dict[str, Any]) -> None:
        telemetry.parent.mkdir(parents=True, exist_ok=True)
        with telemetry.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, default=str) + "\n")

    ctx.write(
        "judged",
        judged.run_judged(ctx.entries(), repo_root=ctx.repo_root, dry_run=ctx.dry_run, event_sink=sink),
    )


def run_mutate(ctx: Context) -> None:
    from . import mutation

    mutants, records = mutation.run_mutation(
        ctx.suite,
        ctx.entries(),
        repo_root=ctx.repo_root,
        max_mutants=ctx.args.max_mutants,
        seed=ctx.args.seed,
        python=ctx.python,
    )
    ctx.write("mutation", records)
    mutants_path = ctx.out / "mutants.jsonl"
    mutants_path.parent.mkdir(parents=True, exist_ok=True)
    with mutants_path.open("w", encoding="utf-8") as fh:
        for mutant in mutants:
            data = mutant.to_json()
            rec.validate(data, "mutation-result")
            fh.write(json.dumps(data, sort_keys=True) + "\n")


def run_refactor(ctx: Context) -> None:
    from . import refactor

    ctx.write(
        "rename",
        refactor.run_rename_survival(ctx.suite, ctx.entries(), repo_root=ctx.repo_root, python=ctx.python),
    )


def run_history(ctx: Context) -> None:
    from . import history

    ctx.write("history", history.run_history(ctx.entries(), repo_root=ctx.repo_root))


def joined_records(ctx: Context) -> dict[str, dict[str, StageRecord]]:
    """node_id -> {stage: record} over the inventory's ok entries."""
    joined: dict[str, dict[str, StageRecord]] = {e.test_id.node_id: {} for e in ctx.entries()}
    for stage in (*MEASURED_STAGES, "explain"):
        for record in ctx.read(stage):
            if record.test_id.node_id in joined:
                joined[record.test_id.node_id][stage] = record
    return joined


def kill_rate_cuts(mutation_records: Sequence[StageRecord]) -> tuple[float, float] | None:
    from .thresholds import tercile_cutpoints

    rates = [
        r.payload["kill_rate"]
        for r in mutation_records
        if r.status == "ok" and isinstance(r.payload.get("kill_rate"), int | float)
    ]
    return tercile_cutpoints(rates) if rates else None


def run_explain(ctx: Context) -> None:
    from . import explain

    backend = CommandBackend(ctx.args.explain_command) if ctx.args.explain_command else None
    joined = joined_records(ctx)
    for record in joined.values():
        record.pop("explain", None)
    ctx.write(
        "explain",
        explain.run_explain(
            ctx.entries(),
            joined,
            backend=None if ctx.dry_run else backend,
            kill_rate_cuts=kill_rate_cuts(ctx.read("mutation")),
        ),
    )


STAGE_RUNNERS = {
    "inventory": run_inventory,
    "static": run_static,
    "judge": run_judge,
    "mutate": run_mutate,
    "refactor": run_refactor,
    "history": run_history,
    "explain": run_explain,
}


# --- analysis, labels, report -------------------------------------------------


def current_hashes(ctx: Context) -> dict[str, str]:
    return {e.test_id.node_id: e.test_id.content_hash for e in ctx.entries()}


def run_analyze(ctx: Context) -> None:
    from . import analysis
    from .ledger import LabelLedger

    labels = LabelLedger.load(ctx.ledger_path).current_labels(current_hashes(ctx))
    joined = joined_records(ctx)
    document = analysis.analyze(joined, labels, seed=ctx.args.seed, suites=[ctx.suite.name])
    rec.validate(document, "analysis-report")
    ctx.out.mkdir(parents=True, exist_ok=True)
    (ctx.out / "analysis.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def boundaries(ctx: Context) -> dict[str, str]:
    """Top judged boundary label per node id (descriptive only, D7)."""
    out: dict[str, str] = {}
    for record in ctx.read("judged"):
        dist = record.payload.get("boundary") if record.status == "ok" else None
        if isinstance(dist, dict) and dist:
            out[record.test_id.node_id] = max(dist, key=lambda k: dist[k])
    return out


def run_report(ctx: Context) -> int:
    from . import report

    analysis_path = ctx.out / "analysis.json"
    if not analysis_path.exists():
        run_analyze(ctx)
    document = json.loads(analysis_path.read_text("utf-8"))
    if ctx.args.validate:
        try:
            rec.validate(document, "analysis-report")
        except jsonschema.ValidationError as exc:
            print(f"analysis.json is invalid: {exc}", file=sys.stderr)
            return 2
        print(f"{analysis_path} is valid")
        return 0
    (ctx.out / "report.md").write_text(
        report.render_report(document, boundaries=boundaries(ctx)), encoding="utf-8"
    )
    return 0


def run_label(ctx: Context) -> int:
    from . import labelling

    args = ctx.args
    if args.label_action == "record":
        if not (args.node_id and args.label and args.labeller):
            raise SystemExit("label record needs NODE_ID LABEL and --labeller")
        if ctx.dry_run:
            print("dry run: ledger not written")
            return 0
        entry = labelling.record_label(
            args.node_id,
            args.label,
            repo_root=ctx.repo_root,
            ledger_path=ctx.ledger_path,
            labeller=args.labeller,
            note=args.note,
        )
        print(f"recorded {entry.label} for {entry.node_id}")
        return 0
    if not ctx.path("static").exists():
        run_static(ctx)
    card = labelling.label_next(
        ctx.entries(),
        ctx.read("static"),
        ctx.read("mutation"),
        repo_root=ctx.repo_root,
        out_dir=ctx.out,
        ledger_path=ctx.ledger_path,
        n=args.sample_size,
        seed=args.seed,
        dry_run=ctx.dry_run,
    )
    print(card if card is not None else "all sampled tests are labelled")
    return 0


def run_all(ctx: Context) -> int:
    for stage in STAGE_ORDER:
        STAGE_RUNNERS[stage](ctx)
    run_analyze(ctx)
    return run_report(ctx)


# --- argument parsing -------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test-oracle-audit", description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--suites-file", help="suites.json (default: the package's config/suites.json)")
    parser.add_argument("--suite", required=True, help="suite name from the suites file")
    parser.add_argument("--out", help="output dir (default: docs/reports/test-oracle-audit/<date>)")
    parser.add_argument("--ledger", help="label ledger (default: docs/reports/test-oracle-audit/labels.json)")
    parser.add_argument(
        "--python", help="run audited pytest with this interpreter instead of uv run --project"
    )
    parser.add_argument("--dry-run", action="store_true", help="no judge/explain calls; label writes nothing")
    parser.add_argument("--max-mutants", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--explain-command", help="shell command used as the explanation backend (stdin -> stdout)"
    )

    sub = parser.add_subparsers(dest="command", required=True)
    for name in (*STAGE_ORDER, "analyze", "run-all"):
        sub.add_parser(name)
    report = sub.add_parser("report")
    report.add_argument("--validate", action="store_true", help="validate analysis.json against the schema")
    label = sub.add_parser("label")
    label.add_argument("label_action", nargs="?", choices=("next", "record"), default="next")
    label.add_argument("node_id", nargs="?")
    label.add_argument("label", nargs="?")
    label.add_argument("--labeller")
    label.add_argument("--note")
    label.add_argument("--sample-size", type=int, default=40)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if not hasattr(args, "validate"):
        args.validate = False
    ctx = Context(args)
    ctx.out.mkdir(parents=True, exist_ok=True)
    command = args.command
    if command in STAGE_RUNNERS:
        STAGE_RUNNERS[command](ctx)
        return 0
    if command == "analyze":
        run_analyze(ctx)
        return 0
    if command == "report":
        return run_report(ctx)
    if command == "label":
        return run_label(ctx)
    if command == "run-all":
        return run_all(ctx)
    raise SystemExit(f"unknown command {command!r}")  # pragma: no cover - argparse rejects it first


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
