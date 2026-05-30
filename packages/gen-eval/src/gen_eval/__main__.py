"""CLI entry point for gen-eval framework.

Usage:
    python -m evaluation.gen_eval --descriptor PATH [options]
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .openspec_seed import (  # noqa: F401  (InvalidChangeIdError re-exported for callers)
    InvalidChangeIdError,
    validate_change_id,
)

logger = logging.getLogger(__name__)

# Exit code for usage errors per BSD sysexits.h convention. Used when
# --openspec-change fails the regex validation. Argparse's default of 2
# is not specific enough; the spec calls for 64.
EX_USAGE = 64


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


async def main(args: argparse.Namespace) -> int:
    """Run the gen-eval pipeline and return exit code.

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
    from .descriptor import InterfaceDescriptor
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

    # 2. Load descriptor
    descriptor = InterfaceDescriptor.from_yaml(args.descriptor)

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

    # 9. Exit code based on pass rate
    if report.pass_rate >= config.fail_threshold:
        print(f"gen-eval: PASS ({report.pass_rate:.1%} >= {config.fail_threshold:.1%})")
        return 0
    else:
        print(f"gen-eval: FAIL ({report.pass_rate:.1%} < {config.fail_threshold:.1%})")
        return 1


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
