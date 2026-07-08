"""CLI entry point: run a scenario suite and emit findings.

    python -m agent_scenarios --scenarios <dir> --target <change-id> [--out findings.json]

In-container this runs with the fake executor disabled (no vendor CLIs), so the
default CLI is a dry lister/validator; the GX10 wiring injects real per-vendor
CLI commands via a config file. Kept intentionally thin — the library is the
product; this is a convenience.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .loader import load_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_scenarios")
    parser.add_argument("--scenarios", required=True, help="directory of *.scenario.yaml")
    parser.add_argument(
        "--validate-only", action="store_true", help="load+validate scenarios, no run"
    )
    args = parser.parse_args(argv)

    scenarios = load_scenarios(Path(args.scenarios))
    if not scenarios:
        print(f"no scenarios found under {args.scenarios}", file=sys.stderr)
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
    if args.validate_only:
        print(f"validated {len(scenarios)} scenario(s)", file=sys.stderr)
        return 0
    print(
        "no vendor CLIs configured in this environment; inject a ScenarioExecutor "
        "and call agent_scenarios.run_scenarios(...) to execute.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
