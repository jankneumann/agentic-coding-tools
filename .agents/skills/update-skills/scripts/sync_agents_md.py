#!/usr/bin/env python3
"""Regenerate AGENTS.md as a byte-identical copy of CLAUDE.md.

Exit codes:
  0  regenerate succeeded; or --check passed (files byte-identical)
  1  CLAUDE.md missing
  2  --check failed (drift between CLAUDE.md and AGENTS.md)

Usage:
  python3 sync_agents_md.py            # regenerate AGENTS.md from CLAUDE.md
  python3 sync_agents_md.py --check    # verify byte-identity; exit 2 on drift
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

CLAUDE_FILENAME = "CLAUDE.md"
AGENTS_FILENAME = "AGENTS.md"


def _remediation_hint() -> str:
    return (
        "To fix, run: python3 skills/update-skills/scripts/sync_agents_md.py "
        "(or /update-skills)."
    )


def regenerate(root: Path) -> int:
    claude = root / CLAUDE_FILENAME
    if not claude.exists():
        print(f"ERROR: source file missing: {claude}", file=sys.stderr)
        return 1
    (root / AGENTS_FILENAME).write_bytes(claude.read_bytes())
    return 0


def check(root: Path) -> int:
    claude = root / CLAUDE_FILENAME
    agents = root / AGENTS_FILENAME
    if not claude.exists():
        print(f"ERROR: source file missing: {claude}", file=sys.stderr)
        return 1
    claude_bytes = claude.read_bytes()
    agents_bytes = agents.read_bytes() if agents.exists() else b""
    if claude_bytes == agents_bytes:
        return 0
    diff = difflib.unified_diff(
        claude_bytes.decode("utf-8", errors="replace").splitlines(keepends=True),
        agents_bytes.decode("utf-8", errors="replace").splitlines(keepends=True),
        fromfile=f"{CLAUDE_FILENAME} (expected)",
        tofile=f"{AGENTS_FILENAME} (actual)",
    )
    sys.stderr.write("".join(diff))
    sys.stderr.write(f"\n{_remediation_hint()}\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify AGENTS.md matches CLAUDE.md without modifying; exit 2 on drift.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    return check(args.root) if args.check else regenerate(args.root)


if __name__ == "__main__":
    sys.exit(main())
