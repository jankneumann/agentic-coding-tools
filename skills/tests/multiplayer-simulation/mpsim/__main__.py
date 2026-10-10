"""``python -m mpsim`` / ``bin/mpsim``: the CLI per ``openspec/contracts/multiplayer-simulation/cli/mpsim.yaml``.

Exit codes: 0 ran to completion, 1 scenario could not be established (report with
``error`` printed), 2 argparse usage error, 64 semantic usage error (EX_USAGE).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mpsim.errors import UsageError
from mpsim.runner import DEFAULT_TICK_BUDGET, run
from mpsim.scenarios import scenario_ids

EX_USAGE = 64


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpsim", description="Deterministic, offline multi-player simulation driver."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="print the built-in scenario ids as a JSON array")
    run_cmd = commands.add_parser("run", help="run one scenario and print its report")
    run_cmd.add_argument("--scenario", required=True, help="built-in scenario id (see `list`)")
    run_cmd.add_argument("--probe", action="append", default=None,
                         help="restrict the run to this registered probe (repeatable)")
    run_cmd.add_argument("--tick-budget", type=int, default=DEFAULT_TICK_BUDGET,
                         help="maximum logical ticks (default %(default)s)")
    run_cmd.add_argument("--fixture-dir", type=Path, default=None,
                         help="replace the scenario's built-in fixture directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        sys.stdout.write(json.dumps(scenario_ids()) + "\n")
        return 0
    try:
        result = run(
            args.scenario,
            probe_ids=args.probe,
            tick_budget=args.tick_budget,
            fixture_dir=args.fixture_dir,
        )
    except UsageError as exc:
        sys.stderr.write(f"mpsim: usage error: {exc}\n")
        return EX_USAGE
    sys.stdout.write(result.text)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
