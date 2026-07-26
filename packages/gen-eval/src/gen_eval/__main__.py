"""CLI entry point for gen-eval framework.

Usage:
    gen-eval --descriptor PATH [options]        # installed console script
    python -m gen_eval --descriptor PATH [...]  # equivalent module form

Both forms route through :func:`main`, the synchronous entry point named by
``[project.scripts]`` in pyproject.toml. :func:`run` holds the async pipeline
body and is the one to call from an existing event loop.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .contracts import CONTRACT_VERSION
from .openspec_seed import (  # noqa: F401  (InvalidChangeIdError re-exported for callers)
    InvalidChangeIdError,
    validate_change_id,
)
from .reports import GenEvalReport

logger = logging.getLogger(__name__)

# Exit code for usage errors per BSD sysexits.h convention. Used when
# --openspec-change fails the regex validation. Argparse's default of 2
# is not specific enough; the spec calls for 64.
EX_USAGE = 64

#: Default coverage floor: none (D10, Rule 4). A run that exits 0 today must
#: keep exiting 0 after upgrading, and gen-eval's own dogfood reports 0%
#: coverage until its descriptor is derived from its contract.
DEFAULT_MIN_COVERAGE = 0.0


def _percentage(value: str) -> float:
    """argparse type= adapter for a 0-100 percentage.

    Rejecting out-of-range values catches ``--min-coverage 800`` from someone
    thinking in basis points. That mistake fails *closed*, which is why the
    band just above zero needs its own check: ``--fail-threshold`` is a rate in
    ``[0, 1]``, so ``--min-coverage 0.8`` from someone reading the two flags
    alike is a legal 0.8% floor that any real suite clears. The run exits 0 and
    the operator reads a green build as an enforced coverage gate — the exact
    outcome the flag exists to prevent.

    Nothing legitimate lives in ``(0, 1)``. Coverage is denominated in
    operations, so the smallest non-zero reading is ``100/N`` and a sub-1%
    floor cannot separate any two outcomes. ``0`` (no floor) and ``1`` (any
    coverage at all) both remain available.
    """
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc
    if not 0.0 <= number <= 100.0:
        raise argparse.ArgumentTypeError(f"must be a percentage between 0 and 100, got {number}")
    if 0.0 < number < 1.0:
        raise argparse.ArgumentTypeError(
            f"{number} is a percent, so it means {number}% — a floor every "
            f"non-empty run clears, which would pass silently. If you meant "
            f"{number * 100:g}%, pass {number * 100:g}. If you meant no floor "
            f"at all, pass 0. Unlike --fail-threshold, this flag is not a rate."
        )
    return number


def _argparse_change_id(value: str) -> str:
    """argparse type= adapter: maps InvalidChangeIdError to argparse.ArgumentTypeError.

    Argparse will then call ``parser.error`` which exits with the configured
    status (we install a custom error handler in :func:`parse_args` that
    overrides argparse's default 2 to 64 for this specific failure).
    """
    try:
        return validate_change_id(value)
    except InvalidChangeIdError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


class _PrintContractVersionAction(argparse.Action):
    """Print the JSON Schema contract version and exit 0.

    Implemented as an Action (rather than a flag checked after parsing) so it
    fires *during* argument consumption. Argparse only enforces ``required=``
    once every argument has been consumed, so this short-circuits before
    ``--descriptor`` is demanded — the same mechanism ``--help`` and
    ``--version`` rely on.
    """

    def __init__(self, option_strings: list[str], dest: str, **kwargs: Any) -> None:
        kwargs.pop("nargs", None)
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        print(CONTRACT_VERSION)
        parser.exit(0)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gen-eval",
        description="Generator-Evaluator testing framework",
    )

    # Override argparse's default exit status (2) with EX_USAGE (64) for
    # --openspec-change validation failures, per the spec contract.
    original_error = parser.error

    def _error(message: str) -> None:
        # message is e.g. "argument --openspec-change: change-id MUST match ..."
        if "--openspec-change" in message and "change-id MUST match" in message:
            parser.print_usage(sys.stderr)
            sys.stderr.write(f"{parser.prog}: error: {message}\n")
            sys.exit(EX_USAGE)
        original_error(message)

    parser.error = _error  # type: ignore[method-assign]

    parser.add_argument(
        "--print-contract-version",
        action=_PrintContractVersionAction,
        help=(
            "Print the published JSON Schema contract version (one line) and "
            "exit 0. Lets a consumer assert at runtime that the gen-eval it "
            "found matches the contract it pinned."
        ),
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
    parser.add_argument(
        "--fail-threshold",
        type=float,
        default=0.95,
        help="Minimum pass rate to exit 0 (default: 0.95)",
    )
    parser.add_argument(
        "--min-coverage",
        type=_percentage,
        default=DEFAULT_MIN_COVERAGE,
        help=(
            "Minimum interface coverage to exit 0, as a PERCENT (0-100) — the "
            "same number the report prints, unlike --fail-threshold which is a "
            "rate. Checked independently of the pass rate: a suite that gets "
            "every answer right on a tenth of the declared surface fails this "
            "gate. Default: 0 (no coverage floor)."
        ),
    )
    parser.add_argument(
        "--openspec-change",
        type=_argparse_change_id,
        default=None,
        help=(
            "OpenSpec change-id whose Requirement+Scenario blocks augment "
            "the cli-augmented prompt as constraints. Must match "
            "^[a-zA-Z0-9_-]+$ (no path separators or shell metacharacters). "
            "Effective only with --mode cli-augmented."
        ),
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    """Run the gen-eval pipeline and return exit code.

    This is the async body. Call it directly when you already have an event
    loop; otherwise use :func:`main`, which owns ``asyncio.run``.

    Pipeline steps:
        1. Load configuration from CLI args
        2. Load and validate the interface descriptor
        3. Create transport client registry
        4. Create generator (based on --mode)
        5. Create evaluator with transport clients
        6. Create orchestrator
        7. Run scenarios and collect results
        8. Write report files
        9. Return 0 if pass_rate >= threshold, else 1
    """
    from .change_detector import ChangeDetector
    from .clients.base import TransportClientRegistry
    from .clients.cli_client import CliClient
    from .clients.http_client import HttpClient
    from .clients.wait_client import WaitClient
    from .config import GenEvalConfig
    from .descriptor import load_descriptor
    from .evaluator import Evaluator
    from .generator import TemplateGenerator
    from .hybrid_generator import HybridGenerator
    from .openspec_seed import ParsedScenario, parse_openspec_change
    from .orchestrator import GenEvalOrchestrator
    from .reports import generate_json_report, generate_markdown_report

    # 1. Build config from CLI args
    config = GenEvalConfig(
        descriptor_path=args.descriptor,
        mode=args.mode,
        cli_command=args.cli_command,
        time_budget_minutes=args.time_budget,
        sdk_budget_usd=args.sdk_budget,
        max_iterations=args.max_iterations,
        parallel_scenarios=args.parallel,
        changed_features_ref=args.changed_features_ref,
        openspec_change_id=args.openspec_change,
        report_format=args.report_format,
        fail_threshold=args.fail_threshold,
        seed_data=not args.no_services,
        no_services=args.no_services,
        categories=args.categories,
        verbose=args.verbose,
    )

    # Parse OpenSpec scenarios when requested. The flag's regex validation
    # already ran at argparse time, so args.openspec_change is guaranteed
    # to be a safe basename when set. If the change directory or specs/
    # subdir is missing, log a warning and degrade to descriptor-only
    # generation (no OpenSpec content in prompt) per spec contract.
    openspec_scenarios: list[ParsedScenario] = []
    if args.openspec_change:
        if config.mode != "cli-augmented":
            logger.warning(
                "--openspec-change is effective only in --mode cli-augmented; "
                "ignoring (current mode=%s)",
                config.mode,
            )
        else:
            change_dir = Path("openspec/changes") / args.openspec_change
            if not change_dir.exists():
                logger.warning(
                    "openspec change directory not found: %s; "
                    "continuing with descriptor-only generation",
                    change_dir,
                )
            else:
                specs_dir = change_dir / "specs"
                if not specs_dir.exists():
                    logger.warning(
                        "openspec specs directory missing: %s; "
                        "continuing with descriptor-only generation",
                        specs_dir,
                    )
                else:
                    openspec_scenarios = parse_openspec_change(change_dir)
                    if openspec_scenarios:
                        logger.info(
                            "openspec_seed: parsed %d scenario(s) from %s",
                            len(openspec_scenarios),
                            specs_dir,
                        )
                    else:
                        logger.info(
                            "no Requirement+Scenario blocks found in %s",
                            specs_dir,
                        )

    if args.verbose:
        print(f"gen-eval: loading descriptor from {args.descriptor}")

    # 2. Load descriptor — as its archetype, not as the base model. Loading
    # through InterfaceDescriptor discards `operations` on a service descriptor
    # and `commands`/`executable`/`contract` on a tool descriptor, which makes
    # every derived descriptor inert at exactly this seam.
    descriptor = load_descriptor(args.descriptor)

    if args.verbose:
        print(
            f"gen-eval: descriptor loaded — {len(descriptor.services)} services, "
            f"{descriptor.total_interface_count()} interfaces, mode={config.mode}"
        )

    # 3. Create transport client registry from descriptor services
    registry = TransportClientRegistry()
    for svc in descriptor.services:
        if svc.type == "http" and svc.base_url:
            registry.register("http", HttpClient(base_url=svc.base_url, auth=svc.auth))
        elif svc.type == "cli" and svc.command:
            registry.register("cli", CliClient(command=svc.command, json_flag=svc.json_flag))
    # Always register the wait client
    registry.register("wait", WaitClient())

    # 4. Create generator based on mode
    generator: TemplateGenerator | HybridGenerator
    if config.mode == "template-only":
        generator = TemplateGenerator(descriptor, config)
    else:
        generator = HybridGenerator(
            descriptor,
            config,
            openspec_scenarios=openspec_scenarios or None,
        )

    # 5. Create evaluator
    evaluator = Evaluator(descriptor, registry)

    # 6. Create orchestrator
    change_detector = None
    if config.changed_features_ref:
        change_detector = ChangeDetector(descriptor)

    orchestrator = GenEvalOrchestrator(
        config=config,
        descriptor=descriptor,
        generator=generator,
        evaluator=evaluator,
        change_detector=change_detector,
    )

    # 7. Run evaluation
    report = await orchestrator.run()

    if args.verbose:
        print(
            f"gen-eval: completed — {report.passed}/{report.total_scenarios} "
            f"passed ({report.pass_rate:.1%})"
        )

    # 8. Write report files
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []

    if args.report_format in ("markdown", "both"):
        md_path = output_dir / "gen-eval-report.md"
        md_path.write_text(generate_markdown_report(report))
        output_paths.append(md_path)

    if args.report_format in ("json", "both"):
        json_path = output_dir / "gen-eval-report.json"
        json_path.write_text(generate_json_report(report))
        output_paths.append(json_path)

        # Emit review-findings-conformant findings-gen-eval.json alongside
        # the existing JSON report. Required by the "Behavioral Findings
        # Schema Conformance" requirement so consensus_synthesizer.py can
        # merge gen-eval findings with scrutiny-review findings.
        from .findings_emitter import emit_findings

        failed_verdicts = [
            v for v in report.verdicts if v.status in ("fail", "error")
        ]
        findings_path = output_dir / "findings-gen-eval.json"
        emit_findings(
            failed_scenarios=failed_verdicts,
            output_path=findings_path,
            target=args.openspec_change or "gen-eval-run",
        )
        output_paths.append(findings_path)

    # Write metrics for integration with evaluation/metrics.py pipeline
    metrics = report.to_metrics()
    if metrics:
        metrics_path = output_dir / "gen-eval-metrics.json"
        metrics_path.write_text(
            json.dumps([m.to_dict() for m in metrics], indent=2)
        )
        output_paths.append(metrics_path)

    for path in output_paths:
        print(f"gen-eval: report written to {path}")

    # 9. Exit code: pass rate and coverage, gated independently.
    #
    # Read through getattr: run() is documented as callable from an existing
    # event loop, so a caller assembling its own Namespace is a supported
    # shape. Making a new attribute mandatory would break every such caller on
    # upgrade; absent means "no coverage floor", which is what they get today
    # (Rule 4).
    code, message = exit_decision(
        report,
        fail_threshold=config.fail_threshold,
        min_coverage=getattr(args, "min_coverage", DEFAULT_MIN_COVERAGE),
    )
    print(f"gen-eval: {message}")
    return code


def exit_decision(
    report: GenEvalReport,
    *,
    fail_threshold: float,
    min_coverage: float,
) -> tuple[int, str]:
    """Decide the process exit code from a finished report (D10).

    Returns ``(exit code, message)``. Pure, so the two gates can be asserted
    without running a scenario.

    The gates are independent. A pass rate says the scenarios that ran got the
    right answers; coverage says how much of the declared surface ran at all. A
    suite can be perfect at one and empty at the other — which is the vacuous
    success a coverage floor exists to catch — so a failure of either fails the
    run, and the message names every gate that tripped rather than only the
    first. An operator told ``FAIL (100.0% < 95.0%)`` when the real problem is
    coverage goes looking in the wrong place.

    A run that evaluated nothing is never a pass. ``pass_rate`` is already 0.0
    when ``total_scenarios == 0``, which fails any positive threshold — but
    ``--fail-threshold 0`` would otherwise let an empty run exit 0 and read as
    green, so the guard is explicit rather than left to threshold arithmetic.
    """
    if report.total_scenarios == 0:
        return 1, "FAIL (no scenarios were evaluated)"

    failures: list[str] = []
    if report.pass_rate < fail_threshold:
        failures.append(f"pass rate {report.pass_rate:.1%} < {fail_threshold:.1%}")
    if report.coverage_pct < min_coverage:
        failures.append(f"coverage {report.coverage_pct:.1f}% < {min_coverage:.1f}%")

    if failures:
        return 1, "FAIL (" + "; ".join(failures) + ")"

    summary = f"pass rate {report.pass_rate:.1%} >= {fail_threshold:.1%}"
    if min_coverage > 0:
        summary += f"; coverage {report.coverage_pct:.1f}% >= {min_coverage:.1f}%"
    return 0, f"PASS ({summary})"


def main() -> int:
    """Console-script entry point (``gen-eval``).

    Takes no arguments: the ``[project.scripts]`` launcher generated at install
    time calls this with an empty signature. Argument parsing and event-loop
    ownership both live here so that the installed executable and
    ``python -m gen_eval`` are the same code path.
    """
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
