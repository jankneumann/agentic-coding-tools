"""``agent-scenarios results {query,trend,latest}`` (design D2/D8)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .results_store import (
    GROUP_BY_CHOICES,
    JsonlResultsStore,
    RecordFilter,
    ResultRecord,
    compute_trend,
    default_results_path,
    latest_per_pair,
    parse_bound,
    run_states,
)


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--store", type=Path, default=None, help="results JSONL (default: XDG state)")
    p.add_argument("--vendor")
    p.add_argument("--skill", help="skill under test")
    p.add_argument("--family", choices=["plan", "implement", "validate", "merge", "other"])
    p.add_argument("--scenario")
    p.add_argument("--since", help="ISO date/time lower bound (inclusive)")
    p.add_argument("--until", help="ISO date/time upper bound (a bare date covers that day)")
    p.add_argument("--status", action="append", choices=["pass", "fail", "error", "skipped_budget"])
    p.add_argument("--format", choices=["json", "table"], default="json", dest="fmt")


def add_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the ``results`` command group on a parent ``subparsers`` object."""
    results: argparse.ArgumentParser = subparsers.add_parser(
        "results", help="query the durable results store"
    )
    sub = results.add_subparsers(dest="results_cmd", required=True)

    q = sub.add_parser("query", help="list matching result records")
    _add_filters(q)
    q.set_defaults(func=_cmd_query)

    t = sub.add_parser("trend", help="pass-rate per bucket")
    _add_filters(t)
    t.add_argument("--group-by", default="vendor,skill", choices=sorted(GROUP_BY_CHOICES))
    t.add_argument("--bucket", default="day", choices=["day", "week"])
    t.set_defaults(func=_cmd_trend)

    la = sub.add_parser("latest", help="most recent result per (scenario, vendor)")
    _add_filters(la)
    la.set_defaults(func=_cmd_latest)
    results.set_defaults(func=lambda a: results.print_help() or 2)
    return results


def _store(args: argparse.Namespace) -> JsonlResultsStore:
    return JsonlResultsStore(args.store or default_results_path())


def _filter(args: argparse.Namespace) -> RecordFilter:
    return RecordFilter(
        vendor=args.vendor,
        skill=args.skill,
        family=args.family,
        scenario=args.scenario,
        since=parse_bound(args.since) if args.since else None,
        until=parse_bound(args.until, end=True) if args.until else None,
        status=tuple(args.status or ()),
    )


def _print_table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> None:
    if not rows:
        print("(no records)")
        return
    cells = [[("" if r.get(c) is None else str(r.get(c))) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)))


def _annotated(store: JsonlResultsStore, results: Sequence[ResultRecord]) -> list[dict[str, Any]]:
    states = run_states(store)
    out: list[dict[str, Any]] = []
    for rec in results:
        row = rec.model_dump(mode="json")
        row["run_state"] = states.get(rec.run_id, "interrupted")
        out.append(row)
    return out


_RESULT_COLUMNS = ("recorded_at", "run_id", "scenario_id", "vendor", "deterministic_status",
                   "failed_gates", "run_state")


def _emit(rows: list[dict[str, Any]], columns: Sequence[str], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, indent=2))
    else:
        _print_table(rows, columns)


def _cmd_query(args: argparse.Namespace) -> int:
    store = _store(args)
    results = list(store.iter_results(_filter(args)))
    _emit(_annotated(store, results), _RESULT_COLUMNS, args.fmt)
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    store = _store(args)
    results = latest_per_pair(list(store.iter_results(_filter(args))))
    _emit(_annotated(store, results), _RESULT_COLUMNS, args.fmt)
    return 0


def _cmd_trend(args: argparse.Namespace) -> int:
    store = _store(args)
    group_by = GROUP_BY_CHOICES[args.group_by]
    rows = compute_trend(list(store.iter_results(_filter(args))), group_by, args.bucket)
    _emit(rows, ("bucket", *group_by, "pass", "fail", "error", "skipped_budget", "pass_rate"),
          args.fmt)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone entry for tests (``python -m agent_scenarios`` routes via ``__main__``)."""
    parser = argparse.ArgumentParser(prog="agent-scenarios")
    add_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
