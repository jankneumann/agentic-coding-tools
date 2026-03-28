"""Config-driven multi-vendor review dispatcher.

Dispatches review skills to vendor CLIs using configuration from
agents.yaml.  A single CliVendorAdapter class handles all vendors —
no per-vendor subclasses needed.

Usage:
    from review_dispatcher import ReviewOrchestrator

    # Preferred: query coordinator MCP server (works in any repo)
    orch = ReviewOrchestrator.from_coordinator()
    # Fallback: load from agents.yaml on disk (only in agentic-coding-tools repo)
    orch = ReviewOrchestrator.from_agents_yaml()
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
import re
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
# Data classes — canonical definitions in agent-coordinator/src/agents_config.py.
# Duplicated here so the dispatcher works standalone (in repos without
# agent-coordinator). When agent-coordinator is available, from_agents_yaml()
# converts its types to these.
# ---------------------------------------------------------------------------

@dataclass
class PollConfig:
    """Polling configuration for async dispatch modes."""

    command_template: list[str]
    task_id_pattern: str
    success_pattern: str
    failure_pattern: str = "failed|error"
    interval_seconds: int = 30
    timeout_seconds: int = 600


@dataclass
class ModeConfig:
    """CLI args for a single dispatch mode."""

    args: list[str]
    async_dispatch: bool = False
    poll: PollConfig | None = None


@dataclass
class CliConfig:
    """CLI dispatch configuration for an agent."""

    command: str
    dispatch_modes: dict[str, ModeConfig]
    model_flag: str
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)
    prompt_via_stdin: bool = False


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
    async_dispatch: bool = False
    task_id: str | None = None


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
        """Build subprocess command from config.

        When ``cli_config.prompt_via_stdin`` is True, the prompt is NOT
        appended to the command — it will be passed via stdin instead.
        """
        mode_config = self.cli_config.dispatch_modes[mode]
        cmd = [self.cli_config.command, *mode_config.args]
        effective_model = model or self.cli_config.model
        if effective_model:
            cmd.extend([self.cli_config.model_flag, effective_model])
        if not self.cli_config.prompt_via_stdin:
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
        dispatch_start = time.monotonic()

        for model in models_to_try:
            model_name = model or "(default)"
            models_attempted.append(model_name)

            cmd = self.build_command(mode, prompt, model)
            stdin_text = prompt if self.cli_config.prompt_via_stdin else None
            start = time.monotonic()

            try:
                result = subprocess.run(
                    cmd,
                    input=stdin_text,
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
            elapsed_seconds=time.monotonic() - dispatch_start,
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

    def dispatch_async(
        self,
        mode: str,
        prompt: str,
        cwd: Path,
    ) -> ReviewResult:
        """Submit an async dispatch and return immediately with task_id.

        The caller must subsequently call ``poll_for_result()`` to wait
        for completion.
        """
        mode_config = self.cli_config.dispatch_modes[mode]
        if not mode_config.async_dispatch or not mode_config.poll:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Mode is not configured for async dispatch",
            )

        # Model fallback: try primary, then each fallback on capacity errors
        models_to_try: list[str | None] = [self.cli_config.model]
        models_to_try.extend(self.cli_config.model_fallbacks)

        models_attempted: list[str] = []

        for model in models_to_try:
            model_name = model or "(default)"
            models_attempted.append(model_name)

            cmd = self.build_command(mode, prompt, model)
            stdin_text = prompt if self.cli_config.prompt_via_stdin else None
            start = time.monotonic()

            try:
                result = subprocess.run(
                    cmd,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=120,  # submit timeout (not execution timeout)
                    cwd=str(cwd),
                )
            except subprocess.TimeoutExpired:
                return ReviewResult(
                    vendor=self.vendor, success=False,
                    models_attempted=models_attempted,
                    error="Timeout submitting async task",
                    error_class=ErrorClass.TRANSIENT,
                )

            combined = result.stdout + "\n" + result.stderr
            elapsed = time.monotonic() - start

            # Check for capacity errors before extracting task ID
            if result.returncode != 0:
                error_class = classify_error(result.stderr)
                if error_class == ErrorClass.AUTH:
                    relogin = _RELOGIN_COMMANDS.get(
                        self.cli_config.command,
                        f"{self.cli_config.command} login",
                    )
                    print(
                        f"[WARN] {self.vendor} async dispatch failed: "
                        f"auth expired.\n       Run: {relogin}",
                        file=sys.stderr,
                    )
                    return ReviewResult(
                        vendor=self.vendor, success=False,
                        models_attempted=models_attempted,
                        elapsed_seconds=elapsed,
                        error=f"Auth expired. Run: {relogin}",
                        error_class=ErrorClass.AUTH,
                    )
                if error_class == ErrorClass.CAPACITY:
                    logger.info(
                        "%s async model %s capacity exhausted, trying fallback",
                        self.vendor, model_name,
                    )
                    continue
                # Non-retryable error
                return ReviewResult(
                    vendor=self.vendor, success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    error=result.stderr[:500],
                    error_class=error_class,
                )

            # Extract task ID from output
            match = re.search(mode_config.poll.task_id_pattern, combined)
            if not match:
                return ReviewResult(
                    vendor=self.vendor, success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    error=f"Could not extract task ID from output: {combined[:300]}",
                    error_class=ErrorClass.UNKNOWN,
                )

            # Handle multi-group alternation patterns
            task_id = next(
                (g for g in match.groups() if g is not None),
                match.group(0),
            )
            logger.info(
                "Async task submitted for %s: task_id=%s", self.vendor, task_id,
            )

            return ReviewResult(
                vendor=self.vendor,
                success=True,
                models_attempted=models_attempted,
                elapsed_seconds=elapsed,
                async_dispatch=True,
                task_id=task_id,
            )

        # All models exhausted
        return ReviewResult(
            vendor=self.vendor,
            success=False,
            models_attempted=models_attempted,
            error="All models exhausted for async dispatch",
            error_class=ErrorClass.CAPACITY,
        )

    def poll_for_result(
        self,
        task_id: str,
        poll_config: PollConfig,
        cwd: Path | None = None,
    ) -> ReviewResult:
        """Poll an async task until completion or timeout.

        Args:
            task_id: Task identifier extracted from async dispatch output.
            poll_config: Polling configuration from the mode config.
            cwd: Working directory for poll commands (optional).

        Returns:
            ReviewResult with findings if successful, error otherwise.
        """
        poll_cmd = [
            arg.replace("{task_id}", task_id)
            for arg in poll_config.command_template
        ]

        success_re = re.compile(poll_config.success_pattern, re.IGNORECASE)
        failure_re = re.compile(poll_config.failure_pattern, re.IGNORECASE)

        start = time.monotonic()
        deadline = start + poll_config.timeout_seconds
        attempts = 0

        while time.monotonic() < deadline:
            attempts += 1
            logger.info(
                "Polling %s task %s (attempt %d)", self.vendor, task_id, attempts,
            )

            try:
                result = subprocess.run(
                    poll_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(cwd) if cwd else None,
                )
            except subprocess.TimeoutExpired:
                logger.warning("Poll command timed out, retrying")
                time.sleep(poll_config.interval_seconds)
                continue

            combined = result.stdout + "\n" + result.stderr

            if failure_re.search(combined):
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - start,
                    error=f"Async task failed: {combined[:300]}",
                    error_class=ErrorClass.UNKNOWN,
                    task_id=task_id,
                )

            if success_re.search(combined):
                # Task completed — try to extract findings from output
                findings = self._parse_findings(result.stdout)
                return ReviewResult(
                    vendor=self.vendor,
                    success=findings is not None,
                    findings=findings,
                    elapsed_seconds=time.monotonic() - start,
                    error=None if findings else "Task completed but no findings JSON in output",
                    task_id=task_id,
                )

            # Still running — wait and retry
            time.sleep(poll_config.interval_seconds)

        # Timeout
        return ReviewResult(
            vendor=self.vendor,
            success=False,
            elapsed_seconds=time.monotonic() - start,
            error=f"Polling timed out after {poll_config.timeout_seconds}s ({attempts} attempts)",
            error_class=ErrorClass.TRANSIENT,
            task_id=task_id,
        )


# ---------------------------------------------------------------------------
# Review orchestrator
# ---------------------------------------------------------------------------

class ReviewOrchestrator:
    """Multi-vendor review dispatch orchestrator."""

    def __init__(self, adapters: dict[str, CliVendorAdapter]) -> None:
        self.adapters = adapters

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ReviewOrchestrator":
        """Create orchestrator from a config dict (as returned by coordinator).

        The dict should have an ``agents`` key containing a list of agent
        config dicts, each with ``agent_id``, ``type``, and ``cli``.
        """
        adapters: dict[str, CliVendorAdapter] = {}
        for agent in data.get("agents", []):
            cli = agent.get("cli")
            if not cli:
                continue
            dispatch_modes: dict[str, ModeConfig] = {}
            for mode_name, mode_data in cli.get("dispatch_modes", {}).items():
                poll_data = mode_data.get("poll")
                poll_cfg = PollConfig(
                    command_template=poll_data["command_template"],
                    task_id_pattern=poll_data["task_id_pattern"],
                    success_pattern=poll_data["success_pattern"],
                    failure_pattern=poll_data.get("failure_pattern", "failed|error"),
                    interval_seconds=poll_data.get("interval_seconds", 30),
                    timeout_seconds=poll_data.get("timeout_seconds", 600),
                ) if poll_data else None
                dispatch_modes[mode_name] = ModeConfig(
                    args=mode_data["args"],
                    async_dispatch=mode_data.get("async", False),
                    poll=poll_cfg,
                )
            adapters[agent["agent_id"]] = CliVendorAdapter(
                agent_id=agent["agent_id"],
                vendor=agent["type"],
                cli_config=CliConfig(
                    command=cli["command"],
                    dispatch_modes=dispatch_modes,
                    model_flag=cli.get("model_flag", "-m"),
                    model=cli.get("model"),
                    model_fallbacks=cli.get("model_fallbacks", []),
                    prompt_via_stdin=cli.get("prompt_via_stdin", False),
                ),
            )
        return cls(adapters)

    @classmethod
    def _find_coordinator_dir(cls) -> tuple[str, Path] | None:
        """Discover the agent-coordinator directory from MCP config.

        Reads ``~/.claude.json`` to find the coordination MCP server's
        ``run_mcp.py`` path, then derives the agent-coordinator directory
        and Python binary from it.  Returns ``(python_bin, ac_dir)`` or
        ``None`` if not configured.
        """
        claude_json = Path.home() / ".claude.json"
        if not claude_json.is_file():
            return None
        try:
            cfg = json.loads(claude_json.read_text())
            mcp = cfg.get("mcpServers", {}).get("coordination", {})
            python_bin = mcp.get("command", "")
            args = mcp.get("args", [])
            if not python_bin or not args:
                return None
            # args[0] is the path to run_mcp.py; its parent is agent-coordinator
            ac_dir = Path(args[0]).resolve().parent
            if not ac_dir.is_dir():
                return None
            return (python_bin, ac_dir)
        except (json.JSONDecodeError, OSError, IndexError):
            return None

    @classmethod
    def from_coordinator(cls) -> "ReviewOrchestrator":
        """Create orchestrator by calling get_dispatch_configs via subprocess.

        Discovers the agent-coordinator directory from the coordination
        MCP server config in ``~/.claude.json``, then runs
        ``get_dispatch_configs.py`` using the same Python binary.
        Works from any repo — no local agent-coordinator checkout required.
        """
        found = cls._find_coordinator_dir()
        if not found:
            logger.warning("coordination MCP server not configured in ~/.claude.json")
            return cls({})

        python_bin, ac_dir = found
        script = ac_dir / "get_dispatch_configs.py"
        if not script.is_file():
            logger.warning("get_dispatch_configs.py not found at %s", script)
            return cls({})

        try:
            result = subprocess.run(
                [python_bin, str(script)],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.warning(
                    "Coordinator query failed: %s", result.stderr[:200],
                )
                return cls({})
            data = json.loads(result.stdout)
            return cls.from_config_dict(data)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            logger.warning("Coordinator query error: %s", exc)
            return cls({})

    @classmethod
    def from_agents_yaml(cls, path: Path | None = None) -> "ReviewOrchestrator":
        """Create orchestrator from an explicit agents.yaml path.

        Uses ``_find_coordinator_dir()`` to locate the
        ``get_dispatch_configs.py`` script, then passes *path* as an
        argument so the script loads the specified YAML instead of its
        default.  Works from any repo.
        """
        found = cls._find_coordinator_dir()
        if not found:
            logger.warning(
                "agent-coordinator not found — "
                "coordination MCP server not configured in ~/.claude.json",
            )
            return cls({})

        python_bin, ac_dir = found
        script = ac_dir / "get_dispatch_configs.py"
        if not script.is_file():
            logger.warning("get_dispatch_configs.py not found at %s", script)
            return cls({})

        cmd = [python_bin, str(script)]
        if path is not None:
            cmd.append(str(path))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.warning(
                    "agents.yaml load failed: %s", result.stderr[:200],
                )
                return cls({})
            data = json.loads(result.stdout)
            return cls.from_config_dict(data)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            logger.warning("agents.yaml load error: %s", exc)
            return cls({})

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

            mode_config = adapter.cli_config.dispatch_modes[dispatch_mode]

            if mode_config.async_dispatch:
                logger.info(
                    "Async dispatching %s review to %s",
                    review_type, reviewer.agent_id,
                )
                submit_result = adapter.dispatch_async(
                    mode=dispatch_mode, prompt=prompt, cwd=cwd,
                )
                if submit_result.success and submit_result.task_id and mode_config.poll:
                    # Poll for completion
                    poll_result = adapter.poll_for_result(
                        submit_result.task_id, mode_config.poll, cwd=cwd,
                    )
                    results.append(poll_result)
                else:
                    results.append(submit_result)
            else:
                logger.info(
                    "Sync dispatching %s review to %s",
                    review_type, reviewer.agent_id,
                )
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
        "--list-agents", action="store_true",
        help="List available agents with CLI dispatch configs and exit",
    )
    parser.add_argument(
        "--review-type",
        choices=["plan", "implementation"],
    )
    parser.add_argument(
        "--mode", default="review",
        help="Dispatch mode: review (read-only) or alternative (write access)",
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

    # --list-agents: show available agents and exit
    if args.list_agents:
        if args.agents_yaml:
            orch = ReviewOrchestrator.from_agents_yaml(Path(args.agents_yaml))
        else:
            orch = ReviewOrchestrator.from_coordinator()
            if not orch.adapters:
                orch = ReviewOrchestrator.from_agents_yaml()
        if not orch.adapters:
            print("No agents with CLI dispatch configs found")
            return 1
        print(f"{'Agent':<20} {'Vendor':<15} {'Command':<10} {'Modes':<30} {'Stdin':<6} {'Fallbacks'}")
        print("-" * 100)
        for agent_id, adapter in orch.adapters.items():
            c = adapter.cli_config
            modes = ", ".join(
                f"{m}{'*' if c.dispatch_modes[m].async_dispatch else ''}"
                for m in c.dispatch_modes
            )
            fb = ", ".join(c.model_fallbacks) or "(none)"
            print(f"{agent_id:<20} {adapter.vendor:<15} {c.command:<10} {modes:<30} {'yes' if c.prompt_via_stdin else 'no':<6} {fb}")
        print(f"\n* = async dispatch (submit + poll)")
        return 0

    if not args.review_type:
        print("Error: --review-type required (or use --list-agents)", file=sys.stderr)
        return 1

    # Load prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Error: --prompt or --prompt-file required", file=sys.stderr)
        return 1

    # Create orchestrator — try coordinator first, fall back to agents.yaml
    if args.agents_yaml:
        orch = ReviewOrchestrator.from_agents_yaml(Path(args.agents_yaml))
    else:
        orch = ReviewOrchestrator.from_coordinator()
        if not orch.adapters:
            logger.info("Coordinator unavailable, trying agents.yaml on disk")
            orch = ReviewOrchestrator.from_agents_yaml()

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
