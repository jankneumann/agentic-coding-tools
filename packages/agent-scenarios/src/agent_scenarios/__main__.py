"""CLI entry point.

    agent-scenarios validate --scenarios <dir>
    agent-scenarios --scenarios <dir> [--validate-only]      # legacy form, unchanged
    agent-scenarios nightly --config <path> [--dry-run]
    agent-scenarios results {query,trend,latest} ...
    agent-scenarios gaps flush

The library is the product; this is a thin convenience. Each subcommand module owns its own
``add_parser(subparsers)``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import gap_emitter, nightly, results_cli
from .loader import load_scenarios

SUBCOMMANDS = ("validate", "nightly", "results", "gaps")


def _validate(scenarios_dir: str, *, validate_only: bool) -> int:
    scenarios = load_scenarios(Path(scenarios_dir))
    if not scenarios:
        print(f"no scenarios found under {scenarios_dir}", file=sys.stderr)
        return 2

    summary = [
        {
            "id": s.id,
            "skill_under_test": s.skill_under_test,
            "vendors": s.vendors,
            "gates": len(s.goal_gates.all_gates()),
        }
        for s in scenarios
    ]
    print(json.dumps({"scenarios": summary}, indent=2))
    if validate_only:
        print(f"validated {len(scenarios)} scenario(s)", file=sys.stderr)
        return 0
    print(
        "no vendor CLIs configured in this environment; inject a ScenarioExecutor "
        "and call agent_scenarios.run_scenarios(...) to execute.",
        file=sys.stderr,
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    return _validate(args.scenarios, validate_only=True)


def _legacy(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent-scenarios")
    parser.add_argument("--scenarios", required=True, help="directory of *.scenario.yaml")
    parser.add_argument(
        "--validate-only", action="store_true", help="load+validate scenarios, no run"
    )
    args = parser.parse_args(argv)
    return _validate(args.scenarios, validate_only=args.validate_only)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-scenarios")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="load and validate scenario files")
    validate.add_argument("--scenarios", required=True, help="directory of *.scenario.yaml")
    validate.set_defaults(func=_cmd_validate)
    nightly.add_parser(sub)
    results_cli.add_parser(sub)
    gap_emitter.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list or args_list[0] not in SUBCOMMANDS:
        if args_list and args_list[0] in ("-h", "--help"):
            build_parser().parse_args(args_list)  # prints the subcommand overview
        return _legacy(args_list)
    args = build_parser().parse_args(args_list)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
