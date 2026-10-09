#!/usr/bin/env python3
"""``.github/CODEOWNERS`` as a derived projection of ``openspec/owners.yaml`` (design D8).

    codeowners.py emit      [--repo-root DIR] [--write] [--json]
    codeowners.py reconcile [--repo-root DIR] [--json]

``emit`` renders a managed block ordered by *ascending* specificity so GitHub's
last-match-wins selection agrees with the resolver's most-specific-wins selection.
``CODEOWNERS`` is never read back into ``owners.yaml``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_owners import make_finding  # noqa: E402
from owners import OwnershipContext, Rule, collect_problems, compile_pattern  # noqa: E402
from principals import (  # noqa: E402
    OwnershipConfigError,
    Principal,
    default_repo_root,
    is_git_checkout,
)

CODEOWNERS_RELPATH = ".github/CODEOWNERS"
BEGIN_MARKER = "# BEGIN ownership-map"
END_MARKER = "# END ownership-map"
BEGIN_LINE = (
    f"{BEGIN_MARKER} (generated from openspec/owners.yaml — do not edit; "
    f"run codeowners.py emit)"
)


@dataclass(frozen=True)
class EmitLine:
    pattern: str
    handles: tuple[str, ...]


def handle(principal: Principal) -> str:
    """``@<github>``; a human without a handle makes emission fail (fail closed)."""
    if not principal.github:
        raise OwnershipConfigError(
            "missing_github_handle",
            f"principal '{principal.id}' is in an emitted owner set but has no `github` "
            f"field in the registry; add `github:` to humans.{principal.id}",
            principal.id,
        )
    return f"@{principal.github}"


def emit_lines(ctx: OwnershipContext) -> list[EmitLine]:
    """Rule lines in CODEOWNERS order: ``*`` first, then ascending specificity."""
    assert ctx.default_owner is not None
    lines = [EmitLine("*", (handle(ctx.default_owner),))]
    ordered: list[Rule] = sorted(ctx.rules, key=lambda r: r.sort_key)
    for rule in ordered:
        lines.append(
            EmitLine(rule.pattern, tuple(handle(p) for p in rule.assignment.owners))
        )
    return lines


def render_block(ctx: OwnershipContext) -> str:
    """The managed block, newline-terminated."""
    lines = emit_lines(ctx)
    width = max(len(line.pattern) for line in lines) + 2
    body = [f"{line.pattern.ljust(width)}{' '.join(line.handles)}" for line in lines]
    return "\n".join([BEGIN_LINE, *body, END_MARKER]) + "\n"


def find_block(text: str) -> tuple[int, int] | None:
    """Character span ``[start, end)`` of the managed block (through its END line)."""
    offset = 0
    start: int | None = None
    for raw in text.splitlines(keepends=True):
        stripped = raw.strip()
        if stripped.startswith(BEGIN_MARKER):
            # A later BEGIN supersedes an unterminated earlier one, so re-emitting over a
            # truncated block is idempotent.
            start = offset
        elif start is not None and stripped == END_MARKER:
            return start, offset + len(raw)
        offset += len(raw)
    return None


def splice_block(existing: str, block: str) -> str:
    """Replace only the managed block; append it when none exists. Other text is verbatim."""
    span = find_block(existing)
    if span is not None:
        return existing[: span[0]] + block + existing[span[1] :]
    if not existing:
        return block
    separator = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + separator + block


def read_codeowners(repo_root: Path) -> str | None:
    path = repo_root / CODEOWNERS_RELPATH
    if not path.is_file():
        return None
    return path.read_bytes().decode("utf-8")


def _fail(code: str, message: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"schema_version": 1, "ok": False, "code": code, "message": message}))
    else:
        print(f"error: {code}: {message}", file=sys.stderr)
    return 1


def run_emit(repo_root: Path, *, write: bool, as_json: bool) -> int:
    ctx, problems = collect_problems(repo_root)
    if problems:
        first = problems[0]
        return _fail(first.code, first.message, as_json)
    assert ctx is not None
    if not ctx.has_map:
        return _fail(
            "no_ownership_map",
            "openspec/owners.yaml does not exist; there is nothing to project "
            "(a `*` line would make CODEOWNERS an authority of its own)",
            as_json,
        )
    try:
        block = render_block(ctx)
    except OwnershipConfigError as exc:
        return _fail(exc.code, exc.message, as_json)
    path = repo_root / CODEOWNERS_RELPATH
    if write:
        existing = read_codeowners(repo_root) or ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(splice_block(existing, block).encode("utf-8"))
    if as_json:
        print(json.dumps({"schema_version": 1, "ok": True, "written": write, "block": block}))
    elif not write:
        sys.stdout.write(block)
    else:
        print(f"wrote managed block to {CODEOWNERS_RELPATH}")
    return 0


# --------------------------------------------------------------------------- reconcile


@dataclass(frozen=True)
class Entry:
    """One CODEOWNERS rule line."""

    pattern: str
    handles: tuple[str, ...]


def parse_codeowners(text: str) -> list[Entry]:
    """Rule lines of the *whole* file (managed and unmanaged), in file order."""
    entries: list[Entry] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+#.*$", "", raw.strip())
        if not line or line.startswith("#"):
            continue
        pattern, *handles = line.split()
        entries.append(Entry(pattern, tuple(handles)))
    return entries


def _entry_regex(pattern: str) -> re.Pattern[str] | None:
    """CODEOWNERS glob semantics. GitHub treats an embedded ``**`` as ``*``."""
    if pattern.startswith("!") or "[" in pattern:
        return None  # not supported by CODEOWNERS; such a line never matches
    softened = "/".join(
        seg if seg == "**" else seg.replace("**", "*") for seg in pattern.split("/")
    )
    try:
        return compile_pattern(softened)
    except OwnershipConfigError:  # pragma: no cover - softened patterns always compile
        return None


def selected_handles(entries: list[Entry], path: str) -> frozenset[str]:
    """The owners GitHub selects: the last matching line wins."""
    chosen: frozenset[str] = frozenset()
    for entry in entries:
        regex = _entry_regex(entry.pattern)
        if regex is not None and regex.fullmatch(path):
            chosen = frozenset(entry.handles)
    return chosen


def tracked_files(repo_root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if done.returncode != 0:
        return []
    return [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p]


def _literal_prefix(rule: Rule) -> str:
    pattern = rule.pattern.lstrip("/")
    cuts = [i for i in (pattern.find("*"), pattern.find("?")) if i >= 0]
    return pattern[: min(cuts)] if cuts else pattern


def build_probes(ctx: OwnershipContext, tracked: list[str]) -> list[str]:
    """Paths whose owners are compared: spec/contract files, rule matches, prefixes, one miss."""
    probes: set[str] = set()
    for path in tracked:
        if path.startswith(("openspec/specs/", "openspec/contracts/")):
            probes.add(path)
    for rule in ctx.rules:
        if not rule.implied:
            probes.update(p for p in tracked if rule.regex.fullmatch(p))
        prefix = _literal_prefix(rule)
        if prefix:
            probes.add(prefix + "probe-file" if prefix.endswith("/") else prefix)
    probes.add("zz-ownership-probe/unmatched.txt")
    return sorted(probes)


def _expected_handles(ctx: OwnershipContext, path: str) -> frozenset[str]:
    return frozenset(handle(p) for p in ctx.resolve_path(path).owners)


def _fmt(handles: frozenset[str]) -> str:
    return "{" + ", ".join(sorted(handles)) + "}" if handles else "{nobody}"


def reconcile(repo_root: Path) -> dict[str, Any]:
    """Compare ``.github/CODEOWNERS`` against the resolver; return a report document."""
    findings: list[dict[str, str]] = []
    disagreements = 0
    stale = False

    def done() -> dict[str, Any]:
        failed = any(f["severity"] == "error" for f in findings)
        return {
            "schema_version": 1,
            "disagreements": disagreements,
            "stale": stale,
            "exit_code": 1 if failed else 0,
            "findings": findings,
        }

    ctx, problems = collect_problems(repo_root)
    if problems:
        findings.extend(make_finding(p.code, p.subject, p.message) for p in problems)
        return done()
    assert ctx is not None
    text = read_codeowners(repo_root)
    span = find_block(text) if text is not None else None

    if not ctx.has_map:
        if span is not None:
            findings.append(
                make_finding(
                    "orphan_managed_block",
                    CODEOWNERS_RELPATH,
                    "CODEOWNERS has a managed ownership-map block but openspec/owners.yaml "
                    "does not exist; the projection outlived its source",
                )
            )
        else:
            findings.append(
                make_finding(
                    "no_ownership_map",
                    "openspec/owners.yaml",
                    "no ownership map; nothing to reconcile",
                )
            )
        return done()

    if not is_git_checkout(repo_root):
        findings.append(
            make_finding(
                "not_a_git_checkout",
                str(repo_root),
                "reconcile builds its probe set from `git ls-files` and needs a git checkout",
            )
        )
        return done()

    try:
        fresh = render_block(ctx)
    except OwnershipConfigError as exc:
        findings.append(make_finding(exc.code, exc.subject or "", exc.message))
        return done()

    if text is None:
        findings.append(
            make_finding(
                "codeowners_missing",
                CODEOWNERS_RELPATH,
                f"{CODEOWNERS_RELPATH} does not exist; run codeowners.py emit --write",
            )
        )
        return done()
    if span is None:
        findings.append(
            make_finding(
                "codeowners_missing",
                CODEOWNERS_RELPATH,
                "CODEOWNERS has no managed ownership-map block; run codeowners.py emit --write",
            )
        )
    elif text[span[0] : span[1]] != fresh:
        stale = True
        diff = "\n".join(
            difflib.unified_diff(
                text[span[0] : span[1]].splitlines(),
                fresh.splitlines(),
                fromfile="CODEOWNERS managed block",
                tofile="fresh emit",
                lineterm="",
            )
        )
        findings.append(
            make_finding(
                "codeowners_stale",
                CODEOWNERS_RELPATH,
                f"managed block differs from a fresh emit:\n{diff}",
            )
        )

    entries = parse_codeowners(text)
    for path in build_probes(ctx, tracked_files(repo_root)):
        expected = _expected_handles(ctx, path)
        actual = selected_handles(entries, path)
        if expected != actual:
            disagreements += 1
            rule = ctx.resolve_path(path).matched_rule or "default_owner"
            findings.append(
                make_finding(
                    "codeowners_disagreement",
                    path,
                    f"GitHub would select {_fmt(actual)} but the resolver selects "
                    f"{_fmt(expected)} (rule: {rule})",
                )
            )
    return done()


def check_findings(ctx: OwnershipContext | None, repo_root: Path) -> list[dict[str, str]]:
    """Findings for ``check_owners.py --codeowners``."""
    if ctx is None:
        return []
    findings: list[dict[str, str]] = reconcile(repo_root)["findings"]
    return findings


def run_reconcile(repo_root: Path, *, as_json: bool) -> int:
    report = reconcile(repo_root)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for f in report["findings"]:
            print(f"{f['severity']}: {f['code']}: {f['subject']}: {f['message']}")
        print(
            f"disagreements: {report['disagreements']}; "
            f"managed block {'stale' if report['stale'] else 'fresh or absent'}"
        )
    return int(report["exit_code"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project the ownership map to CODEOWNERS.")
    sub = parser.add_subparsers(dest="command", required=True)
    emit_p = sub.add_parser("emit", help="render the managed block")
    emit_p.add_argument("--write", action="store_true")
    for p in (emit_p,):
        p.add_argument("--repo-root", type=Path, default=None)
        p.add_argument("--json", action="store_true", dest="as_json")
    rec_p = sub.add_parser("reconcile", help="compare CODEOWNERS with the resolver")
    rec_p.add_argument("--repo-root", type=Path, default=None)
    rec_p.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    root = (args.repo_root or default_repo_root()).resolve()
    if args.command == "emit":
        return run_emit(root, write=args.write, as_json=args.as_json)
    if args.command == "reconcile":
        return run_reconcile(root, as_json=args.as_json)
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
