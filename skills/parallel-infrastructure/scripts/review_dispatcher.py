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
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator

from review_attempts import run_vendor_recovery, select_replacement_vendor, validate_review_attempt_chain
from review_routing import RoutingContext, Resolver, resolve_review_routing, translate_thinking

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class ErrorClass(str, Enum):
    """Classification of vendor subprocess errors."""

    CAPACITY = "capacity_exhausted"
    AUTH = "auth_required"
    TRANSIENT = "transient"
    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


_CAPACITY_PATTERNS = ["429", "resource_exhausted", "capacity", "rate limit", "rate_limit"]
_AUTH_PATTERNS = ["401", "unauthenticated", "token expired", "login required", "unauthorized"]
_TRANSIENT_PATTERNS = ["500", "503", "unavailable", "internal server error"]

# Re-login command per CLI binary, keyed by ``cli.command`` (E4). Only harnesses
# with a real ``<cmd> login`` subcommand appear here.
_RELOGIN_COMMANDS: dict[str, str] = {
    "codex": "codex login",
    "grok": "grok login",
    "claude": "claude login",
}

# Harnesses whose auth is NOT restored by a ``<cmd> login`` subcommand (E4). A
# fabricated ``agy login`` / ``pi login`` would be invalid, so these carry an
# explicit manual-remediation hint instead.
_MANUAL_REAUTH: dict[str, str] = {
    # agy: no login subcommand — auto-auth on launch; re-auth is the interactive
    # `/logout` slash command followed by relaunch (design.md §L3).
    "agy": "re-auth manually: run `/logout` inside an agy session, then relaunch",
    # pi: env-var key model — a missing key is a config error, not a re-auth
    # (design.md §L7).
    "pi": "set OPENROUTER_API_KEY in the environment (pi has no login subcommand)",
}


def _relogin_hint(command: str) -> str:
    """Return an actionable auth-recovery hint for a CLI binary (E4).

    Falls back to ``<command> login`` only for binaries not covered by either
    table — never fabricating an invalid ``agy login`` / ``pi login``.
    """
    if command in _RELOGIN_COMMANDS:
        return _RELOGIN_COMMANDS[command]
    if command in _MANUAL_REAUTH:
        return _MANUAL_REAUTH[command]
    return f"{command} login"


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
    thinking_flag: str = ""
    thinking_values: dict[str, str] = field(default_factory=dict)
    prompt_via_stdin: bool = False
    # When set, the prompt is attached as the value of this flag (e.g. agy's
    # ``--prompt``) rather than as a trailing positional or via stdin. E7:
    # antigravity ignores stdin and a trailing positional — the prompt must be
    # the value of ``--prompt``/``-p``.
    prompt_via_flag: str | None = None


@dataclass
class SdkConfig:
    """SDK dispatch configuration for an agent."""

    package: str
    model: str
    method: str = "messages.create"
    model_fallbacks: list[str] = field(default_factory=list)
    thinking_parameter: str = ""
    thinking_values: dict[str, str] = field(default_factory=dict)
    api_key_env: str = ""
    max_tokens: int = 16384


@dataclass
class ReviewerInfo:
    """Information about an available reviewer."""

    vendor: str
    agent_id: str
    cli_config: CliConfig | None = None
    sdk_config: SdkConfig | None = None
    available: bool = True
    dispatch_tier: str = "skip"  # "cli", "sdk", or "skip"


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
    # OpenRouter/OpenAI-compatible generation id for spend reconciliation
    # (OpenSpec add-adaptive-model-router, D7/D10). None for CLI/SDK adapters.
    generation_id: str | None = None
    # Complete logical-result provenance is additive so old callers can keep
    # consuming ``success``/``findings`` while newer checkpoint consumers use
    # the transport-neutral attempt-chain shape directly.
    logical_request_id: str | None = None
    requested_vendor: str | None = None
    requested_routing: dict[str, Any] | None = None
    deadline_at: str | None = None
    budget: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    terminal_outcome: str | None = None
    terminal_vendor: str | None = None
    quorum_eligible: bool = False
    replacement_allocation: dict[str, str] | None = None
    # Raw process text is retained only while the orchestrator creates a
    # bounded/redacted attempt record. It is never copied to the logical result.
    raw_stdout: str | None = field(default=None, repr=False)
    raw_stderr: str | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Generic CLI adapter
# ---------------------------------------------------------------------------

