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

``refresh`` carries two opt-in flags for the main-convergence sync point (ri-11),
both defaulting to off so that every existing invocation behaves exactly as before:

* ``--sync-point`` authorizes the mutation from the shared checkout by reaching
  the checkout policy's ``approved_sync_point`` branch. It is a *caller* decision
  and is never inferred from the environment — an environment sniff would re-open
  shared-checkout writes for every skill that happens to run on ``main``. The
  caller remains responsible for its own clean-tree and active-agent guards.
* ``--defer-semantic-index`` skips the inline index attempt and records the index
  as ``pending`` with an ``exact-search`` fallback, for a caller that enqueues the
  index itself against a later revision. Pending is a weaker claim than attempted,
  so a deferred run degrades (exit 2) rather than reporting success.

The branch-local checkpoint (ri-09) is a *third* mode, deliberately outside the
operation ledger: read-only, scoped to one work package, and advisory.

    python scripts/cli.py checkpoint --change-id C --package-id P \
        --changed-file docs/guide.md

The composed drift gate (ri-10) is a *fourth* mode: read-only, repository-wide,
and blocking. It is what ``make context-drift-gate`` runs, so a CI failure
reproduces verbatim in a developer checkout.

    python scripts/cli.py gate --base main

The exit code distinguishes deterministic drift from an internal failure:

* ``0`` — fresh / succeeded (or a generate that wrote successfully);
* ``2`` — drift / degraded detected (actionable, not an error);
* ``1`` — a producer failed or a fail-closed input error.

``checkpoint`` deliberately does not use ``2``: drift is data in its report, and
its only non-zero exit is being unable to produce a valid report at all (D8).

``gate`` uses the same three codes but derives them from ri-10's classification
rather than from ``OperationState``, which is why the two can disagree on the
same tree: an absent *optional* owner degrades ``refresh-check`` to ``2`` and
leaves ``gate`` at ``0``, because a required producer reporting no configuration
has already been rewritten to a failure by registry policy, so a surviving one
is external degradation. ``_exit_code`` and ``refresh-check`` keep their
mappings unchanged; the gate is a third caller with its own documented codes.

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

import checkpoint
import gate as gate_module
import orchestrator
from _runtime import ProducerStatus
from registry import Mode, ProducerError, list_producers, run_producer
from semantic_adapter import default_semantic_indexer

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


def _enforce_checkout_policy(repository: Path, *, sync_point: bool) -> None:
    """Classify the checkout and refuse the mutation when it is not allowed.

    Best-effort: if the shared checkout-policy module is unavailable the guard is
    skipped rather than blocking the run.

    The refusal chains the ``CheckoutPolicyError``, so a caller that needs the
    machine-readable ``PolicyReason`` reads it off ``__cause__.policy`` instead of
    parsing the message.
    """
    try:
        import checkout_policy  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - guard is best-effort when the module is absent
        return
    try:
        checkout_policy.require_mutation_allowed(cwd=repository, sync_point=sync_point)
    except checkout_policy.CheckoutPolicyError as exc:
        raise ProducerError(
            f"refusing to write outside a managed worktree: {exc}"
        ) from exc


def _require_mutation(repository: Path) -> None:
    """Refuse a shared or bare checkout before a mutating command (D7)."""
    _enforce_checkout_policy(repository, sync_point=False)


def _require_sync_point_mutation(repository: Path) -> None:
    """Authorize an explicit sync-point mutation on the shared checkout (ri-11 D5).

    A separate entry point rather than a defaulted parameter on
    :func:`_require_mutation`: sync-point authorization is a decision the caller
    must name, and threading it as an ordinary argument makes it reachable — and
    eventually reached by accident — from every other mutating call site.

    The policy's own message says the caller must still enforce clean-tree and
    active-agent guards. This function is layer 2 of that contract only; the
    convergence driver owns layers 1 and 3.
    """
    _enforce_checkout_policy(repository, sync_point=True)


