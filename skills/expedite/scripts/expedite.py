"""Expediter — readiness gate for sync-point operations.

Inspects a change's active-agent guard, validation-report.md, and
rework-report.json to produce a binary verdict (READY / BLOCKED).

Does NOT mutate state. The expediter is the kitchen-brigade role
implementation called out in docs/mental-models.md gap G2 — a first-class
readonly gate that refuses outgoing work that is not ready.

Use::

    python skills/expedite/scripts/expedite.py <change-id>
    python skills/expedite/scripts/expedite.py <change-id> --json
    python skills/expedite/scripts/expedite.py <change-id> \\
        --validation-report path/to/validation-report.md \\
        --rework-report path/to/rework-report.json
    python skills/expedite/scripts/expedite.py <change-id> \\
        --accept-missing-validation "<reason>"

A missing validation report blocks, and so does one that cannot be read.
``--accept-missing-validation`` accepts its absence with a recorded,
non-blank reason; it never masks a report that exists.

Default report paths probed (in order)::

    openspec/changes/<change-id>/validation-report.md
    openspec/changes/<change-id>/reports/validation-report.md
    .git-worktrees/<change-id>/openspec/changes/<change-id>/validation-report.md

Exit codes::

    0  READY    — no blocking checks
    1  BLOCKED  — at least one check failed
    2  usage error (including a blank --accept-missing-validation reason)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve()
SKILLS_DIR = THIS.parent.parent.parent
sys.path.insert(0, str(SKILLS_DIR / "shared"))
sys.path.insert(0, str(SKILLS_DIR / "validate-feature" / "scripts"))

import active_agents  # noqa: E402
import gate_logic  # noqa: E402
import rework_report as rr  # noqa: E402

# Mirrors gate_logic.pre_merge_gate's "FORCED OVERRIDE —" so one grep for
# "OVERRIDE —" finds every accepted bypass.
OVERRIDE_PREFIX = "OVERRIDE — no validation report accepted: "


@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "skip"
    detail: str = ""
    action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    change_id: str
    ready: bool
    checks: list[CheckResult] = field(default_factory=list)
    overrides: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "ready": self.ready,
            "checks": [c.to_dict() for c in self.checks],
            "overrides": list(self.overrides),
        }


def _candidate_paths(change_id: str, repo_root: Path, filename: str) -> list[Path]:
    # The last entry is where /validate-feature writes when it runs inside the
    # change's worktree, so a run from the shared checkout still finds it.
    return [
        repo_root / "openspec" / "changes" / change_id / filename,
        repo_root / "openspec" / "changes" / change_id / "reports" / filename,
        repo_root / ".git-worktrees" / change_id / "openspec" / "changes" / change_id / filename,
    ]


def _override_reason(accept_missing: str | None) -> str | None:
    """A blank or whitespace-only reason is no override at all."""
    if accept_missing is None or not accept_missing.strip():
        return None
    return accept_missing


def _probe_paths(change_id: str, repo_root: Path, filename: str) -> Path | None:
    candidates = _candidate_paths(change_id, repo_root, filename)
    return next((p for p in candidates if p.is_file()), None)


def find_validation_report(change_id: str, repo_root: Path) -> Path | None:
    return _probe_paths(change_id, repo_root, "validation-report.md")


def find_rework_report(change_id: str, repo_root: Path) -> Path | None:
    return _probe_paths(change_id, repo_root, "rework-report.json")


def check_active_agents(repo_root: Path) -> CheckResult:
    clear, active = active_agents.check_no_active_agents(repo_root=repo_root)
    if clear:
        return CheckResult(name="active_agents", status="pass",
                           detail="no active agents hold worktrees")
    labels = ", ".join(a.label for a in active)
    return CheckResult(name="active_agents", status="fail",
                       detail=f"{len(active)} active agent(s): {labels}",
                       action="wait, or pass --force to /cleanup-feature after confirming with operator")


def check_validation_report(
    report_path: Path | None,
    *,
    change_id: str,
    repo_root: Path,
    accept_missing: str | None = None,
) -> CheckResult:
    accept_missing = _override_reason(accept_missing)
    if report_path is None and accept_missing is not None:
        return CheckResult(name="validation_report", status="pass",
                           detail=OVERRIDE_PREFIX + accept_missing)
    if report_path is None:
        probed = ", ".join(
            p.relative_to(repo_root).as_posix()
            for p in _candidate_paths(change_id, repo_root, "validation-report.md")
        )
        return CheckResult(name="validation_report", status="fail",
                           detail=f"no validation-report.md at any probed path ({probed})",
                           action="run /validate-feature")
    # Derive change_dir from the change id, not the report location: a report
    # under reports/ or in a worktree must still see the change's metadata.
    change_dir_path = repo_root / "openspec" / "changes" / change_id
    change_dir = change_dir_path if change_dir_path.is_dir() else None
    try:
        action, reason, _details = gate_logic.pre_merge_gate(
            str(report_path), force=False, change_dir=change_dir,
        )
    except Exception as exc:  # unreadable report: fail closed, keep the verdict
        return CheckResult(name="validation_report", status="fail",
                           detail=f"failed to read {report_path.name}: "
                                  f"{exc.__class__.__name__}: {exc}",
                           action="inspect the report, then re-run /validate-feature")
    if action == "continue":
        return CheckResult(name="validation_report", status="pass",
                           detail=f"hard gates pass ({report_path.name})")
    return CheckResult(name="validation_report", status="fail",
                       detail=reason,
                       action="re-run /validate-feature; if hard-gate failure was investigated and accepted, pass --force at merge time")


def check_rework_report(report_path: Path | None) -> CheckResult:
    if report_path is None:
        return CheckResult(name="rework_report", status="skip",
                           detail="no rework-report.json at any candidate path")
    try:
        report = rr.load_rework_report(report_path)
    except Exception as exc:
        return CheckResult(name="rework_report", status="fail",
                           detail=f"failed to load: {exc.__class__.__name__}: {exc}",
                           action="inspect rework-report.json manually")
    action = report.summary_action
    total = report.total_failures
    holdout = report.holdout_failures
    if action == rr.ACTION_NONE:
        return CheckResult(name="rework_report", status="pass",
                           detail="no failures in rework report")
    if action == rr.ACTION_BLOCK_CLEANUP:
        return CheckResult(name="rework_report", status="fail",
                           detail=f"{holdout} holdout failure(s) — block-cleanup",
                           action="iterate on the failures, then re-validate; merge is blocked until clean")
    if action == rr.ACTION_ITERATE:
        return CheckResult(name="rework_report", status="fail",
                           detail=f"{total} failure(s) — iterate recommended",
                           action="run /iterate-on-implementation, then re-validate")
    if action == rr.ACTION_REVISE_SPEC:
        return CheckResult(name="rework_report", status="fail",
                           detail=f"{total} failure(s) — spec revision recommended",
                           action="run /update-specs or revise the proposal, then re-validate")
    if action == rr.ACTION_DEFER:
        return CheckResult(name="rework_report", status="pass",
                           detail=f"{total} failure(s) — deferred (non-blocking)")
    return CheckResult(name="rework_report", status="fail",
                       detail=f"unknown summary_action: {action!r}",
                       action="inspect rework-report.json")


def expedite(
    change_id: str,
    repo_root: Path,
    *,
    validation_report: Path | None = None,
    rework_report_path: Path | None = None,
    accept_missing_validation: str | None = None,
) -> Verdict:
    if validation_report is None:
        validation_report = find_validation_report(change_id, repo_root)
    if rework_report_path is None:
        rework_report_path = find_rework_report(change_id, repo_root)

    checks = [
        check_active_agents(repo_root),
        check_validation_report(validation_report, change_id=change_id,
                                repo_root=repo_root,
                                accept_missing=accept_missing_validation),
        check_rework_report(rework_report_path),
    ]
    accept_missing_validation = _override_reason(accept_missing_validation)
    overrides: list[dict[str, str]] = []
    if validation_report is None and accept_missing_validation is not None:
        overrides.append({"check": "validation_report",
                          "reason": accept_missing_validation})
    ready = all(c.status != "fail" for c in checks)
    return Verdict(change_id=change_id, ready=ready, checks=checks,
                   overrides=overrides)


def render_text(v: Verdict) -> str:
    marker_for = {"pass": "[ok]", "fail": "[fail]", "skip": "[skip]"}
    lines = [
        f"Change: {v.change_id}",
        f"Verdict: {'READY' if v.ready else 'BLOCKED'}",
        "",
    ]
    for c in v.checks:
        marker = marker_for.get(c.status, "[?]")
        lines.append(f"  {marker} {c.name}: {c.detail}")
        if c.action:
            lines.append(f"        action: {c.action}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Readiness gate for sync-point operations"
    )
    p.add_argument("change_id", help="OpenSpec change-id")
    p.add_argument("--repo-root", type=Path, default=Path.cwd(),
                   help="repository root (default: cwd)")
    p.add_argument("--validation-report", type=Path, default=None,
                   help="path to validation-report.md (default: probe candidate paths)")
    p.add_argument("--rework-report", type=Path, default=None,
                   help="path to rework-report.json (default: probe candidate paths)")
    p.add_argument("--accept-missing-validation", metavar="REASON", default=None,
                   help="accept a missing validation report, recording REASON "
                        "(ignored when a report exists)")
    p.add_argument("--json", action="store_true",
                   help="emit JSON to stdout instead of human text")
    args = p.parse_args(argv)
    if (args.accept_missing_validation is not None
            and not args.accept_missing_validation.strip()):
        p.error("--accept-missing-validation requires a non-empty reason")

    verdict = expedite(
        args.change_id,
        args.repo_root,
        validation_report=args.validation_report,
        rework_report_path=args.rework_report,
        accept_missing_validation=args.accept_missing_validation,
    )

    if args.json:
        json.dump(verdict.to_dict(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(verdict) + "\n")

    return 0 if verdict.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