class CliVendorAdapter:
    """Config-driven vendor adapter — one class handles all vendors."""

    def __init__(
        self,
        agent_id: str,
        vendor: str,
        cli_config: CliConfig,
        transport: str = "mcp",
    ) -> None:
        self.agent_id = agent_id
        self.vendor = vendor
        self.cli_config = cli_config
        self.transport = transport

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
        thinking: str | None = None,
    ) -> list[str]:
        """Build subprocess command from config.

        When ``cli_config.prompt_via_stdin`` is True, the prompt is NOT
        appended to the command — it will be passed via stdin instead.
        When ``cli_config.prompt_via_flag`` is set, the prompt is attached as
        the value of that flag (e.g. ``--prompt <prompt>``) and is neither a
        trailing positional nor sent via stdin.
        """
        mode_config = self.cli_config.dispatch_modes[mode]
        cmd = [self.cli_config.command, *mode_config.args]
        effective_model = model or self.cli_config.model
        if effective_model:
            cmd.extend([self.cli_config.model_flag, effective_model])
        flag, value, status = translate_thinking(
            thinking, self.cli_config.thinking_flag, self.cli_config.thinking_values,
        )
        if status == "applied":
            assert flag is not None and value is not None
            cmd.extend([flag, value])
        if self.cli_config.prompt_via_flag:
            cmd.extend([self.cli_config.prompt_via_flag, prompt])
        elif not self.cli_config.prompt_via_stdin:
            cmd.append(prompt)
        return cmd

    def dispatch(
        self,
        mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 300,
        archetype_model: str | None = None,
        archetype_thinking: str | None = None,
    ) -> ReviewResult:
        """Dispatch a review with model fallback on capacity errors.

        Tries the primary model first, then each fallback in order.
        Returns the first successful result or the final failure.

        Args:
            archetype_model: Optional model override from archetype resolution.
                When provided, overrides the agent's default primary model
                but reuses the existing fallback chain (design decision D4).
        """
        _, _, thinking_status = translate_thinking(
            archetype_thinking, self.cli_config.thinking_flag, self.cli_config.thinking_values,
        )
        if thinking_status == "unsupported":
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Requested thinking setting is unsupported by this CLI adapter",
                error_class=ErrorClass.CONFIGURATION,
            )

        primary = archetype_model or self.cli_config.model
        models_to_try: list[str | None] = [primary]
        models_to_try.extend(self.cli_config.model_fallbacks)

        models_attempted: list[str] = []
        last_error = ""
        last_error_class = ErrorClass.UNKNOWN
        dispatch_start = time.monotonic()

        for model in models_to_try:
            model_name = model or "(default)"
            models_attempted.append(model_name)

            cmd = self.build_command(mode, prompt, model, archetype_thinking)
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
                        error_class=None if findings else ErrorClass.INVALID_OUTPUT,
                        raw_stdout=result.stdout,
                        raw_stderr=result.stderr,
                    )

                # Non-zero exit — classify error
                last_error = result.stderr
                last_error_class = classify_error(result.stderr)

                if last_error_class == ErrorClass.AUTH:
                    # Auth errors can't be fixed by model fallback
                    relogin = _relogin_hint(self.cli_config.command)
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
                        raw_stdout=result.stdout,
                        raw_stderr=result.stderr,
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
                    error_class=ErrorClass.TIMEOUT,
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
    def _extract_findings(data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract findings from a parsed JSON dict.

        Handles both direct findings objects and vendor CLI envelopes. grok
        ``--output-format json --json-schema`` places the schema-conforming
        object under ``structuredOutput`` (E6), so unwrap that key when the
        top level is not already a findings object.
        """
        if "findings" in data:
            return data if CliVendorAdapter._validate_findings(data) else None
        # Unwrap grok's structured-output envelope (E6). structuredOutput is
        # normally the parsed object, but tolerate a JSON-string form too.
        structured = data.get("structuredOutput")
        if isinstance(structured, dict) and "findings" in structured:
            return structured if CliVendorAdapter._validate_findings(structured) else None
        if isinstance(structured, str):
            try:
                inner = json.loads(structured)
                if isinstance(inner, dict) and "findings" in inner:
                    return inner if CliVendorAdapter._validate_findings(inner) else None
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _validate_findings(data: dict[str, Any]) -> bool:
        """Validate the complete vendor payload before it becomes eligible.

        A parseable object is not enough: enum violations and excessive
        payloads must enter invalid-output recovery rather than count toward
        quorum or reach consensus matching.
        """
        findings = data.get("findings")
        if not isinstance(findings, list) or len(findings) > 500:
            return False
        try:
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
                return False
            schema_path = CliVendorAdapter._find_review_findings_schema()
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(data)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
        except Exception:  # jsonschema ValidationError; fail closed without exposing payloads
            return False
        return True

    @staticmethod
    def _find_review_findings_schema() -> Path:
        """Locate a repository schema in both source and copied-skill installs."""
        roots = [Path.cwd(), *Path(__file__).resolve().parents]
        for root in roots:
            candidate = root / "openspec" / "schemas" / "review-findings.schema.json"
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("review-findings.schema.json is unavailable")

    @staticmethod
    def _parse_json_blob(text: str) -> dict[str, Any] | None:
        """Parse a findings object from a single text blob.

        Handles a bare JSON object, a vendor envelope (grok
        ``structuredOutput``), and prose wrapped around the JSON.
        """
        text = text.strip()
        if not text:
            return None

        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                result = CliVendorAdapter._extract_findings(data)
                if result is not None:
                    return result
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in output (vendor may emit text around it)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start:brace_end + 1])
                if isinstance(data, dict):
                    result = CliVendorAdapter._extract_findings(data)
                    if result is not None:
                        return result
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _assistant_text(message: Any) -> str | None:
        """Concatenate assistant text parts from a pi/Claude-shaped message."""
        if not isinstance(message, dict) or message.get("role") != "assistant":
            return None
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                part["text"]
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            if parts:
                return "\n".join(parts)
        return None

    @staticmethod
    def _parse_ndjson_findings(text: str) -> dict[str, Any] | None:
        """Parse findings from an NDJSON event stream (e.g. ``pi --mode json``).

        pi emits one JSON event per line; the model's answer is carried as the
        ``message`` payload of assistant ``message_end``/``turn_end`` events, so
        a whole-stdout ``json.loads`` fails and the single-brace scan spans
        unrelated events. Each parsed line is checked directly first (in case a
        vendor emits a bare findings object on its own line); otherwise the last
        complete assistant message wins, mirroring how streaming deltas are
        superseded by the final message snapshot.
        """
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None  # not an event stream — the single-blob path already ran

        saw_event = False
        last_assistant_text: str | None = None
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            saw_event = True
            direct = CliVendorAdapter._extract_findings(obj)
            if direct is not None:
                return direct
            assistant_text = CliVendorAdapter._assistant_text(obj.get("message"))
            if assistant_text:
                last_assistant_text = assistant_text

        if not saw_event or last_assistant_text is None:
            return None
        return CliVendorAdapter._parse_json_blob(last_assistant_text)

    @staticmethod
    def _parse_findings(stdout: str) -> dict[str, Any] | None:
        """Try to parse review findings JSON from stdout.

        Handles a bare JSON object, prose wrapped around the JSON, vendor
        envelopes (e.g. grok ``--output-format json`` nesting the object under
        ``structuredOutput``), and NDJSON event streams (e.g. pi ``--mode
        json``) that carry the answer inside assistant message events.
        """
        text = stdout.strip()
        if not text:
            return None
        result = CliVendorAdapter._parse_json_blob(text)
        if result is not None:
            return result
        return CliVendorAdapter._parse_ndjson_findings(text)

    def dispatch_async(
        self,
        mode: str,
        prompt: str,
        cwd: Path,
        archetype_model: str | None = None,
        archetype_thinking: str | None = None,
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

        _, _, thinking_status = translate_thinking(
            archetype_thinking, self.cli_config.thinking_flag, self.cli_config.thinking_values,
        )
        if thinking_status == "unsupported":
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Requested thinking setting is unsupported by this CLI adapter",
                error_class=ErrorClass.CONFIGURATION,
            )

        # Model fallback: try primary, then each fallback on capacity errors
        models_to_try: list[str | None] = [archetype_model or self.cli_config.model]
        models_to_try.extend(self.cli_config.model_fallbacks)

        models_attempted: list[str] = []

        for model in models_to_try:
            model_name = model or "(default)"
            models_attempted.append(model_name)

            cmd = self.build_command(mode, prompt, model, archetype_thinking)
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
                    relogin = _relogin_hint(self.cli_config.command)
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
# SDK adapter
# ---------------------------------------------------------------------------

class SdkVendorAdapter:
    """SDK-based vendor adapter — dispatches via vendor Python SDKs.

    Used as a fallback when the vendor's CLI is not installed but an API
    key is available.  Only supports the ``review`` dispatch mode (read-only).
    """

    def __init__(
        self,
        agent_id: str,
        vendor: str,
        sdk_config: SdkConfig,
        openbao_role_id: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.vendor = vendor
        self.sdk_config = sdk_config
        self.openbao_role_id = openbao_role_id

    def can_dispatch(self, mode: str) -> bool:
        """Check if SDK dispatch is available for the given mode.

        Only ``review`` mode is supported (read-only).  Also checks
        that the SDK package is importable.
        """
        if mode != "review":
            return False
        return self._can_import_sdk()

    def _can_import_sdk(self) -> bool:
        """Check if the vendor SDK package is importable (without importing)."""
        import importlib.util

        pkg = self.sdk_config.package
        # Map pip package names to import names
        import_map = {
            "google-generativeai": "google.generativeai",
        }
        import_name = import_map.get(pkg, pkg)
        return importlib.util.find_spec(import_name) is not None

    def dispatch(
        self,
        mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 300,
        api_key: str | None = None,
        thinking_parameter: str | None = None,
        thinking_value: str | None = None,
    ) -> ReviewResult:
        """Dispatch a review via vendor SDK with model fallback."""
        if not api_key:
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                error="No API key available for SDK dispatch",
            )

        models_to_try = [self.sdk_config.model, *self.sdk_config.model_fallbacks]
        models_attempted: list[str] = []
        last_error = ""
        dispatch_start = time.monotonic()

        for model in models_to_try:
            models_attempted.append(model)
            try:
                findings = self._call_sdk(
                    prompt=prompt,
                    model=model,
                    api_key=api_key,
                    timeout=timeout_seconds,
                    thinking_parameter=thinking_parameter,
                    thinking_value=thinking_value,
                )
                return ReviewResult(
                    vendor=self.vendor,
                    success=findings is not None,
                    findings=findings,
                    model_used=model,
                    models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - dispatch_start,
                    error=None if findings else "Invalid JSON in SDK response",
                )
            except _SdkCapacityError:
                logger.info(
                    "%s SDK model %s capacity exhausted, trying fallback",
                    self.vendor, model,
                )
                continue
            except _SdkAuthError as exc:
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - dispatch_start,
                    error=f"SDK auth error: {exc}",
                    error_class=ErrorClass.AUTH,
                )
            except _SdkTransientError as exc:
                last_error = str(exc)
                logger.warning(
                    "%s SDK transient error: %s", self.vendor, str(exc)[:200],
                )
                break

        return ReviewResult(
            vendor=self.vendor,
            success=False,
            models_attempted=models_attempted,
            elapsed_seconds=time.monotonic() - dispatch_start,
            error=last_error[:500] or "All models exhausted",
            error_class=ErrorClass.CAPACITY if not last_error else ErrorClass.UNKNOWN,
        )

    def _call_sdk(
        self,
        prompt: str,
        model: str,
        api_key: str,
        timeout: int,
        thinking_parameter: str | None = None,
        thinking_value: str | None = None,
    ) -> dict[str, Any] | None:
        """Call the vendor SDK and parse JSON findings from response."""
        pkg = self.sdk_config.package
        if pkg == "anthropic":
            return self._call_anthropic(prompt, model, api_key, timeout, thinking_parameter, thinking_value)
        elif pkg == "openai":
            return self._call_openai(prompt, model, api_key, timeout, thinking_parameter, thinking_value)
        elif pkg == "google-generativeai":
            return self._call_google(prompt, model, api_key, timeout, thinking_parameter, thinking_value)
        else:
            raise ValueError(f"Unknown SDK package: {pkg}")

    def _call_anthropic(
        self, prompt: str, model: str, api_key: str, timeout: int,
        thinking_parameter: str | None = None, thinking_value: str | None = None,
    ) -> dict[str, Any] | None:
        """Dispatch via Anthropic SDK."""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        try:
            thinking_kwargs = {thinking_parameter: thinking_value} if thinking_parameter and thinking_value else {}
            response = client.messages.create(
                model=model,
                max_tokens=self.sdk_config.max_tokens,
                system=_SDK_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                **thinking_kwargs,
            )
            text = response.content[0].text if response.content else ""
            return CliVendorAdapter._parse_findings(text)
        except anthropic.RateLimitError:
            raise _SdkCapacityError()
        except anthropic.AuthenticationError as exc:
            raise _SdkAuthError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise _SdkTransientError(str(exc))

    def _call_openai(
        self, prompt: str, model: str, api_key: str, timeout: int,
        thinking_parameter: str | None = None, thinking_value: str | None = None,
    ) -> dict[str, Any] | None:
        """Dispatch via OpenAI SDK."""
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=timeout)
        try:
            thinking_kwargs = {thinking_parameter: thinking_value} if thinking_parameter and thinking_value else {}
            response = client.chat.completions.create(
                model=model,
                max_tokens=self.sdk_config.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SDK_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                **thinking_kwargs,
            )
            text = response.choices[0].message.content or ""
            return CliVendorAdapter._parse_findings(text)
        except openai.RateLimitError:
            raise _SdkCapacityError()
        except openai.AuthenticationError as exc:
            raise _SdkAuthError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise _SdkTransientError(str(exc))

    def _call_google(
        self, prompt: str, model: str, api_key: str, timeout: int,
        thinking_parameter: str | None = None, thinking_value: str | None = None,
    ) -> dict[str, Any] | None:
        """Dispatch via Google Generative AI SDK."""
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        try:
            thinking_kwargs = {thinking_parameter: thinking_value} if thinking_parameter and thinking_value else {}
            response = gen_model.generate_content(
                f"{_SDK_SYSTEM_PROMPT}\n\n{prompt}",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=self.sdk_config.max_tokens,
                ),
                **thinking_kwargs,
            )
            text = response.text if response.text else ""
            return CliVendorAdapter._parse_findings(text)
        except Exception as exc:  # noqa: BLE001
            err_lower = str(exc).lower()
            if "429" in err_lower or "resource_exhausted" in err_lower:
                raise _SdkCapacityError()
            if "401" in err_lower or "api_key" in err_lower:
                raise _SdkAuthError(str(exc))
            raise _SdkTransientError(str(exc))


class _SdkCapacityError(Exception):
    """Raised when SDK returns a rate limit / capacity error."""


class _SdkAuthError(Exception):
    """Raised when SDK returns an authentication error."""


class _SdkTransientError(Exception):
    """Raised when SDK returns a transient/network error."""


_SDK_SYSTEM_PROMPT = (
    "You are a code reviewer. Analyze the provided artifacts and output "
    "ONLY valid JSON conforming to review-findings.schema.json. Do not "
    "include any text outside the JSON object."
)


# ---------------------------------------------------------------------------
# Vendor-diversity policy (worker vs validator) — see agents.yaml policies block
# ---------------------------------------------------------------------------

_DEFAULT_VENDOR_DIVERSITY_POLICY: dict[str, Any] = {
    "enforce_for": ["worker_vs_validator"],
    "fallback": "warn_and_continue",
    "scope": "per_change",
}


_CHANGE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _dispatch_state_path(change_id: str, repo_root: Path | None = None) -> Path:
    """Return the path to the change-scoped dispatch-state file.

    Validates ``change_id`` against ``^[a-zA-Z0-9_-]+$`` to prevent path
    traversal from callers that don't pre-validate. The same regex is used
    by gen-eval's ``--openspec-change`` flag at argparse time; here we
    re-validate at this API boundary for defense in depth.
    """
    if not isinstance(change_id, str) or not _CHANGE_ID_RE.match(change_id):
        raise ValueError(
            f"change_id MUST match {_CHANGE_ID_RE.pattern}: got {change_id!r}"
        )
    base = repo_root if repo_root is not None else Path.cwd()
    return base / "openspec" / "changes" / change_id / ".dispatch-state.json"


def load_vendor_diversity_policy(
    agents_yaml_path: Path | None = None,
) -> dict[str, Any]:
    """Load the vendor_diversity policy from agents.yaml.

    Falls back to the default policy (enforced) if the file or the policy
    block is missing. Returns the policy dict (never None).
    """
    if agents_yaml_path is None or not agents_yaml_path.is_file():
        return dict(_DEFAULT_VENDOR_DIVERSITY_POLICY)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "PyYAML not available; using default vendor_diversity policy",
        )
        return dict(_DEFAULT_VENDOR_DIVERSITY_POLICY)
    try:
        doc = yaml.safe_load(agents_yaml_path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load agents.yaml (%s); using default policy", exc)
        return dict(_DEFAULT_VENDOR_DIVERSITY_POLICY)
    policy = (doc.get("policies") or {}).get("vendor_diversity")
    if not isinstance(policy, dict):
        return dict(_DEFAULT_VENDOR_DIVERSITY_POLICY)
    # Merge with defaults so missing keys are filled in.
    merged = dict(_DEFAULT_VENDOR_DIVERSITY_POLICY)
    merged.update(policy)
    return merged


def read_dispatch_state(
    change_id: str,
    repo_root: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Read change-scoped dispatch state.

    Returns ``{}`` if the file is missing. Refuses to read (returns ``{}``
    and logs an error) if the file's permissions include the world-write bit
    (``0002``) — this is the tamper-resistance guard from the spec.
    """
    path = state_path if state_path is not None else _dispatch_state_path(
        change_id, repo_root,
    )
    if not path.is_file():
        return {}
    try:
        st_mode = path.stat().st_mode
    except OSError as exc:
        logger.warning("Failed to stat dispatch-state file %s: %s", path, exc)
        return {}
    if st_mode & 0o002:
        logger.error(
            "vendor_diversity: refusing to read dispatch-state %s "
            "(world-writable, mode=%o); falling back to no-history mode",
            path, st_mode & 0o777,
        )
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read dispatch-state %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    # Normalise the keys we care about; preserve unknown fields untouched.
    data.setdefault("worker_vendors", [])
    data.setdefault("validator_vendors", [])
    data.setdefault("change_id", change_id)
    return data


def write_dispatch_state(
    change_id: str,
    state: dict[str, Any],
    repo_root: Path | None = None,
    state_path: Path | None = None,
) -> Path:
    """Write change-scoped dispatch state with mode 0644.

    Creates parent directories if needed. Returns the path written.
    """
    path = state_path if state_path is not None else _dispatch_state_path(
        change_id, repo_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "worker_vendors": list(state.get("worker_vendors", [])),
        "validator_vendors": list(state.get("validator_vendors", [])),
        "change_id": state.get("change_id", change_id),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    try:
        path.chmod(0o644)
    except OSError as exc:
        logger.warning("Failed to chmod dispatch-state %s: %s", path, exc)
    return path


def record_worker_vendor(
    change_id: str,
    vendor: str,
    repo_root: Path | None = None,
    state_path: Path | None = None,
) -> Path:
    """Record that a worker with *vendor* was dispatched for *change_id*.

    Idempotent — appends only if the vendor isn't already in the list.
    Used by `implement-feature` worker-side selection so subsequent validator
    selection sees the worker's vendor.
    """
    state = read_dispatch_state(change_id, repo_root, state_path)
    workers = list(state.get("worker_vendors", []))
    if vendor not in workers:
        workers.append(vendor)
    state["worker_vendors"] = workers
    state["change_id"] = change_id
    state.setdefault("validator_vendors", [])
    return write_dispatch_state(change_id, state, repo_root, state_path)


def select_validator_vendor(
    candidates: list[str],
    change_id: str,
    agents_yaml_path: Path | None = None,
    repo_root: Path | None = None,
    state_path: Path | None = None,
) -> tuple[str | None, str]:
    """Select a validator vendor for *change_id*.

    Implements the worker-vs-validator vendor-diversity policy:

    * If policy is disabled (``enforce_for`` does not include
      ``worker_vs_validator``), returns the first candidate with a
      "policy disabled" log message.
    * Otherwise, excludes vendors recorded as workers for this change.
    * If the resulting candidate set is empty, returns the first original
      candidate and logs a warning ("only N vendor available, violating
      policy but continuing"). Does NOT raise — fallback is warn_and_continue.

    Records the selected validator vendor in dispatch state for downstream
    invocations.

    Returns a tuple ``(selected_vendor, log_message)``. ``selected_vendor`` is
    None only when *candidates* is empty.
    """
    if not candidates:
        return None, "vendor_diversity: no candidates available"

    policy = load_vendor_diversity_policy(agents_yaml_path)
    enforce_for = policy.get("enforce_for") or []

    if "worker_vs_validator" not in enforce_for:
        selected = candidates[0]
        msg = "vendor_diversity: policy disabled by config"
        logger.info(msg)
        # Still record selection so downstream tooling can audit.
        state = read_dispatch_state(change_id, repo_root, state_path)
        validators = list(state.get("validator_vendors", []))
        if selected not in validators:
            validators.append(selected)
        state["validator_vendors"] = validators
        state.setdefault("worker_vendors", [])
        state["change_id"] = change_id
        write_dispatch_state(change_id, state, repo_root, state_path)
        return selected, msg

    state = read_dispatch_state(change_id, repo_root, state_path)
    worker_vendors = list(state.get("worker_vendors", []))
    filtered = [c for c in candidates if c not in worker_vendors]

    if filtered:
        selected = filtered[0]
        excluded = ",".join(worker_vendors) if worker_vendors else "(none)"
        msg = (
            f"vendor_diversity: excluded {excluded} (worker), "
            f"selected {selected} (validator) for {change_id}"
        )
        logger.info(msg)
    else:
        selected = candidates[0]
        n = len(set(candidates))
        msg = (
            f"vendor_diversity: only {n} vendor available "
            f"({selected}), violating policy but continuing"
        )
        logger.warning(msg)

    # Persist the validator selection.
    validators = list(state.get("validator_vendors", []))
    if selected not in validators:
        validators.append(selected)
    state["validator_vendors"] = validators
    state.setdefault("worker_vendors", worker_vendors)
    state["change_id"] = change_id
    write_dispatch_state(change_id, state, repo_root, state_path)

    return selected, msg


# ---------------------------------------------------------------------------
# Review orchestrator
# ---------------------------------------------------------------------------

class ReviewOrchestrator:
    """Multi-vendor review dispatch orchestrator.

    Supports both CLI and SDK adapters with three-tier dispatch selection:
    Tier 1 (Local CLI) → Tier 2 (SDK/API) → Tier 3 (Skip).
    """

    def __init__(
        self,
        adapters: dict[str, CliVendorAdapter],
        sdk_adapters: dict[str, SdkVendorAdapter] | None = None,
    ) -> None:
        self.adapters = adapters
        self.sdk_adapters = sdk_adapters or {}

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ReviewOrchestrator":
        """Create orchestrator from a config dict (as returned by coordinator).

        The dict should have an ``agents`` key containing a list of agent
        config dicts, each with ``agent_id``, ``type``, ``cli``, and
        optionally ``sdk``.
        """
        adapters: dict[str, CliVendorAdapter] = {}
        sdk_adapters: dict[str, SdkVendorAdapter] = {}
        for agent in data.get("agents", []):
            cli = agent.get("cli")
            sdk = agent.get("sdk")
            if not cli and not sdk:
                continue

            # Build CLI adapter
            if cli:
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
                        thinking_flag=cli.get("thinking_flag", ""),
                        thinking_values=cli.get("thinking_values", {}),
                        prompt_via_stdin=cli.get("prompt_via_stdin", False),
                        prompt_via_flag=cli.get("prompt_via_flag"),
                    ),
                    transport=agent.get("transport", "mcp"),
                )

            # Build SDK adapter
            if sdk:
                sdk_adapters[agent["agent_id"]] = SdkVendorAdapter(
                    agent_id=agent["agent_id"],
                    vendor=agent["type"],
                    sdk_config=SdkConfig(
                        package=sdk["package"],
                        model=sdk["model"],
                        method=sdk.get("method", "messages.create"),
                        model_fallbacks=sdk.get("model_fallbacks", []),
                        thinking_parameter=sdk.get("thinking_parameter", ""),
                        thinking_values=sdk.get("thinking_values", {}),
                        api_key_env=sdk.get("api_key_env", ""),
                        max_tokens=sdk.get("max_tokens", 16384),
                    ),
                    openbao_role_id=agent.get("openbao_role_id"),
                )

        return cls(adapters, sdk_adapters)

    @staticmethod
    def _config_from_agents_yaml(path: Path) -> dict[str, Any] | None:
        """Load dispatch config directly from an agents.yaml file.

        This keeps non-Claude environments from depending on ``~/.claude.json``
        just to discover the local repo's dispatch configuration.
        """
        if not path.is_file():
            return None
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("PyYAML not available; cannot load %s", path)
            return None
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("agents.yaml load error from %s: %s", path, exc)
            return None
        agents_out: list[dict[str, Any]] = []
        for agent_id, agent in (raw.get("agents") or {}).items():
            cli = agent.get("cli")
            sdk = agent.get("sdk")
            if not cli and not sdk:
                continue
            agents_out.append({
                "agent_id": agent_id,
                "type": agent.get("type"),
                "transport": agent.get("transport", "mcp"),
                "openbao_role_id": agent.get("openbao_role_id"),
                "cli": cli,
                "sdk": sdk,
            })
        logger.info("Loaded dispatch config from agents.yaml: %s", path)
        return {"agents": agents_out}

    @staticmethod
    def _explicit_agents_yaml_path() -> Path | None:
        raw = os.environ.get("AGENTS_YAML")
        if not raw:
            return None
        return Path(raw).expanduser()

    @staticmethod
    def _find_local_agents_yaml(start: Path | None = None) -> Path | None:
        """Find repo-local ``agent-coordinator/agents.yaml`` by walking up."""
        current = (start or Path.cwd()).resolve()
        for candidate_root in (current, *current.parents):
            candidate = candidate_root / "agent-coordinator" / "agents.yaml"
            if candidate.is_file():
                return candidate
        return None

    @classmethod
    def _load_from_http(cls) -> dict[str, Any] | None:
        """Load dispatch config from the HTTP coordinator endpoint."""
        base_url = os.environ.get("COORDINATION_API_URL", "http://localhost:8081").rstrip("/")
        url = f"{base_url}/agents/dispatch-configs"
        req = Request(url, method="GET")
        req.add_header("User-Agent", "agentic-coding-tools/0.1")
        try:
            with urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    if isinstance(data, dict):
                        logger.info("Loaded dispatch config from HTTP coordinator: %s", url)
                        return data
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug("HTTP dispatch config discovery failed at %s: %s", url, exc)
        return None

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
        """Create orchestrator using provider-neutral discovery order."""
        explicit = cls._explicit_agents_yaml_path()
        if explicit:
            data = cls._config_from_agents_yaml(explicit)
            if data is not None:
                return cls.from_config_dict(data)

        data = cls._load_from_http()
        if data is not None:
            return cls.from_config_dict(data)

        # Provider-native fallback. Today this includes Claude Code MCP config.
        found = cls._find_coordinator_dir()
        if found:
            python_bin, ac_dir = found
            script = ac_dir / "get_dispatch_configs.py"
            if script.is_file():
                try:
                    result = subprocess.run(
                        [python_bin, str(script)],
                        capture_output=True, text=True, timeout=15,
                    )
                    if result.returncode == 0:
                        return cls.from_config_dict(json.loads(result.stdout))
                    logger.warning("Coordinator query failed: %s", result.stderr[:200])
                except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
                    logger.warning("Coordinator query error: %s", exc)

        # Compatibility only: source-repository configuration is considered
        # after explicit, HTTP, and provider-native MCP configuration.
        local = cls._find_local_agents_yaml()
        if local:
            data = cls._config_from_agents_yaml(local)
            if data is not None:
                return cls.from_config_dict(data)

        logger.warning("No public or local vendor configuration found")
        return cls({})

    @classmethod
    def from_agents_yaml(cls, path: Path | None = None) -> "ReviewOrchestrator":
        """Create orchestrator from explicit or local agents.yaml."""
        resolved = path or cls._explicit_agents_yaml_path() or cls._find_local_agents_yaml()
        if resolved is None:
            logger.warning("agents.yaml not found via explicit path or local repo fallback")
            return cls({})
        data = cls._config_from_agents_yaml(resolved)
        if data is None:
            return cls({})
        try:
            return cls.from_config_dict(data)
        except (KeyError, TypeError) as exc:
            logger.warning("agents.yaml dispatch config conversion failed: %s", exc)
            return cls({})

    def discover_reviewers(
        self,
        exclude_vendor: str | None = None,
        dispatch_mode: str = "review",
    ) -> list[ReviewerInfo]:
        """Discover available reviewers with three-tier selection.

        For each vendor, selects the best available dispatch method:
        Tier 1 (Local CLI) → Tier 2 (SDK/API) → Tier 3 (Skip).
        Deduplicates by vendor — at most one reviewer per vendor type.
        """
        # Collect all CLI adapters (local transport only)
        cli_by_vendor: dict[str, tuple[str, CliVendorAdapter]] = {}
        for agent_id, adapter in self.adapters.items():
            if exclude_vendor and adapter.vendor == exclude_vendor:
                continue
            # Only consider local agents (transport=mcp) for CLI dispatch
            if adapter.transport == "mcp" and adapter.vendor not in cli_by_vendor:
                cli_by_vendor[adapter.vendor] = (agent_id, adapter)

        # Collect all SDK adapters
        sdk_by_vendor: dict[str, tuple[str, SdkVendorAdapter]] = {}
        for agent_id, adapter in self.sdk_adapters.items():
            if exclude_vendor and adapter.vendor == exclude_vendor:
                continue
            if adapter.vendor not in sdk_by_vendor:
                sdk_by_vendor[adapter.vendor] = (agent_id, adapter)

        # Three-tier selection per vendor
        all_vendors = set(cli_by_vendor.keys()) | set(sdk_by_vendor.keys())
        reviewers: list[ReviewerInfo] = []

        for vendor in sorted(all_vendors):
            # Tier 1: Local CLI
            if vendor in cli_by_vendor:
                agent_id, cli_adapter = cli_by_vendor[vendor]
                cli_available = shutil.which(cli_adapter.cli_config.command) is not None
                if cli_available:
                    logger.info("Tier 1 (CLI) selected for %s: %s", vendor, agent_id)
                    reviewers.append(ReviewerInfo(
                        vendor=vendor,
                        agent_id=agent_id,
                        cli_config=cli_adapter.cli_config,
                        available=True,
                        dispatch_tier="cli",
                    ))
                    continue

            # Tier 2: SDK/API
            if vendor in sdk_by_vendor:
                agent_id, sdk_adapter = sdk_by_vendor[vendor]
                if sdk_adapter.can_dispatch(dispatch_mode):
                    logger.info("Tier 2 (SDK) selected for %s: %s", vendor, agent_id)
                    reviewers.append(ReviewerInfo(
                        vendor=vendor,
                        agent_id=agent_id,
                        sdk_config=sdk_adapter.sdk_config,
                        available=True,
                        dispatch_tier="sdk",
                    ))
                    continue

            # Tier 3: Skip
            logger.info("Tier 3 (skip) for %s: no CLI or SDK available", vendor)

        return reviewers

    @staticmethod
    def _routing_payload(routing: RoutingContext | None) -> dict[str, Any]:
        """Return the contract's stable requested-routing subset."""
        return {
            "archetype": routing.archetype if routing else None,
            "tier": routing.tier if routing else None,
            "phase": routing.phase if routing else None,
        }

    @staticmethod
    def _result_response(result: ReviewResult, transport: str) -> dict[str, Any]:
        """Translate one adapter result into the shared recovery input."""
        if result.success and result.findings is not None:
            return {
                "transport": transport,
                "validation_status": "schema_valid",
                "stdout": result.raw_stdout,
                "stderr": result.raw_stderr,
            }
        error_class = result.error_class.value if result.error_class else "invalid_output"
        if error_class == ErrorClass.AUTH.value:
            error_class = "auth"
        if error_class not in {
            "invalid_output", "capacity_exhausted", "auth", "transient",
            "timeout", "configuration", "unknown",
        }:
            error_class = "unknown"
        return {
            "transport": transport,
            "validation_status": "invalid" if error_class == "invalid_output" else "not_reached",
            "error_class": error_class,
            "error_detail": result.error or "review dispatch failed",
            "stdout": result.raw_stdout,
            "stderr": result.raw_stderr,
        }

    @staticmethod
    def _logical_result(
        *, vendor: str, chain: dict[str, Any], attempt_results: list[ReviewResult],
    ) -> ReviewResult:
        """Expose a validated attempt chain through the legacy result API."""
        terminal = chain["attempts"][-1]
        success = chain["terminal_outcome"] == "success"
        source = attempt_results[-1] if attempt_results else None
        error_value = terminal.get("error_class")
        try:
            error_class = ErrorClass.AUTH if error_value == "auth" else (ErrorClass(error_value) if error_value else None)
        except ValueError:
            error_class = ErrorClass.UNKNOWN
        return ReviewResult(
            vendor=vendor,
            success=success,
            findings=source.findings if success and source else None,
            model_used=terminal["resolved_execution"]["model"],
            models_attempted=[
                str(attempt["resolved_execution"]["model"])
                for attempt in chain["attempts"]
            ],
            elapsed_seconds=sum(float(a["elapsed_seconds"]) for a in chain["attempts"]),
            error=None if success else terminal.get("error_detail"),
            error_class=error_class,
            logical_request_id=chain["logical_request_id"],
            requested_vendor=chain["requested_vendor"],
            requested_routing=dict(chain["requested_routing"]),
            deadline_at=chain["deadline_at"],
            budget=dict(chain["budget"]),
            attempts=list(chain["attempts"]),
            terminal_outcome=chain["terminal_outcome"],
            terminal_vendor=chain["terminal_vendor"],
            quorum_eligible=bool(chain["quorum_eligible"]),
        )

    @staticmethod
    def _combine_replacement_result(
        primary: ReviewResult,
        replacement: ReviewResult,
    ) -> ReviewResult:
        """Make one replacement result the terminal result of the original slot."""
        if not primary.attempts or not replacement.attempts:
            raise ValueError("replacement requires recovery-aware logical results")
        if not primary.logical_request_id or not primary.requested_vendor:
            raise ValueError("primary replacement provenance is incomplete")
        primary_attempts = [dict(attempt) for attempt in primary.attempts]
        replacement_attempts = [dict(attempt) for attempt in replacement.attempts]
        for attempt in primary_attempts:
            attempt["terminal"] = False
        replacement_attempts[0]["reason"] = "replacement_vendor"
        attempts = primary_attempts + replacement_attempts
        for index, attempt in enumerate(attempts, start=1):
            attempt["attempt_index"] = index
        fallback_models = list(dict.fromkeys([
            *(primary.budget or {}).get("fallback_models", []),
            *(replacement.budget or {}).get("fallback_models", []),
        ]))
        chain = {
            "logical_request_id": primary.logical_request_id,
            "requested_vendor": primary.requested_vendor,
            "requested_routing": dict(primary.requested_routing or {}),
            "deadline_at": primary.deadline_at,
            "budget": {"corrective_max": 1, "replacement_max": 1, "fallback_models": fallback_models},
            "attempts": attempts,
            "terminal_outcome": replacement.terminal_outcome,
            "terminal_vendor": replacement.terminal_vendor,
            "quorum_eligible": replacement.quorum_eligible,
        }
        validate_review_attempt_chain(chain)
        combined = ReviewOrchestrator._logical_result(
            vendor=str(replacement.terminal_vendor),
            chain=chain,
            attempt_results=[replacement],
        )
        combined.replacement_allocation = {
            "replaced_vendor": primary.requested_vendor,
            "replacement_vendor": str(replacement.terminal_vendor),
            "action": "transferred",
        }
        return combined

    def _dispatch_replacement_review(
        self,
        reviewer: ReviewerInfo,
        *,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int,
        routing_context: RoutingContext | None,
        phase: str | None,
        routing_resolver: Resolver | None,
        api_key_resolver: Any,
    ) -> ReviewResult:
        """Dispatch an undispatched reviewer when it consumes another slot."""
        routing = resolve_review_routing(
            vendor=reviewer.vendor,
            dispatch_mode=dispatch_mode,
            explicit=routing_context,
            phase=phase,
            resolver=routing_resolver,
        )
        if reviewer.dispatch_tier == "cli":
            adapter = self.adapters[reviewer.agent_id]
            return self._dispatch_cli_review(
                adapter=adapter, reviewer=reviewer, review_type=review_type,
                dispatch_mode=dispatch_mode, prompt=prompt, cwd=cwd,
                timeout_seconds=timeout_seconds, routing=routing,
            )
        sdk_adapter = self.sdk_adapters[reviewer.agent_id]
        api_key = api_key_resolver.resolve(
            sdk_adapter.openbao_role_id, sdk_adapter.sdk_config.api_key_env,
        )
        if not api_key:
            chain = run_vendor_recovery(
                logical_request_id=f"{review_type}:{reviewer.agent_id}",
                vendor=reviewer.vendor,
                primary_model=(routing.model if routing else None) or sdk_adapter.sdk_config.model,
                fallback_models=[],
                timeout_seconds=timeout_seconds,
                requested_routing=self._routing_payload(routing),
                invoke=lambda *_args: {
                    "transport": "sdk",
                    "validation_status": "not_reached",
                    "error_class": "auth",
                    "error_detail": "No API key available for SDK dispatch",
                },
            )
            return self._logical_result(
                vendor=reviewer.vendor, chain=chain, attempt_results=[],
            )
        return self._dispatch_sdk_review(
            adapter=sdk_adapter, reviewer=reviewer, review_type=review_type,
            prompt=prompt, cwd=cwd, timeout_seconds=timeout_seconds,
            api_key=api_key, routing=routing,
        )

    def _replace_exhausted_review(
        self,
        primary: ReviewResult,
        *,
        available: list[ReviewerInfo],
        dispatched_vendors: set[str],
        consumed_replacement_vendors: set[str],
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int,
        routing_context: RoutingContext | None,
        phase: str | None,
        routing_resolver: Resolver | None,
        api_key_resolver: Any,
    ) -> ReviewResult:
        """Transfer one undispatched slot when invalid-output recovery exhausts."""
        if primary.terminal_outcome != "invalid_output_exhausted":
            return primary
        reviewers_by_vendor = {reviewer.vendor: reviewer for reviewer in available}
        replacement_vendor = select_replacement_vendor(
            [reviewer.vendor for reviewer in available],
            dispatched_vendors=dispatched_vendors,
            eligible=lambda vendor: vendor not in consumed_replacement_vendors,
        )
        if replacement_vendor is None:
            return primary
        # Cancel the replacement's own slot before it can be dispatched, so it
        # cannot provide a second quorum vote later in this round.
        consumed_replacement_vendors.add(replacement_vendor)
        dispatched_vendors.add(replacement_vendor)
        replacement = self._dispatch_replacement_review(
            reviewers_by_vendor[replacement_vendor],
            review_type=review_type, dispatch_mode=dispatch_mode, prompt=prompt,
            cwd=cwd, timeout_seconds=timeout_seconds,
            routing_context=routing_context, phase=phase,
            routing_resolver=routing_resolver, api_key_resolver=api_key_resolver,
        )
        return self._combine_replacement_result(primary, replacement)

    def _dispatch_cli_review(
        self,
        *, adapter: CliVendorAdapter, reviewer: ReviewerInfo, review_type: str,
        dispatch_mode: str, prompt: str, cwd: Path, timeout_seconds: int,
        routing: RoutingContext | None,
    ) -> ReviewResult:
        """Run CLI sync/async transports through the one recovery state machine."""
        primary_model = (routing.model if routing else None) or adapter.cli_config.model
        requested_routing = self._routing_payload(routing)
        if not primary_model:
            # The attempt helper requires a concrete model for attributable
            # success. Fail closed rather than claiming an implicit default.
            primary_model = "unresolved-model"
            configuration_failure = True
        else:
            configuration_failure = False
        attempt_results: list[ReviewResult] = []
        mode_config = adapter.cli_config.dispatch_modes[dispatch_mode]

        def invoke(_vendor: str, model: str, remaining: float, _reason: str) -> dict[str, Any]:
            if configuration_failure:
                result = ReviewResult(
                    vendor=adapter.vendor, success=False,
                    error="No concrete model available for review dispatch",
                    error_class=ErrorClass.CONFIGURATION,
                )
            else:
                # Recovery owns fallback order/deadline. A one-model adapter
                # prevents the legacy adapter fallback loop from multiplying it.
                one_model = CliVendorAdapter(
                    agent_id=adapter.agent_id,
                    vendor=adapter.vendor,
                    cli_config=replace(adapter.cli_config, model_fallbacks=[]),
                    transport=adapter.transport,
                )
                if mode_config.async_dispatch:
                    submitted = one_model.dispatch_async(
                        dispatch_mode, prompt, cwd,
                        archetype_model=model,
                        archetype_thinking=routing.thinking if routing else None,
                    )
                    result = (
                        one_model.poll_for_result(submitted.task_id, mode_config.poll, cwd)
                        if submitted.success and submitted.task_id and mode_config.poll
                        else submitted
                    )
                    transport = "async"
                else:
                    if remaining < 1:
                        result = ReviewResult(
                            vendor=adapter.vendor, success=False,
                            error="logical vendor deadline exhausted",
                            error_class=ErrorClass.TIMEOUT,
                        )
                    else:
                        result = one_model.dispatch(
                        dispatch_mode, prompt, cwd,
                        timeout_seconds=int(remaining),
                        archetype_model=model,
                        archetype_thinking=routing.thinking if routing else None,
                        )
                    transport = "cli"
                attempt_results.append(result)
                return self._result_response(result, transport)
            attempt_results.append(result)
            return self._result_response(result, "async" if mode_config.async_dispatch else "cli")

        chain = run_vendor_recovery(
            logical_request_id=f"{review_type}:{reviewer.agent_id}",
            vendor=reviewer.vendor,
            primary_model=primary_model,
            fallback_models=adapter.cli_config.model_fallbacks,
            invoke=invoke,
            timeout_seconds=timeout_seconds,
            requested_routing=requested_routing,
        )
        # The core owns bounded retries; the adapter owns the provider-specific
        # translation recorded on every concrete execution.
        _, applied_thinking, translation = translate_thinking(
            routing.thinking if routing else None,
            adapter.cli_config.thinking_flag,
            adapter.cli_config.thinking_values,
        )
        for attempt in chain["attempts"]:
            execution = attempt["resolved_execution"]
            execution["requested_thinking"] = routing.thinking if routing else None
            execution["applied_thinking"] = applied_thinking
            execution["thinking_translation"] = translation
        validate_review_attempt_chain(chain)
        return self._logical_result(vendor=reviewer.vendor, chain=chain, attempt_results=attempt_results)

    def _dispatch_sdk_review(
        self,
        *, adapter: SdkVendorAdapter, reviewer: ReviewerInfo, review_type: str,
        prompt: str, cwd: Path, timeout_seconds: int, api_key: str,
        routing: RoutingContext | None,
    ) -> ReviewResult:
        """Run SDK reviews through the same bounded recovery chain as CLIs."""
        primary_model = (routing.model if routing else None) or adapter.sdk_config.model
        requested_routing = self._routing_payload(routing)
        attempt_results: list[ReviewResult] = []
        requested_thinking = routing.thinking if routing else None
        sdk_parameter = adapter.sdk_config.thinking_parameter
        sdk_value = adapter.sdk_config.thinking_values.get(requested_thinking) if requested_thinking else None
        configuration_failure = bool(requested_thinking and (not sdk_parameter or not sdk_value))

        def invoke(_vendor: str, model: str, remaining: float, _reason: str) -> dict[str, Any]:
            # Recovery owns model fallback order.  Each SDK invocation gets a
            # single concrete model so an adapter cannot reset the deadline.
            if configuration_failure:
                result = ReviewResult(
                    vendor=adapter.vendor,
                    success=False,
                    error="Requested thinking setting is unsupported by this SDK adapter",
                    error_class=ErrorClass.CONFIGURATION,
                )
            else:
                one_model = SdkVendorAdapter(
                    agent_id=adapter.agent_id,
                    vendor=adapter.vendor,
                    sdk_config=replace(adapter.sdk_config, model=model, model_fallbacks=[]),
                    openbao_role_id=adapter.openbao_role_id,
                )
                if remaining < 1:
                    result = ReviewResult(vendor=adapter.vendor, success=False,
                                          error="logical vendor deadline exhausted",
                                          error_class=ErrorClass.TIMEOUT)
                else:
                    result = one_model.dispatch(
                        mode="review", prompt=prompt, cwd=cwd,
                        timeout_seconds=int(remaining), api_key=api_key,
                        thinking_parameter=sdk_parameter if requested_thinking else None,
                        thinking_value=sdk_value,
                    )
            attempt_results.append(result)
            return self._result_response(result, "sdk")

        chain = run_vendor_recovery(
            logical_request_id=f"{review_type}:{reviewer.agent_id}",
            vendor=reviewer.vendor,
            primary_model=primary_model,
            fallback_models=adapter.sdk_config.model_fallbacks,
            invoke=invoke,
            timeout_seconds=timeout_seconds,
            requested_routing=requested_routing,
        )
        for attempt in chain["attempts"]:
            execution = attempt["resolved_execution"]
            execution["requested_thinking"] = requested_thinking
            execution["applied_thinking"] = sdk_value
            execution["thinking_translation"] = (
                "not_requested" if requested_thinking is None else
                ("applied" if not configuration_failure else "unsupported")
            )
        validate_review_attempt_chain(chain)
        return self._logical_result(vendor=reviewer.vendor, chain=chain, attempt_results=attempt_results)

    def dispatch_and_wait(
        self,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int = 300,
        exclude_vendor: str | None = None,
        routing_context: RoutingContext | None = None,
        phase: str | None = None,
        routing_resolver: Resolver | None = None,
        on_terminal_result: Callable[[ReviewResult, list[ReviewResult]], None] | None = None,
    ) -> list[ReviewResult]:
        """Dispatch reviews to available vendors and collect results.

        Uses three-tier selection: CLI → SDK → skip.
        Currently dispatches sequentially.
        """
        try:
            from api_key_resolver import ApiKeyResolver
        except ImportError:
            # When not running from the scripts directory, try relative path
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "api_key_resolver",
                Path(__file__).parent / "api_key_resolver.py",
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                ApiKeyResolver = mod.ApiKeyResolver  # type: ignore[no-redef] # noqa: N806
            else:
                raise

        reviewers = self.discover_reviewers(
            exclude_vendor=exclude_vendor,
            dispatch_mode=dispatch_mode,
        )
        available = [r for r in reviewers if r.available]

        if not available:
            logger.warning("No vendors available for review dispatch")
            return []

        api_key_resolver = ApiKeyResolver()
        results: list[ReviewResult] = []
        dispatched_vendors: set[str] = set()
        consumed_replacement_vendors: set[str] = set()

        def record(result: ReviewResult) -> None:
            """Expose every terminal slot before the next vendor starts."""
            results.append(result)
            if on_terminal_result is not None:
                on_terminal_result(result, list(results))

        for reviewer in available:
            if reviewer.vendor in consumed_replacement_vendors:
                continue
            dispatched_vendors.add(reviewer.vendor)
            if reviewer.dispatch_tier == "cli":
                # CLI dispatch
                adapter = self.adapters[reviewer.agent_id]
                if not adapter.can_dispatch(dispatch_mode):
                    logger.info(
                        "Skipping %s: dispatch mode '%s' not configured",
                        reviewer.agent_id, dispatch_mode,
                    )
                    continue

                mode_config = adapter.cli_config.dispatch_modes[dispatch_mode]
                routing = resolve_review_routing(
                    vendor=reviewer.vendor,
                    dispatch_mode=dispatch_mode,
                    explicit=routing_context,
                    phase=phase,
                    resolver=routing_resolver,
                )

                if dispatch_mode == "review":
                    primary = self._dispatch_cli_review(
                        adapter=adapter, reviewer=reviewer, review_type=review_type,
                        dispatch_mode=dispatch_mode, prompt=prompt, cwd=cwd,
                        timeout_seconds=timeout_seconds, routing=routing,
                    )
                    record(self._replace_exhausted_review(
                        primary, available=available, dispatched_vendors=dispatched_vendors,
                        consumed_replacement_vendors=consumed_replacement_vendors,
                        review_type=review_type, dispatch_mode=dispatch_mode, prompt=prompt,
                        cwd=cwd, timeout_seconds=timeout_seconds,
                        routing_context=routing_context, phase=phase,
                        routing_resolver=routing_resolver,
                        api_key_resolver=api_key_resolver,
                    ))
                    continue

                if mode_config.async_dispatch:
                    logger.info(
                        "Async CLI dispatching %s review to %s",
                        review_type, reviewer.agent_id,
                    )
                    submit_result = adapter.dispatch_async(
                        mode=dispatch_mode, prompt=prompt, cwd=cwd,
                    )
                    if submit_result.success and submit_result.task_id and mode_config.poll:
                        poll_result = adapter.poll_for_result(
                            submit_result.task_id, mode_config.poll, cwd=cwd,
                        )
                        record(poll_result)
                    else:
                        record(submit_result)
                else:
                    logger.info(
                        "Sync CLI dispatching %s review to %s",
                        review_type, reviewer.agent_id,
                    )
                    result = adapter.dispatch(
                        mode=dispatch_mode,
                        prompt=prompt,
                        cwd=cwd,
                        timeout_seconds=timeout_seconds,
                    )
                    record(result)

            elif reviewer.dispatch_tier == "sdk":
                # SDK dispatch
                sdk_adapter = self.sdk_adapters[reviewer.agent_id]
                api_key = api_key_resolver.resolve(
                    sdk_adapter.openbao_role_id,
                    sdk_adapter.sdk_config.api_key_env,
                )
                logger.info(
                    "SDK dispatching %s review to %s (key: %s)",
                    review_type, reviewer.agent_id,
                    "resolved" if api_key else "missing",
                )
                if not api_key:
                    record(ReviewResult(
                        vendor=reviewer.vendor,
                        success=False,
                        error="No API key available for SDK dispatch",
                    ))
                    continue

                if dispatch_mode == "review":
                    routing = resolve_review_routing(
                        vendor=reviewer.vendor,
                        dispatch_mode=dispatch_mode,
                        explicit=routing_context,
                        phase=phase,
                        resolver=routing_resolver,
                    )
                    primary = self._dispatch_sdk_review(
                        adapter=sdk_adapter, reviewer=reviewer,
                        review_type=review_type, prompt=prompt, cwd=cwd,
                        timeout_seconds=timeout_seconds, api_key=api_key,
                        routing=routing,
                    )
                    record(self._replace_exhausted_review(
                        primary, available=available, dispatched_vendors=dispatched_vendors,
                        consumed_replacement_vendors=consumed_replacement_vendors,
                        review_type=review_type, dispatch_mode=dispatch_mode, prompt=prompt,
                        cwd=cwd, timeout_seconds=timeout_seconds,
                        routing_context=routing_context, phase=phase,
                        routing_resolver=routing_resolver,
                        api_key_resolver=api_key_resolver,
                    ))
                    continue

                result = sdk_adapter.dispatch(
                    mode=dispatch_mode,
                    prompt=prompt,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    api_key=api_key,
                )
                record(result)

        return results

    def write_manifest(
        self,
        results: list[ReviewResult],
        output_path: Path,
        review_type: str,
        target: str,
        vendors: list[dict[str, Any]] | None = None,
    ) -> None:
        """Write review-manifest.json via the shared checkpoint_findings helper.

        The manifest is the superset shape: legacy fields (review_type, target,
        dispatches[], quorum_requested, quorum_received) plus new fields
        (schema_version, change_id=null, created_at, vendors[]). Existing
        callers reading the legacy fields continue to work; the new fields
        are additive.

        The helper always writes ``review-manifest.json`` under
        ``output_path.parent`` (this is the canonical filename baked into
        the schema). To prevent silent caller confusion, ``output_path.name``
        MUST equal ``"review-manifest.json"`` — passing any other filename
        raises ``ValueError`` instead of silently losing the requested name.
        ``vendors`` defaults to an empty index for callers that pre-date
        the per-vendor file write loop in main().
        """
        if output_path.name != "review-manifest.json":
            raise ValueError(
                f"output_path.name must be 'review-manifest.json', "
                f"got {output_path.name!r}. The helper writes a fixed "
                f"filename; pass the desired parent directory with "
                f"trailing 'review-manifest.json' if you need to be explicit."
            )

        from checkpoint_findings import write_manifest as _cf_write_manifest

        dispatches = []
        for r in results:
            if r.attempts:
                dispatches.append({
                    "logical_request_id": r.logical_request_id,
                    "requested_vendor": r.requested_vendor,
                    "requested_routing": r.requested_routing,
                    "deadline_at": r.deadline_at,
                    "budget": r.budget,
                    "attempts": r.attempts,
                    "terminal_outcome": r.terminal_outcome,
                    "terminal_vendor": r.terminal_vendor,
                    "quorum_eligible": r.quorum_eligible,
                    **({"replacement_allocation": r.replacement_allocation}
                       if r.replacement_allocation else {}),
                })
            else:
                dispatches.append({
                    "vendor": r.vendor, "success": r.success, "model_used": r.model_used,
                    "models_attempted": r.models_attempted, "elapsed_seconds": r.elapsed_seconds,
                    "error": r.error,
                    "error_class": "auth" if r.error_class == ErrorClass.AUTH else (r.error_class.value if r.error_class else None),
                })
        _cf_write_manifest(
            output_path.parent,
            review_type=review_type,
            target=target,
            vendors=list(vendors) if vendors is not None else [],
            change_id=None,
            dispatches=dispatches,
            quorum_requested=len(results),
            quorum_received=None,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

# Exit code for "fewer dispatchable vendors than the requested quorum". Distinct
# from 1 (operational failure) so a caller can tell "below quorum" from "the
# probe itself broke" — both are non-zero, so a caller that only checks
# truthiness still degrades safely.
CHECK_VENDORS_BELOW_QUORUM = 2


def _check_vendors(
    *,
    agents_yaml: str | None = None,
    exclude_vendor: str | None = None,
    min_vendors: int = 2,
    dispatch_mode: str = "review",
) -> int:
    """Report whether enough vendors are dispatchable for multi-vendor review.

    Returns 0 when at least *min_vendors* reviewers are available, else
    :data:`CHECK_VENDORS_BELOW_QUORUM`. Orchestrators use the exit status to
    decide whether to enable CLI review — so this MUST fail closed: any error
    resolving the roster reports "below quorum" rather than passing silently.
    """
    try:
        if agents_yaml:
            orch = ReviewOrchestrator.from_agents_yaml(Path(agents_yaml))
        else:
            orch = ReviewOrchestrator.from_coordinator()
            if not orch.adapters:
                orch = ReviewOrchestrator.from_agents_yaml()
        reviewers = orch.discover_reviewers(
            exclude_vendor=exclude_vendor,
            dispatch_mode=dispatch_mode,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on any resolution error
        print(
            f"check-vendors: unable to resolve vendor roster ({exc})",
            file=sys.stderr,
        )
        return CHECK_VENDORS_BELOW_QUORUM

    names = sorted({r.vendor for r in reviewers})
    # flush so the summary precedes the stderr diagnostic when both are captured
    print(
        f"check-vendors: {len(names)}/{min_vendors} available: "
        f"{', '.join(names) or '(none)'}",
        flush=True,
    )
    if len(names) < min_vendors:
        print(
            f"check-vendors: below quorum ({len(names)} < {min_vendors}) — "
            f"multi-vendor review unavailable",
            file=sys.stderr,
        )
        return CHECK_VENDORS_BELOW_QUORUM
    return 0


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
        "--check-vendors", action="store_true",
        help=(
            "Exit 0 if at least --min-vendors reviewers are dispatchable, 2 "
            "otherwise. For orchestrator CLI-mode detection; honors "
            "--exclude-vendor."
        ),
    )
    parser.add_argument(
        "--min-vendors", type=int, default=2,
        help=(
            "Quorum required by --check-vendors (default: 2, the minimum for "
            "multi-vendor convergence)"
        ),
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

    # --check-vendors: quorum probe for orchestrator CLI-mode detection.
    # Exits 0 (quorum met) or 2 (below quorum / no config) so callers can
    # branch on the exit status. Never dispatches; never writes.
    if args.check_vendors:
        return _check_vendors(
            agents_yaml=args.agents_yaml,
            exclude_vendor=args.exclude_vendor,
            min_vendors=args.min_vendors,
            dispatch_mode=args.mode,
        )

    # --list-agents: show available agents and exit
    if args.list_agents:
        if args.agents_yaml:
            orch = ReviewOrchestrator.from_agents_yaml(Path(args.agents_yaml))
        else:
            orch = ReviewOrchestrator.from_coordinator()
            if not orch.adapters:
                orch = ReviewOrchestrator.from_agents_yaml()
        if not orch.adapters and not orch.sdk_adapters:
            print("No agents with dispatch configs found")
            return 1
        reviewers = orch.discover_reviewers()
        print(f"{'Agent':<20} {'Vendor':<15} {'Tier':<6} {'Command/SDK':<20} {'Modes':<25} {'Fallbacks'}")
        print("-" * 110)
        for reviewer in reviewers:
            if reviewer.dispatch_tier == "cli" and reviewer.agent_id in orch.adapters:
                c = orch.adapters[reviewer.agent_id].cli_config
                modes = ", ".join(
                    f"{m}{'*' if c.dispatch_modes[m].async_dispatch else ''}"
                    for m in c.dispatch_modes
                )
                fb = ", ".join(c.model_fallbacks) or "(none)"
                print(f"{reviewer.agent_id:<20} {reviewer.vendor:<15} {'CLI':<6} {c.command:<20} {modes:<25} {fb}")
            elif reviewer.dispatch_tier == "sdk" and reviewer.agent_id in orch.sdk_adapters:
                s = orch.sdk_adapters[reviewer.agent_id].sdk_config
                fb = ", ".join(s.model_fallbacks) or "(none)"
                print(f"{reviewer.agent_id:<20} {reviewer.vendor:<15} {'SDK':<6} {s.package:<20} {'review':<25} {fb}")

        # Also show skipped vendors
        for agent_id, adapter in orch.adapters.items():
            if not any(r.agent_id == agent_id for r in reviewers):
                c = adapter.cli_config
                print(f"{agent_id:<20} {adapter.vendor:<15} {'---':<6} {c.command + ' (missing)':<20} {'---':<25} ---")
        for agent_id, adapter in orch.sdk_adapters.items():
            if not any(r.agent_id == agent_id for r in reviewers):
                s = adapter.sdk_config
                print(f"{agent_id:<20} {adapter.vendor:<15} {'---':<6} {s.package + ' (no key)':<20} {'---':<25} ---")

        print("\n* = async dispatch (submit + poll)")
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

    # Discover (three-tier selection)
    reviewers = orch.discover_reviewers(
        exclude_vendor=args.exclude_vendor,
        dispatch_mode=args.mode,
    )
    available = [r for r in reviewers if r.available]
    print(f"Available reviewers: {[(r.agent_id, r.dispatch_tier) for r in available]}")

    if not available:
        print("No vendors available (no CLI or SDK dispatch)", file=sys.stderr)
        return 1

    # Persist every terminal slot as it completes. This is deliberately set up
    # before dispatch: a later timeout/crash cannot erase earlier evidence.
    from checkpoint_findings import write_vendor_findings as _cf_write_vendor_findings

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_terminal(_result: ReviewResult, partial: list[ReviewResult]) -> None:
        vendors_index: list[dict[str, Any]] = []
        for item in partial:
            eligible = item.quorum_eligible if item.attempts else item.success
            if eligible and item.findings is not None:
                findings_array = item.findings.get("findings", [])
                _cf_write_vendor_findings(
                    output_dir, vendor=item.vendor, review_type=args.review_type,
                    target="cli-dispatch", findings=findings_array,
                    reviewer_vendor=item.vendor,
                )
                vendors_index.append({
                    "name": item.vendor,
                    "findings_path": f"findings-{item.vendor}-{args.review_type}.json",
                    "finding_count": len(findings_array),
                    "quorum_eligible": True,
                })
        orch.write_manifest(
            partial, output_dir / "review-manifest.json", args.review_type,
            "cli-dispatch", vendors=vendors_index,
        )

    # Dispatch
    cwd = Path(args.cwd)
    results = orch.dispatch_and_wait(
        review_type=args.review_type,
        dispatch_mode=args.mode,
        prompt=prompt,
        cwd=cwd,
        timeout_seconds=args.timeout,
        exclude_vendor=args.exclude_vendor,
        on_terminal_result=checkpoint_terminal,
    )

    # Write results via the shared checkpoint_findings helper. Per-vendor
    # files preserve the existing wrapper-object shape and path layout; the
    # manifest gains the superset fields needed by the in-process converge()
    # caller while preserving everything legacy callers parse.
    vendors_index: list[dict[str, Any]] = []
    for result in results:
        quorum_eligible = result.quorum_eligible if result.attempts else result.success
        if quorum_eligible and result.findings:
            findings_array = result.findings.get("findings", [])
            _cf_write_vendor_findings(
                output_dir,
                vendor=result.vendor,
                review_type=args.review_type,
                target="cli-dispatch",
                findings=findings_array,
            )
            vendors_index.append({
                "name": result.vendor,
                "findings_path": f"findings-{result.vendor}-{args.review_type}.json",
                "finding_count": len(findings_array),
                "quorum_eligible": True,
            })
            print(f"[OK] {result.vendor}: {len(findings_array)} findings"
                  f" (model: {result.model_used}, {result.elapsed_seconds:.1f}s)")
        else:
            print(f"[FAIL] {result.vendor}: {result.error}"
                  f" (models tried: {result.models_attempted})")

    # Write manifest with the vendor index pointing at per-vendor files
    manifest_path = output_dir / "review-manifest.json"
    orch.write_manifest(
        results, manifest_path, args.review_type, "cli-dispatch",
        vendors=vendors_index,
    )
    print(f"\nManifest: {manifest_path}")

    succeeded = sum(1 for r in results if (r.quorum_eligible if r.attempts else r.success))
    print(f"Results: {succeeded}/{len(results)} vendors succeeded")
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
