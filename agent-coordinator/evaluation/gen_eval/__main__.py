"""CLI entry point for gen-eval framework.

Usage:
    python -m evaluation.gen_eval --descriptor PATH [options]
"""

import argparse
import asyncio
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gen-eval",
        description="Generator-Evaluator testing framework",
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        required=True,
        help="Path to interface descriptor YAML",
    )
    parser.add_argument(
        "--mode",
        choices=["template-only", "cli-augmented", "sdk-only"],
        default="template-only",
        help="Generator mode (default: template-only)",
    )
    parser.add_argument(
        "--cli-command",
        default="claude",
        help="CLI tool for cli-augmented mode: claude or codex (default: claude)",
    )
    parser.add_argument(
        "--time-budget",
        type=float,
        default=60.0,
        help="Time budget in minutes for CLI mode (default: 60.0)",
    )
    parser.add_argument(
        "--sdk-budget",
        type=float,
        help="USD budget cap for SDK mode",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Feedback loop iterations (default: 1)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=5,
        help="Concurrent scenario execution (default: 5)",
    )
    parser.add_argument(
        "--changed-features-ref",
        help="Git ref for change detection (filters scenarios to changed features)",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help="Filter to specific scenario categories",
    )
    parser.add_argument(
        "--report-format",
        choices=["markdown", "json", "both"],
        default="both",
        help="Report output format (default: both)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Report output directory (default: current directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--no-services",
        action="store_true",
        help="Skip service startup/teardown (assume services already running)",
    )
    return parser.parse_args(argv)


async def main(args: argparse.Namespace) -> int:
    """Run the gen-eval pipeline and return exit code.

    Pipeline steps:
        1. Load configuration from CLI args
        2. Load and validate the interface descriptor
        3. Create generator (based on --mode)
        4. Create evaluator with transport clients
        5. Create orchestrator
        6. Run scenarios and collect results
        7. Write report files
        8. Return 0 if pass_rate >= threshold, else 1
    """
    from .config import GenEvalConfig
    from .descriptor import load_descriptor
    from .orchestrator import Orchestrator
    from .reports import write_reports

    # 1. Build config from CLI args
    config = GenEvalConfig.from_args(args)

    if args.verbose:
        print(f"gen-eval: loading descriptor from {args.descriptor}")

    # 2. Load descriptor
    descriptor = load_descriptor(args.descriptor)

    if args.verbose:
        print(
            f"gen-eval: descriptor loaded — {len(descriptor.features)} features, "
            f"mode={config.mode}"
        )

    # 3-5. Create orchestrator (encapsulates generator + evaluator setup)
    orchestrator = Orchestrator(config=config, descriptor=descriptor)

    # 6. Run evaluation
    report = await orchestrator.run()

    if args.verbose:
        print(
            f"gen-eval: completed — {report.scenarios_passed}/{report.scenarios_total} "
            f"passed ({report.pass_rate:.1%})"
        )

    # 7. Write report files
    output_paths = write_reports(
        report=report,
        output_dir=args.output_dir,
        formats=args.report_format,
    )
    for path in output_paths:
        print(f"gen-eval: report written to {path}")

    # 8. Exit code based on pass rate
    if report.pass_rate >= config.fail_threshold:
        print(f"gen-eval: PASS ({report.pass_rate:.1%} >= {config.fail_threshold:.1%})")
        return 0
    else:
        print(f"gen-eval: FAIL ({report.pass_rate:.1%} < {config.fail_threshold:.1%})")
        return 1


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
