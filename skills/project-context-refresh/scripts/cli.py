"""CLI for the deterministic context producers (ri-05).

Thin wrapper over :mod:`registry` so each producer is independently runnable
(from this skill's directory, or via ``make context-refresh`` at the repo root):

    python scripts/cli.py list
    python scripts/cli.py check <producer_id>
    python scripts/cli.py generate <producer_id>
    python scripts/cli.py check-all

The exit code distinguishes deterministic drift from an internal failure so a
future gate (ri-10) and orchestrator (ri-07) can branch on it:

* ``0`` — fresh (or a generate that wrote successfully);
* ``2`` — drift detected in check mode (actionable, not an error);
* ``1`` — a producer failed or a fail-closed input error.

Output is the canonical ri-06 ``ProducerResult`` JSON (a list for ``*-all``),
so callers parse exactly what ri-07 would persist.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from _runtime import ProducerStatus
from registry import Mode, ProducerError, list_producers, run_producer


def _resolve_revision(repository: Path, revision: str | None) -> str:
    if revision:
        return revision
    out = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    rev = out.stdout.strip()
    if not rev:
        raise ProducerError(
            "could not resolve HEAD; pass --revision <full-sha> explicitly"
        )
    return rev


def _exit_code(status: ProducerStatus) -> int:
    if status is ProducerStatus.FRESH:
        return 0
    if status is ProducerStatus.DEGRADED:
        return 2
    return 1  # failed / not-configured


def _run(mode: str, producer_ids, repository: Path, revision: str) -> int:
    typed_mode = cast(Mode, mode)
    results = [run_producer(pid, typed_mode, repository, revision) for pid in producer_ids]
    payload = [r.to_dict() for r in results]
    sys.stdout.write(json.dumps(payload if len(payload) != 1 else payload[0], indent=2) + "\n")
    return max((_exit_code(r.status) for r in results), default=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic context producers.")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root.")
    parser.add_argument("--revision", default=None, help="Full source Git SHA (default: HEAD).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List registered producers as JSON.")
    for command in ("generate", "check"):
        p = sub.add_parser(command, help=f"{command} one producer.")
        p.add_argument("producer_id")
    sub.add_parser("generate-all", help="generate every producer.")
    sub.add_parser("check-all", help="check every producer.")

    args = parser.parse_args(argv)
    repository = args.repo.resolve()

    if args.command == "list":
        sys.stdout.write(
            json.dumps([spec.to_dict() for spec in list_producers()], indent=2) + "\n"
        )
        return 0

    revision = _resolve_revision(repository, args.revision)
    if args.command in ("generate", "check"):
        return _run(args.command, [args.producer_id], repository, revision)
    mode = "generate" if args.command == "generate-all" else "check"
    ids = [spec.producer_id for spec in list_producers()]
    return _run(mode, ids, repository, revision)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProducerError as exc:
        sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(1) from exc
