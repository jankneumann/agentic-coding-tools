#!/usr/bin/env python3
"""Ownership check CLI (design D9, D14).

    check_owners.py [--repo-root DIR] [--codeowners] [--strict] [--json]

Errors exit ``1``. ``--strict`` promotes warnings to errors, never ``info``.
The ``code`` of each finding is the machine contract; consumers key on codes,
never on message text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from owners import OWNERS_RELPATH, OwnershipContext, collect_problems  # noqa: E402
from principals import SENTINEL_ID, default_repo_root  # noqa: E402

SCHEMA_VERSION = 1

#: code -> default severity (design D9).
CODES: dict[str, str] = {
    "invalid_map": "error",
    "invalid_registry": "error",
    "registry_not_found": "error",
    "unknown_owner": "error",
    "agent_as_owner": "error",
    "team_registry_without_map": "error",
    "registry_outside_repo": "error",
    "missing_github_handle": "error",
    "codeowners_disagreement": "error",
    "not_a_git_checkout": "error",
    "codeowners_unreadable": "error",
    "unowned_capability": "warning",
    "unowned_roadmap_item": "warning",
    "unknown_capability": "warning",
    "unknown_roadmap_item": "warning",
    "sentinel_principal": "warning",
    "codeowners_stale": "warning",
    "codeowners_missing": "warning",
    "orphan_managed_block": "warning",
    "no_ownership_map": "info",
}

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def make_finding(code: str, subject: str, message: str, severity: str | None = None) -> dict[str, str]:
    return {
        "severity": severity or CODES[code],
        "code": code,
        "subject": subject,
        "message": message,
    }


def active_roadmap_items(repo_root: Path) -> set[str]:
    """``<roadmap-id>/<item-id>`` for every item of every active (non-archive) roadmap."""
    found: set[str] = set()
    base = repo_root / "openspec" / "roadmaps"
    if not base.is_dir():
        return found
    for roadmap_file in sorted(base.glob("*/roadmap.yaml")):
        if roadmap_file.parent.name == "archive":
            continue
        try:
            data = yaml.safe_load(roadmap_file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        roadmap_id = str(data.get("roadmap_id") or roadmap_file.parent.name)
        for item in data.get("items") or []:
            if isinstance(item, dict) and item.get("item_id"):
                found.add(f"{roadmap_id}/{item['item_id']}")
    return found


def _capability_dirs(repo_root: Path) -> set[str]:
    base = repo_root / "openspec" / "specs"
    return {p.name for p in base.iterdir() if p.is_dir()} if base.is_dir() else set()


def _advisory_findings(ctx: OwnershipContext) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    capabilities = _capability_dirs(ctx.repo_root)
    roadmap_items = active_roadmap_items(ctx.repo_root)

    if not ctx.has_map:
        if ctx.solo_principal is not None and ctx.solo_principal.id == SENTINEL_ID:
            findings.append(
                make_finding(
                    "sentinel_principal",
                    SENTINEL_ID,
                    "no human principal is declared and no git identity is configured; "
                    "the sole repository principal is the 'repository-default' sentinel",
                )
            )
        return findings

    for key in ctx.capabilities:
        if key not in capabilities:
            findings.append(
                make_finding(
                    "unknown_capability",
                    key,
                    f"assignment names capability '{key}' but openspec/specs/{key}/ does not exist",
                )
            )
    for key in ctx.roadmap_items:
        if key not in roadmap_items:
            findings.append(
                make_finding(
                    "unknown_roadmap_item",
                    key,
                    f"assignment names roadmap item '{key}' which is in no active roadmap",
                )
            )
    if ctx.mode == "team":
        for name in sorted(capabilities - set(ctx.capabilities)):
            findings.append(
                make_finding(
                    "unowned_capability",
                    name,
                    f"capability '{name}' has no explicit assignment; it resolves to the default owner",
                )
            )
        for key in sorted(roadmap_items - set(ctx.roadmap_items)):
            findings.append(
                make_finding(
                    "unowned_roadmap_item",
                    key,
                    f"roadmap item '{key}' has no explicit assignment; it resolves to the default owner",
                )
            )
    return findings


def _codeowners_findings(ctx: OwnershipContext | None, repo_root: Path) -> list[dict[str, str]]:
    try:
        import codeowners
    except ImportError:  # pragma: no cover - codeowners.py ships in the same skill
        return []
    return list(codeowners.check_findings(ctx, repo_root))


def check(repo_root: Path | None = None, *, codeowners: bool = False) -> dict[str, Any]:
    """Run the check; return the report document (without ``strict``/``exit_code`` applied)."""
    root = (repo_root or default_repo_root()).resolve()
    ctx, problems = collect_problems(root)
    findings = [make_finding(p.code, p.subject, p.message) for p in problems]
    if ctx is not None:
        findings.extend(_advisory_findings(ctx))
    if codeowners:
        findings.extend(_codeowners_findings(ctx, root))
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f["severity"]], f["code"], f["subject"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": ctx.mode if ctx is not None else None,
        "strict": False,
        "exit_code": 0,
        "findings": findings,
    }


def exit_code(report: dict[str, Any], *, strict: bool) -> int:
    severities = {f["severity"] for f in report["findings"]}
    if "error" in severities or (strict and "warning" in severities):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the ownership map and principal registry.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--codeowners", action="store_true", help="also reconcile .github/CODEOWNERS")
    parser.add_argument("--strict", action="store_true", help="promote warnings to errors")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    report = check(args.repo_root, codeowners=args.codeowners)
    report["strict"] = args.strict
    report["exit_code"] = exit_code(report, strict=args.strict)
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        for f in report["findings"]:
            print(f"{f['severity']}: {f['code']}: {f['subject']}: {f['message']}")
        if not report["findings"]:
            print(f"ok ({OWNERS_RELPATH}: no findings)")
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
