#!/usr/bin/env python3
"""Terminal gate for add-agy-grok-pi-harnesses: prove the roster migration is complete.

Replaces the original `grep -rl ... | test -z` gate, which PLAN_REVIEW round 1
rejected on two counts (findings C1, C3, confirmed by both claude and codex):

  * `grep -r` descends into `.venv`, so the command returned 240 files under
    system grep versus 68 under a `.gitignore`-aware wrapper. The gate could
    never pass outside one particular shell.
  * The `--include` allow-list omitted `*.md` and extensionless files, hiding
    64 tracked files including `agent-coordinator/Makefile`.

A first correction went repo-wide and was *also* unsatisfiable: design decision
D6 defers 44 narrative-prose files to a follow-up change, so a repo-wide
assertion can never go green either.

This gate therefore checks three separate properties:

  1. **In-scope clean** — every path in `in-scope.txt` is free of gemini
     references. This is the completion criterion.
  2. **Carve-outs intact** — files that must NOT be edited are unmodified
     relative to the merge base. Applied SQL migrations seed `gemini_local`
     profile rows; rewriting them desynchronizes deployed databases from their
     migration history. Review-provenance annotations record which vendor
     raised a past finding; rewriting them falsifies the record.
  3. **Deferred set reported** — the out-of-scope count is printed, never
     asserted, so the follow-up's size stays visible instead of silently
     drifting.

`git grep` is mandatory: it searches tracked files only (no venvs, no
`node_modules`) and `-I` skips binaries so stale `__pycache__/*.pyc` cannot trip
the gate (finding U6).

Usage:
    python3 check_roster_residue.py [--manifest PATH] [--base main]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PATTERN = r"gemini\|Gemini\|GEMINI"

CARVE_OUTS = [
    "agent-coordinator/database/migrations/",
    "docs/merge-logs/",
    "docs/decisions/",
    "docs/archive/",
    "apps/kanban-viz/src/lib/coordinator-types.ts",
    "apps/kanban-viz/src/hooks/useCoordinator.ts",
    "apps/kanban-viz/src/__tests__/useCoordinator.test.tsx",
]

# Excluded from the deferred-set count: generated mirrors and change history.
DEFERRED_EXCLUDE_PREFIXES = (
    ".claude/", ".agents/", ".codex/", ".gemini/",
    "openspec/changes/", "openspec/specs/", "openspec/roadmaps/",
    "docs/feature-discovery/", "docs/archive/", "docs/merge-logs/",
    "docs/decisions/", "agent-coordinator/database/migrations/",
)


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def load_manifest(path: Path) -> list[str]:
    paths = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(Path(__file__).parent / "in-scope.txt"))
    ap.add_argument("--base", default="main", help="merge base for carve-out diff")
    args = ap.parse_args()

    manifest = Path(args.manifest)
    if not manifest.is_file():
        print(f"FAIL: manifest {manifest} not found", file=sys.stderr)
        return 1

    in_scope = load_manifest(manifest)
    failures: list[str] = []

    # 1. In-scope files must be clean. Missing paths are fine — a file deleted
    #    by this change (gemini_jules.py, gemini_cli.py) is the goal, not a fault.
    existing = [p for p in in_scope if Path(p).exists()]
    if existing:
        _, out = run(["git", "grep", "-lI", PATTERN, "--", *existing])
        residue = [ln for ln in out.splitlines() if ln]
        if residue:
            failures.append(
                f"{len(residue)} in-scope file(s) still reference gemini:\n"
                + "\n".join(f"      {r}" for r in residue)
            )

    # 2. Carve-outs must be untouched.
    present = [c for c in CARVE_OUTS if Path(c.rstrip("/")).exists()]
    if present:
        code, out = run(["git", "diff", "--name-only", args.base, "--", *present])
        if code == 0 and out:
            failures.append(
                "carve-out file(s) were modified — these are historical record "
                "and must not be rewritten:\n"
                + "\n".join(f"      {r}" for r in out.splitlines())
            )

    # 3. Report (never assert) the deferred set.
    _, out = run(["git", "grep", "-lI", PATTERN])
    all_hits = [ln for ln in out.splitlines() if ln]
    in_scope_set = set(in_scope)
    deferred = [
        f for f in all_hits
        if f not in in_scope_set
        and not f.startswith(DEFERRED_EXCLUDE_PREFIXES)
    ]

    if failures:
        print("FAIL: roster migration incomplete:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"OK: all {len(existing)} in-scope files are free of gemini references")
    print(f"OK: {len(present)} carve-out path(s) unmodified against {args.base}")
    print(f"INFO: {len(deferred)} narrative-prose file(s) deferred to a follow-up (design D6)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