def _owner_by_producer_id() -> dict[str, str]:
    """Map each configured producer id to its canonical owner.

    The ri-06 ``ProducerResult`` carries no ``owner`` field, so ownership lives on
    the registry ``ProducerSpec``, and every consumer that wants to *name* an
    owner joins the two. One definition of that join lives in ``gate`` and both
    the refresh summary and the gate report use it, so the two can never disagree
    about who owns a producer. The map carries one entry the refresh summary never
    looks up (the context-impact validator, which is not a producer); an unused
    key is harmless, a second copy of the join would not be.
    """
    return gate_module.owner_by_producer_id()


def _refresh_summary(result: orchestrator.RefreshResult) -> dict:
    owners = _owner_by_producer_id()
    return {
        "operation_id": result.operation_id,
        "outcome": result.outcome.value,
        "manifest_path": result.manifest_path,
        "manifest_sha256": result.manifest_sha256,
        "semantic_index": (
            result.semantic_index.to_dict() if result.semantic_index else None
        ),
        "producer_results": [
            {**r.to_dict(), "owner": owners.get(r.producer_id)}
            for r in result.producer_results
        ],
    }


def _refresh(
    repository: Path,
    revision: str,
    producer_ids: list[str] | None,
    *,
    check: bool,
    sync_point: bool = False,
    defer_semantic_index: bool = False,
) -> int:
    if check:
        result = orchestrator.check(
            repository, revision=revision, producer_ids=producer_ids
        )
    else:
        if sync_point:
            _require_sync_point_mutation(repository)
        else:
            _require_mutation(repository)
        # Without this the production path always took the ``None`` default, so
        # the semantic index was reported ``not-configured`` even when the
        # service was available — pinning every refresh to ``degraded``. The
        # factory still returns ``None`` when indexing is unconfigured, which is
        # the correct not-configured degradation on a machine without the stack.
        result = orchestrator.generate(
            repository,
            revision=revision,
            producer_ids=producer_ids,
            semantic_indexer=default_semantic_indexer(),
            defer_semantic_index=defer_semantic_index,
        )
    sys.stdout.write(json.dumps(_refresh_summary(result), indent=2) + "\n")
    return result.exit_code()


def _gate(repository: Path, revision: str, args: argparse.Namespace) -> int:
    """Run the composed drift gate and emit its report (ri-10 D1/D5).

    A thin wrapper on purpose: composition, classification, and rendering all
    live in ``gate.py`` so that ``make context-drift-gate`` reproduces a CI
    failure verbatim rather than approximating it. The canonical JSON report goes
    to stdout, where a caller can parse it; the human summary — which names every
    stale artifact on its own line — goes to stderr, so a failing build log is
    readable without a JSON tool and stdout stays machine-parsable.

    The gate is read-only, so unlike ``refresh`` there is no checkout-policy
    guard: there is no mutation to refuse.
    """
    try:
        result = gate_module.run_gate(
            repository,
            revision=revision,
            base=args.base,
            changed_files=tuple(args.changed_files) if args.changed_files else None,
            rules=args.rules,
        )
    except gate_module.GateError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    sys.stdout.write(json.dumps(result.report, indent=2, sort_keys=True) + "\n")
    sys.stderr.write(gate_module.render_text(result.report) + "\n")
    return result.exit_code


