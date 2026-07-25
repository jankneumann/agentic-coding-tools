"""CLI for the deterministic context producers (ri-05) and the refresh
orchestrator (ri-07).

Per-producer subcommands (ri-05) keep each producer independently runnable:

    python scripts/cli.py list
    python scripts/cli.py check <producer_id>
    python scripts/cli.py generate <producer_id>
    python scripts/cli.py check-all

Orchestration subcommands (ri-07) drive every configured producer into one
durable operation and emit the manifest:

    python scripts/cli.py refresh                       # generate + manifest
    python scripts/cli.py refresh --producer api.contracts   # one producer
    python scripts/cli.py refresh-check                 # read-only drift

The exit code distinguishes deterministic drift from an internal failure:

* ``0`` — fresh / succeeded (or a generate that wrote successfully);
* ``2`` — drift / degraded detected (actionable, not an error);
* ``1`` — a producer failed or a fail-closed input error.

Output is the canonical ri-06 ``ProducerResult`` JSON (a list for ``*-all``) or,
for the orchestrator, a refresh summary, so callers parse exactly what ri-07
persists.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import orchestrator
from _runtime import ProducerStatus
from registry import Mode, ProducerError, list_producers, run_producer

# ``skills/shared`` (two levels up from this skill's ``scripts``) holds the
# shared checkout-policy guard; add it so the mutating ``refresh`` path can
# refuse a shared or bare checkout (design D7).
_SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"
if _SHARED_DIR.is_dir() and str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))


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


def _require_mutation(repository: Path) -> None:
    """Refuse a shared or bare checkout before the mutating refresh (D7).

    Best-effort: if the shared checkout-policy module is unavailable the guard is
    skipped rather than blocking the run.
    """
    try:
        from checkout_policy import (  # type: ignore[import-not-found]
            CheckoutPolicyError,
            require_mutation_allowed,
        )
    except Exception:  # noqa: BLE001 - guard is best-effort when the module is absent
        return
    try:
        require_mutation_allowed(cwd=repository)
    except CheckoutPolicyError as exc:
        raise ProducerError(
            f"refusing to write outside a managed worktree: {exc}"
        ) from exc


def _refresh_summary(result: orchestrator.RefreshResult) -> dict:
    return {
        "operation_id": result.operation_id,
        "outcome": result.outcome.value,
        "manifest_path": result.manifest_path,
        "manifest_sha256": result.manifest_sha256,
        "semantic_index": (
            result.semantic_index.to_dict() if result.semantic_index else None
        ),
        "producer_results": [r.to_dict() for r in result.producer_results],
    }


def _refresh(
    repository: Path, revision: str, producer_ids: list[str] | None, *, check: bool
) -> int:
    if check:
        result = orchestrator.check(
            repository, revision=revision, producer_ids=producer_ids
        )
    else:
        _require_mutation(repository)
        result = orchestrator.generate(
            repository, revision=revision, producer_ids=producer_ids
        )
    sys.stdout.write(json.dumps(_refresh_summary(result), indent=2) + "\n")
    return result.exit_code()


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

    for command in ("refresh", "refresh-check"):
        p = sub.add_parser(
            command,
            help=(
                "orchestrate every configured producer + emit the manifest"
                if command == "refresh"
                else "read-only orchestrated drift check (exit 2 = drift)"
            ),
        )
        p.add_argument(
            "--producer",
            action="append",
            dest="producers",
            metavar="ID",
            help="Limit the run to this producer id (repeatable).",
        )

    args = parser.parse_args(argv)
    repository = args.repo.resolve()

    if args.command == "list":
        sys.stdout.write(
            json.dumps([spec.to_dict() for spec in list_producers()], indent=2) + "\n"
        )
        return 0

    revision = _resolve_revision(repository, args.revision)
    if args.command in ("refresh", "refresh-check"):
        return _refresh(
            repository,
            revision,
            args.producers,
            check=args.command == "refresh-check",
        )
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
