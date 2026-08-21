#!/usr/bin/env python3
"""Audit driver for the audit-choices skill.

Ties together `collect_evidence.py` (evidence bundle + session-log
cross-reference resolver) and `choices_ledger.py` (stable_id, schema
validation, idempotent ledger writer, choices.md renderer).

The auditor sub-agent itself is dispatched by the orchestrating Claude
Code agent per SKILL.md — never from this module. This module only
validates and persists the candidate entries the sub-agent already
returned (D7): it drops entries whose provenance cites a commit or file
absent from the audited range, resolves each surviving candidate's
self-reported cross-reference deterministically against session-log.md,
computes each entry's content-derived stable_id, and writes the ledger
pair. No LLM SDK import anywhere in this file (host-assisted invariant).

D6 — non-blocking by construction: `run_audit()` never raises; any
internal error (missing repo, unreadable schema, git failure, ...) is
caught and reported via `AuditRunResult.ok = False` /
`AuditRunResult.error` instead. `_cli()` always returns 0 regardless of
`run_audit()`'s outcome or of the verdicts the ledger records.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import choices_ledger  # noqa: E402
import collect_evidence  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class AuditRunResult:
    """Outcome of one `run_audit()` call. `ok=False` never raises to the
    caller — it is the D6 "never blocks" signal for internal errors."""

    ok: bool
    change_id: str
    json_path: Path | None = None
    md_path: Path | None = None
    kept_count: int = 0
    dropped_count: int = 0
    dropped: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _head_sha(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def run_audit(
    *,
    repo_root: Path,
    change_id: str,
    base_sha: str,
    head_sha: str,
    candidates: list[dict[str, Any]],
    run_id: str,
    auditor: dict[str, Any] | None = None,
    now: datetime | None = None,
    git_sha: str | None = None,
) -> AuditRunResult:
    """Validate candidate entries from the auditor sub-agent and persist
    the ledger pair.

    Never raises: any internal failure is caught and reported in the
    returned result with `ok=False` (D6 — the audit never blocks, even on
    internal error). Adverse verdicts (`unsound`, `needs-user`) are
    ordinary, successful outcomes — `ok=True` regardless of what the
    entries' verdicts are.
    """
    try:
        return _run_audit_inner(
            repo_root=repo_root,
            change_id=change_id,
            base_sha=base_sha,
            head_sha=head_sha,
            candidates=candidates,
            run_id=run_id,
            auditor=auditor,
            now=now,
            git_sha=git_sha,
        )
    except Exception as exc:  # noqa: BLE001 - D6: the audit never blocks
        logger.warning("audit-choices: internal error, ledger not updated: %s", exc)
        return AuditRunResult(ok=False, change_id=change_id, error=str(exc))


def _resolve_entry(
    candidate: dict[str, Any], known_decisions: list[dict[str, str]]
) -> dict[str, Any]:
    """Fill in the fields the script — not the sub-agent — is responsible
    for: the self-reported cross-reference (D5) and the content-derived
    stable_id (D3). Any self_reported/session_log_ref the candidate
    already carried is replaced, since only the deterministic resolver's
    answer is trustworthy provenance for those two fields."""
    entry = dict(candidate)
    self_reported, ref = collect_evidence.resolve_self_reported(
        entry.get("choice", ""), known_decisions
    )
    entry["self_reported"] = self_reported
    if self_reported and ref:
        entry["session_log_ref"] = ref
    else:
        entry.pop("session_log_ref", None)

    provenance = entry.get("provenance") or {}
    entry["stable_id"] = choices_ledger.compute_stable_id(
        choice=entry.get("choice", ""),
        files=provenance.get("files", []),
        gap=entry.get("gap", ""),
    )
    return entry


def _run_audit_inner(
    *,
    repo_root: Path,
    change_id: str,
    base_sha: str,
    head_sha: str,
    candidates: list[dict[str, Any]],
    run_id: str,
    auditor: dict[str, Any] | None,
    now: datetime | None,
    git_sha: str | None,
) -> AuditRunResult:
    change_dir = repo_root / "openspec" / "changes" / change_id

    bundle = collect_evidence.collect_evidence(
        repo_root, change_id=change_id, base_sha=base_sha, head_sha=head_sha
    )

    # D7 hallucination guard: drop anything citing a commit/file outside
    # the audited range before it gets anywhere near persistence.
    kept_provenance, dropped_provenance = choices_ledger.filter_valid_provenance(
        candidates, known_commits=bundle.known_commits, known_files=bundle.known_files
    )

    resolved = [_resolve_entry(candidate, bundle.known_decisions) for candidate in kept_provenance]

    # Second validation pass: entries missing a required field or carrying
    # a bad enum value are dropped too, not persisted half-formed.
    valid_entries, invalid_entries = choices_ledger.split_schema_valid(resolved)
    dropped_all = dropped_provenance + invalid_entries

    resolved_now = now or datetime.now(timezone.utc)
    resolved_git_sha = git_sha or _head_sha(repo_root)
    header = choices_ledger.make_header(now=resolved_now, git_sha=resolved_git_sha, run_id=run_id)

    json_path, md_path = choices_ledger.write_ledger_pair(
        change_dir,
        header=header,
        change_id=change_id,
        audited_range={"base_sha": base_sha, "head_sha": head_sha},
        entries=valid_entries,
        auditor=auditor,
    )

    return AuditRunResult(
        ok=True,
        change_id=change_id,
        json_path=json_path,
        md_path=md_path,
        kept_count=len(valid_entries),
        dropped_count=len(dropped_all),
        dropped=dropped_all,
    )


def _cli() -> int:
    """CLI wrapper: reads candidate entries JSON, writes the ledger pair.
    D6: always returns 0, printing a warning to stderr on internal error
    (never on adverse verdicts, which are a normal, successful outcome)."""
    import argparse

    p = argparse.ArgumentParser(description="audit-choices ledger driver")
    p.add_argument("--change-id", required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument(
        "--candidates", default="-", help="candidate entries JSON array (default: stdin)"
    )
    p.add_argument("--repo-root", default=".")
    args = p.parse_args()

    try:
        if args.candidates == "-":
            candidates = json.load(sys.stdin)
        else:
            candidates = json.loads(Path(args.candidates).read_text())
    except Exception as exc:  # noqa: BLE001 - D6: never blocks, even on bad input
        print(f"audit-choices: WARNING - could not read candidates: {exc}", file=sys.stderr)
        return 0

    result = run_audit(
        repo_root=Path(args.repo_root).resolve(),
        change_id=args.change_id,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
        candidates=candidates,
        run_id=args.run_id,
    )
    if result.ok:
        print(
            f"audit-choices: wrote {result.json_path} "
            f"({result.kept_count} entries, {result.dropped_count} dropped)"
        )
    else:
        print(f"audit-choices: WARNING - {result.error}", file=sys.stderr)
    return 0  # D6: never blocks


if __name__ == "__main__":
    raise SystemExit(_cli())
