"""Config-driven multi-vendor review dispatcher.

Dispatches review skills to vendor CLIs using configuration from
agents.yaml.  A single CliVendorAdapter class handles all vendors —
no per-vendor subclasses needed.

Usage:
    from review_dispatcher import ReviewOrchestrator

    orch = ReviewOrchestrator.from_agents_yaml(Path("agents.yaml"))
    results = orch.dispatch_and_wait(
        review_type="plan",
        dispatch_mode="review",
        prompt="Review this plan...",
        cwd=Path("/path/to/worktree"),
    )
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class ErrorClass(str, Enum):
    """Classification of vendor subprocess errors."""

    CAPACITY = "capacity_exhausted"
    AUTH = "auth_required"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


_CAPACITY_PATTERNS = ["429", "resource_exhausted", "capacity", "rate limit", "rate_limit"]
_AUTH_PATTERNS = ["401", "unauthenticated", "token expired", "login required", "unauthorized"]
_TRANSIENT_PATTERNS = ["500", "503", "unavailable", "internal server error"]

_RELOGIN_COMMANDS: dict[str, str] = {
    "codex": "codex login",
    "gemini": "gemini login",
    "claude": "claude login",
}


def classify_error(stderr: str) -> ErrorClass:
    """Classify a vendor error from stderr text."""
    lower = stderr.lower()
    if any(p in lower for p in _AUTH_PATTERNS):
        return ErrorClass.AUTH
    if any(p in lower for p in _CAPACITY_PATTERNS):
        return ErrorClass.CAPACITY
    if any(p in lower for p in _TRANSIENT_PATTERNS):
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModeConfig:
    """CLI args for a single dispatch mode."""

    args: list[str]


@dataclass
class CliConfig:
    """CLI dispatch configuration for an agent."""

    command: str
    dispatch_modes: dict[str, ModeConfig]
    model_flag: str
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)


@dataclass
class ReviewerInfo:
    """Information about an available reviewer."""

    vendor: str
    agent_id: str
    cli_config: CliConfig | None = None
    available: bool = True


@dataclass
class ReviewResult:
    """Result from a vendor review dispatch."""

    vendor: str
    success: bool
    findings: dict[str, Any] | None = None
    model_used: str | None = None
    models_attempted: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: str | None = None
    error_class: ErrorClass | None = None


# ---------------------------------------------------------------------------
# Generic CLI adapter
# ---------------------------------------------------------------------------

class CliVendorAdapter:
    """Config-driven vendor adapter — one class handles all vendors."""

    def __init__(self, agent_id: str, vendor: str, cli_config: CliConfig) -> None:
        self.agent_id = agent_id
        self.vendor = vendor
        self.cli_config = cli_config

    def can_dispatch(self, mode: str) -> bool:
        """Check if this adapter can dispatch the given mode."""
        if mode not in self.cli_config.dispatch_modes:
            return False
        return shutil.which(self.cli_config.command) is not None

    def build_command(
        self,
        mode: str,
        prompt: str,
        model: str | None = None,
    ) -> list[str]:
        """Build subprocess command from config."""
        mode_config = self.cli_config.dispatch_modes[mode]
        cmd = [self.cli_config.command, *mode_config.args]
        effective_model = model or self.cli_config.model
        if effective_model:
            cmd.extend([self.cli_config.model_flag, effective_model])
        cmd.append(prompt)
        return cmd

    def dispatch(
        self,
        mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 300,
    ) -> ReviewResult:
        """Dispatch a review with model fallback on capacity errors.

        Tries the primary model first, then each fallback in order.
        Returns the first successful result or the final failure.
        """
        models_to_try: list[str | None] = [self.cli_config.model]
        models_to_try.extend(self.cli_config.model_fallbacks)

        models_attempted: list[str] = []
        last_error = ""
        last_error_class = ErrorClass.UNKNOWN

        for model in models_to_try:
            model_name = model or "(default)"
            models_attempted.append(model_name)

            cmd = self.build_command(mode, prompt, model)
            start = time.monotonic()

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=str(cwd),
                )
                elapsed = time.monotonic() - start

                if result.returncode == 0:
                    # Try to parse JSON from stdout
                    findings = self._parse_findings(result.stdout)
                    return ReviewResult(
                        vendor=self.vendor,
                        success=findings is not None,
                        findings=findings,
                        model_used=model_name,
                        models_attempted=models_attempted,
                        elapsed_seconds=elapsed,
                        error=None if findings else "Invalid JSON output",
                    )

                # Non-zero exit — classify error
                last_error = result.stderr
                last_error_class = classify_error(result.stderr)

                if last_error_class == ErrorClass.AUTH:
                    # Auth errors can't be fixed by model fallback
                    relogin = _RELOGIN_COMMANDS.get(self.cli_config.command, f"{self.cli_config.command} login")
                    msg = (
                        f"[WARN] {self.vendor} review failed: auth expired.\n"
                        f"       Run: {relogin}"
                    )
                    print(msg, file=sys.stderr)
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        models_attempted=models_attempted,
                        elapsed_seconds=time.monotonic() - start,
                        error=f"Auth expired. Run: {relogin}",
                        error_class=ErrorClass.AUTH,
                    )

                if last_error_class == ErrorClass.CAPACITY:
                    # Try next model in fallback chain
                    logger.info(
                        "%s model %s capacity exhausted, trying fallback",
                        self.vendor, model_name,
                    )
                    continue

                # Non-capacity, non-auth error — don't retry
                break

            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    error=f"Timeout after {timeout_seconds}s",
                    error_class=ErrorClass.TRANSIENT,
                )

        # All models exhausted or non-retryable error
        return ReviewResult(
            vendor=self.vendor,
            success=False,
            models_attempted=models_attempted,
            elapsed_seconds=0.0,
            error=last_error[:500] if last_error else "Unknown error",
            error_class=last_error_class,
        )

    @staticmethod
    def _parse_findings(stdout: str) -> dict[str, Any] | None:
        """Try to parse review findings JSON from stdout.

        Handles cases where the vendor outputs extra text before/after JSON.
        """
        text = stdout.strip()
        if not text:
            return None

        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "findings" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in output (vendor may emit text around it)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start:brace_end + 1])
                if isinstance(data, dict) and "findings" in data:
                    return data
            except json.JSONDecodeError:
                pass

        return None


# ---------------------------------------------------------------------------
# Review orchestrator
# ---------------------------------------------------------------------------

class ReviewOrchestrator:
    """Multi-vendor review dispatch orchestrator."""

    def __init__(self, adapters: dict[str, CliVendorAdapter]) -> None:
        self.adapters = adapters

    @classmethod
    def from_agents_yaml(cls, path: Path | None = None) -> "ReviewOrchestrator":
        """Create orchestrator from agents.yaml config."""
        # Import here to avoid circular dependency when used standalone
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "agent-coordinator"))
        from src.agents_config import load_agents_config

        entries = load_agents_config(path)
        adapters: dict[str, CliVendorAdapter] = {}
        for entry in entries:
            if entry.cli is not None:
                adapters[entry.name] = CliVendorAdapter(
                    agent_id=entry.name,
                    vendor=entry.type,
                    cli_config=CliConfig(
                        command=entry.cli.command,
                        dispatch_modes={
                            name: ModeConfig(args=mc.args)
                            for name, mc in entry.cli.dispatch_modes.items()
                        },
                        model_flag=entry.cli.model_flag,
                        model=entry.cli.model,
                        model_fallbacks=entry.cli.model_fallbacks,
                    ),
                )
        return cls(adapters)

    def discover_reviewers(self, exclude_vendor: str | None = None) -> list[ReviewerInfo]:
        """Discover available reviewers, optionally excluding the primary vendor."""
        reviewers: list[ReviewerInfo] = []
        for agent_id, adapter in self.adapters.items():
            if exclude_vendor and adapter.vendor == exclude_vendor:
                continue
            reviewers.append(ReviewerInfo(
                vendor=adapter.vendor,
                agent_id=agent_id,
                cli_config=adapter.cli_config,
                available=shutil.which(adapter.cli_config.command) is not None,
            ))
        return reviewers

    def dispatch_and_wait(
        self,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 300,
        exclude_vendor: str | None = None,
    ) -> list[ReviewResult]:
        """Dispatch reviews to all available vendors and collect results.

        Currently dispatches sequentially. Future: parallel subprocess.
        """
        reviewers = self.discover_reviewers(exclude_vendor=exclude_vendor)
        available = [r for r in reviewers if r.available]

        if not available:
            logger.warning("No vendor CLIs available for review dispatch")
            return []

        results: list[ReviewResult] = []
        for reviewer in available:
            adapter = self.adapters[reviewer.agent_id]
            if not adapter.can_dispatch(dispatch_mode):
                logger.info(
                    "Skipping %s: dispatch mode '%s' not configured",
                    reviewer.agent_id, dispatch_mode,
                )
                continue

            logger.info("Dispatching %s review to %s", review_type, reviewer.agent_id)
            result = adapter.dispatch(
                mode=dispatch_mode,
                prompt=prompt,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
            results.append(result)

        return results

    def write_manifest(
        self,
        results: list[ReviewResult],
        output_path: Path,
        review_type: str,
        target: str,
    ) -> None:
        """Write review-manifest.json with dispatch metadata."""
        manifest = {
            "review_type": review_type,
            "target": target,
            "dispatches": [
                {
                    "vendor": r.vendor,
                    "success": r.success,
                    "model_used": r.model_used,
                    "models_attempted": r.models_attempted,
                    "elapsed_seconds": r.elapsed_seconds,
                    "error": r.error,
                    "error_class": r.error_class.value if r.error_class else None,
                }
                for r in results
            ],
            "quorum_requested": len(results),
            "quorum_received": sum(1 for r in results if r.success),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Dispatch reviews to vendor CLIs and collect results.

    Usage:
        python review_dispatcher.py \\
            --review-type plan --mode review \\
            --prompt-file review-prompt.md \\
            --cwd /path/to/worktree \\
            --output-dir reviews/ \\
            --exclude-vendor claude_code
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Dispatch multi-vendor review via CLI",
    )
    parser.add_argument(
        "--review-type", required=True,
        choices=["plan", "implementation"],
    )
    parser.add_argument(
        "--mode", default="review",
        help="Dispatch mode (review, alternative_plan, alternative_impl)",
    )
    parser.add_argument(
        "--prompt", help="Review prompt text (inline)",
    )
    parser.add_argument(
        "--prompt-file", help="Read prompt from file",
    )
    parser.add_argument(
        "--cwd", default=".", help="Working directory for vendor CLIs",
    )
    parser.add_argument(
        "--output-dir", default="reviews",
        help="Directory for per-vendor findings and manifest",
    )
    parser.add_argument(
        "--exclude-vendor", help="Exclude this vendor type from dispatch",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Per-vendor timeout in seconds",
    )
    parser.add_argument(
        "--agents-yaml", help="Path to agents.yaml (default: auto-detect)",
    )
    args = parser.parse_args()

    # Load prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Error: --prompt or --prompt-file required", file=sys.stderr)
        return 1

    # Create orchestrator
    agents_path = Path(args.agents_yaml) if args.agents_yaml else None
    orch = ReviewOrchestrator.from_agents_yaml(agents_path)

    # Discover
    reviewers = orch.discover_reviewers(exclude_vendor=args.exclude_vendor)
    available = [r for r in reviewers if r.available]
    print(f"Available reviewers: {[r.agent_id for r in available]}")

    if not available:
        print("No vendor CLIs available", file=sys.stderr)
        return 1

    # Dispatch
    cwd = Path(args.cwd)
    results = orch.dispatch_and_wait(
        review_type=args.review_type,
        dispatch_mode=args.mode,
        prompt=prompt,
        cwd=cwd,
        timeout_seconds=args.timeout,
        exclude_vendor=args.exclude_vendor,
    )

    # Write results
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        if result.success and result.findings:
            fpath = output_dir / f"findings-{result.vendor}-{args.review_type}.json"
            with open(fpath, "w") as f:
                json.dump(result.findings, f, indent=2)
            print(f"[OK] {result.vendor}: {len(result.findings.get('findings', []))} findings"
                  f" (model: {result.model_used}, {result.elapsed_seconds:.1f}s)")
        else:
            print(f"[FAIL] {result.vendor}: {result.error}"
                  f" (models tried: {result.models_attempted})")

    # Write manifest
    manifest_path = output_dir / "review-manifest.json"
    orch.write_manifest(results, manifest_path, args.review_type, "cli-dispatch")
    print(f"\nManifest: {manifest_path}")

    succeeded = sum(1 for r in results if r.success)
    print(f"Results: {succeeded}/{len(results)} vendors succeeded")
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
