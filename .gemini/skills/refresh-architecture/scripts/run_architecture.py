#!/usr/bin/env python3
"""Run the architecture refresh pipeline against an arbitrary target directory."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


SCRIPTS_DIR = Path(__file__).resolve().parent
REFRESH_SCRIPT = SCRIPTS_DIR / "refresh_architecture.sh"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run architecture analysis using this repository's tooling against "
            "a target project directory."
        )
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Directory to analyze (used as working directory; default: current directory)",
    )
    parser.add_argument("--python-src-dir", help="Override PYTHON_SRC_DIR for analysis")
    parser.add_argument("--ts-src-dir", help="Override TS_SRC_DIR for analysis")
    parser.add_argument("--migrations-dir", help="Override MIGRATIONS_DIR for analysis")
    parser.add_argument("--arch-dir", help="Override ARCH_DIR output directory")
    parser.add_argument("--python", help="Python interpreter for the pipeline (maps to PYTHON)")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip Layer 3 report/view generation",
    )
    return parser.parse_args(argv)


def build_env(args: argparse.Namespace) -> dict[str, str]:
    """Build child-process environment for refresh_architecture.sh."""
    env = dict(os.environ)
    env["SCRIPTS_DIR"] = str(SCRIPTS_DIR)

    overrides = {
        "PYTHON_SRC_DIR": args.python_src_dir,
        "TS_SRC_DIR": args.ts_src_dir,
        "MIGRATIONS_DIR": args.migrations_dir,
        "ARCH_DIR": args.arch_dir,
        "PYTHON": args.python,
    }
    for key, value in overrides.items():
        if value is not None:
            env[key] = value

    return env


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    target_dir = Path(args.target_dir).expanduser().resolve()

    if not target_dir.is_dir():
        print(f"ERROR: target directory not found: {target_dir}", file=sys.stderr)
        return 2

    if not REFRESH_SCRIPT.is_file():
        print(f"ERROR: refresh script not found: {REFRESH_SCRIPT}", file=sys.stderr)
        return 2

    env = build_env(args)
    # Use bash explicitly so execution does not depend on executable bit state.
    cmd = ["bash", str(REFRESH_SCRIPT)]
    if args.quick:
        cmd.append("--quick")

    try:
        result = subprocess.run(cmd, cwd=target_dir, env=env, check=False)
    except OSError as exc:
        print(f"ERROR: failed to launch refresh script: {exc}", file=sys.stderr)
        return 1

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