def _checkpoint(repository: Path, revision: str, args: argparse.Namespace) -> int:
    """Produce one branch-local checkpoint report for one work package (ri-09).

    Refuses a shared checkout first: the report is a tracked file, so writing it
    outside a managed worktree is the same mutation the guard exists to stop.

    The exit code is the D8 contract in one line — 0 whenever a valid report was
    produced, *including* when producers report drift. Turning drift into a
    failure belongs to the drift-gate capability, which consumes this report; a
    gate here would give it something to rework rather than a signal to use.
    """
    _require_mutation(repository)
    try:
        rules = checkpoint.load_impact_rules(args.rules)
        package = checkpoint.load_package(repository, args.change_id, args.package_id)
        merge_base = args.merge_base or checkpoint.resolve_merge_base(
            repository,
            integration_branch=args.integration_branch,
            revision=revision,
        )
        result = checkpoint.run_checkpoint(
            repository,
            change_id=args.change_id,
            package_id=args.package_id,
            package=package,
            changed_files=tuple(args.changed_files or ()),
            revision=revision,
            merge_base=merge_base,
            rules=rules,
        )
    except checkpoint.CheckpointError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    # An envelope, not the report: ``report_path``/``changed``/``decision`` are
    # caller ergonomics and would fail the report schema's closed object.
    sys.stdout.write(
        json.dumps(
            {
                "report_path": result.report_path,
                "changed": result.changed,
                "decision": result.decision.to_dict(),
                "report": result.report,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


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
        if command != "refresh":
            # ``refresh-check`` writes nothing, so it has no mutation to
            # authorize and no index attempt to defer.
            continue
        p.add_argument(
            "--sync-point",
            action="store_true",
            help=(
                "Authorize this run as an explicit sync-point mutation, allowing "
                "it to write in the shared checkout. Off by default and never "
                "inferred from the environment; the caller must still enforce "
                "its own clean-tree and active-agent guards."
            ),
        )
        p.add_argument(
            "--defer-semantic-index",
            action="store_true",
            help=(
                "Skip the inline semantic-index attempt and record it as pending "
                "with an exact-search fallback, for a caller that enqueues the "
                "index itself against a later revision. Off by default. A pending "
                "index degrades the run (exit 2); it never reports success."
            ),
        )

    gp = sub.add_parser(
        "gate",
        help=(
            "composed, read-only deterministic drift gate "
            "(exit 0 fresh / 2 blocking drift / 1 apparatus failure)"
        ),
    )
    gp.add_argument(
        "--base",
        default=gate_module.DEFAULT_BASE,
        help=(
            "Git ref the diff under test is taken against. Resolved to exactly "
            "one revision -- origin/<ref> when it resolves, else the local ref -- "
            "which scopes work-package context-impact validation and identifies "
            "the tree the verdict was compared against. The report records it as "
            "base_resolved_revision."
        ),
    )
    gp.add_argument(
        "--changed-file",
        action="append",
        dest="changed_files",
        metavar="PATH",
        help=(
            "Repository-relative changed path (repeatable). Overrides the git "
            "diff, so the gate also works on an uncommitted worktree."
        ),
    )
    gp.add_argument(
        "--rules",
        default=None,
        help="Override path to the ri-08 context-impact rule table.",
    )

    cp = sub.add_parser(
        "checkpoint",
        help=(
            "branch-local, read-only context checkpoint for one work package "
            "(never writes the refresh ledger; drift exits 0)"
        ),
    )
    cp.add_argument("--change-id", required=True, help="OpenSpec change id.")
    cp.add_argument("--package-id", required=True, help="Work package id.")
    cp.add_argument(
        "--changed-file",
        action="append",
        dest="changed_files",
        metavar="PATH",
        help=(
            "Repository-relative path this package changed (repeatable). The "
            "checkpoint never derives this from a git range, so it works on an "
            "uncommitted worktree."
        ),
    )
    cp.add_argument(
        "--merge-base",
        default=None,
        help="Full SHA to diff architecture against (default: resolved from --integration-branch).",
    )
    cp.add_argument(
        "--integration-branch",
        default=checkpoint.DEFAULT_INTEGRATION_BRANCH,
        help="Branch to resolve the architecture-diff merge base from.",
    )
    cp.add_argument(
        "--rules",
        default=None,
        help="Override path to the ri-08 context-impact rule table.",
    )

    args = parser.parse_args(argv)
    repository = args.repo.resolve()

    if args.command == "list":
        sys.stdout.write(
            json.dumps([spec.to_dict() for spec in list_producers()], indent=2) + "\n"
        )
        return 0

    revision = _resolve_revision(repository, args.revision)
    if args.command == "gate":
        return _gate(repository, revision, args)
    if args.command == "checkpoint":
        return _checkpoint(repository, revision, args)
    if args.command in ("refresh", "refresh-check"):
        return _refresh(
            repository,
            revision,
            args.producers,
            check=args.command == "refresh-check",
            # ``refresh-check`` never defines these; ``False`` is both the
            # argparse default and the pre-change behaviour.
            sync_point=getattr(args, "sync_point", False),
            defer_semantic_index=getattr(args, "defer_semantic_index", False),
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
