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

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import line_resolver
from vendor_limit_reporter import report_vendor_limit_result

_BRIDGE_SCRIPTS = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

from coordination_bridge import (  # noqa: E402
    try_complete_work,
    try_submit_work,
)

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))
from shared.vendor_process_surfaces import (  # noqa: E402
    VendorProcessInvocation,
    VendorProcessBlocked,
    as_completed_process,
    run_vendor_process,
)
from shared.sandbox_activation import (  # noqa: E402
    SandboxActivationContext,
    SandboxActivationError,
    resolve_activation_context,
)

logger = logging.getLogger(__name__)


def _run_cli_process(
    argv: list[str],
    *,
    input: str | None = None,
    capture_output: bool = True,
    text: bool = True,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    isolation: str = "none",
    activation_context: SandboxActivationContext | None = None,
) -> subprocess.CompletedProcess[str]:
    """Compatibility adapter over the one registered vendor-process backend."""

    if not capture_output or not text:
        raise ValueError("vendor process backend requires captured text output")
    invocation = VendorProcessInvocation(
        surface="review",
        argv=tuple(argv),
        cwd=Path(cwd or Path.cwd()),
        env=env or os.environ.copy(),
        timeout_seconds=timeout,
        isolation=isolation,  # type: ignore[arg-type]
        stdin_text=input,
        activation_context=activation_context,
    )
    return as_completed_process(invocation, run_vendor_process(invocation))


# ---------------------------------------------------------------------------
# Tier→model resolution from archetypes.yaml (sole authored roster).
# ---------------------------------------------------------------------------

def _archetype_roster() -> Any:
    """Import skills.shared.archetype_roster, tolerating path layouts."""
    try:
        from skills.shared import archetype_roster  # type: ignore[import-untyped]

        return archetype_roster
    except ImportError:
        shared = Path(__file__).resolve().parents[2] / "shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared.parent))
        try:
            from skills.shared import archetype_roster  # type: ignore[import-untyped]

            return archetype_roster
        except ImportError:
            # Last resort: load the module by file path.
            import importlib.util

            path = Path(__file__).resolve().parents[2] / "shared" / "archetype_roster.py"
            spec = importlib.util.spec_from_file_location("archetype_roster", path)
            if not spec or not spec.loader:
                raise
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod


def _resolve_review_model_spec(vendor: str) -> tuple[str | None, str | None]:
    """Resolve reviewer premium ``(model, thinking)`` for *vendor*."""
    try:
        roster = _archetype_roster()
        return roster.resolve_tier_for_provider(vendor, "premium")
    except Exception as exc:  # noqa: BLE001 — degrade to agents.yaml pins
        logger.warning("Could not resolve premium tier for %s: %s", vendor, exc)
        return None, None


def _derived_tier_fallbacks(vendor: str) -> list[str]:
    """Capacity fallbacks from standard then economy tiers."""
    try:
        roster = _archetype_roster()
        out: list[str] = []
        for tier in ("standard", "economy"):
            model, _ = roster.resolve_tier_for_provider(vendor, tier)
            if model and model not in out:
                out.append(model)
        return out
    except Exception:  # noqa: BLE001
        return []


def _thinking_cli_flags(vendor: str, thinking: str | None) -> list[str]:
    try:
        return list(_archetype_roster().thinking_cli_flags(vendor, thinking))
    except Exception:  # noqa: BLE001
        return []


def _strip_thinking_flags(vendor: str, cmd: list[str]) -> list[str]:
    """Remove effort/reasoning flags so tier thinking can be re-injected cleanly."""
    out: list[str] = []
    skip_next = False
    i = 0
    while i < len(cmd):
        if skip_next:
            skip_next = False
            i += 1
            continue
        tok = cmd[i]
        if vendor in {"claude_code", "claude"} and tok == "--effort":
            skip_next = True
            i += 1
            continue
        if vendor == "grok" and tok in {"--reasoning-effort", "--effort"}:
            skip_next = True
            i += 1
            continue
        if vendor == "codex" and tok == "-c" and i + 1 < len(cmd) and str(
            cmd[i + 1]
        ).startswith("model_reasoning_effort="):
            skip_next = True
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


# ---------------------------------------------------------------------------
# Canonical review-findings schema access (single source of truth). Imported
# lazily so the dispatcher still imports in environments that vendor only this
# file, and located by file path when the scripts dir is not on sys.path.
# ---------------------------------------------------------------------------

def _schema_mod() -> Any:
    """Return the ``review_findings_schema`` module, or ``None`` if absent."""
    try:
        import review_findings_schema  # type: ignore[import-untyped]

        return review_findings_schema
    except ImportError:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "review_findings_schema",
            Path(__file__).parent / "review_findings_schema.py",
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                return mod
            except Exception as exc:  # noqa: BLE001
                logger.warning("review_findings_schema load failed: %s", exc)
                return None
        return None


def _ocr_adapter_can_dispatch() -> bool:
    """Delegate the ocr vendor's real availability check to its own module.

    ocr-local's configured ``command`` is ``python3`` — always present —
    so the generic PATH check in ``can_dispatch`` cannot tell whether the
    `ocr` binary and its LLM endpoint are actually available
    (add-deterministic-review-preprocessing). Returns ``False`` (never
    available) when ``ocr_adapter`` itself cannot be imported: failing
    closed here means a broken install shows as Tier 3 (skip), not a
    Tier 1 vendor that only fails once dispatch is actually attempted.
    """
    try:
        import ocr_adapter

        return ocr_adapter.can_dispatch()
    except Exception:  # noqa: BLE001 — see docstring
        return False


_DIFF_FENCE_RE = re.compile(r"### Diff\n```diff\n(.*?)\n```", re.DOTALL)


def _extract_diff_from_prompt(prompt: str) -> str:
    """Pull the fenced diff block out of a review_packet-rendered prompt.

    Returns ``""`` when the prompt has no ``### Diff`` fence (a test-
    authored prompt, or a future packet format change) or when the fence
    holds only the empty-diff marker — the ingest-time line resolver then
    simply finds nothing to match against and every finding is kept with
    ``line_resolution: unresolved``, never an error.
    """
    match = _DIFF_FENCE_RE.search(prompt)
    if not match:
        return ""
    text = match.group(1)
    if text.strip() == "(empty-diff)":
        return ""
    return text


_RULE_GROUPS_SECTION_RE = re.compile(r"### Rule groups\n(.*?)(?=\n### |\Z)", re.DOTALL)
_APPLIES_TO_RE = re.compile(r"Applies to:\n((?:- .+\n?)+)")


def _extract_selected_files_from_prompt(prompt: str) -> list[str] | None:
    """Recover the packet's selected-file list from its rendered rule groups.

    ``review_rules.group_files_by_rule`` resolves every selected file to
    exactly one group (falling back to ``"(default)"``), and
    ``review_packet._render_rule_groups`` lists each group's files under an
    "Applies to:" bullet list — before any budget truncation runs — so this
    recovers the same selected set :mod:`file_selection` produced, without
    the dispatcher needing to import the packet-building path. Returns
    ``None`` when the prompt carries no rule-groups section (a hand-authored
    test prompt, or a packet format that predates this feature) or lists no
    files, so coverage scoring is simply skipped — same posture as
    ``_extract_diff_from_prompt``.
    """
    section_match = _RULE_GROUPS_SECTION_RE.search(prompt)
    if not section_match:
        return None
    paths: list[str] = []
    for block in _APPLIES_TO_RE.finditer(section_match.group(1)):
        for line in block.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                paths.append(line[2:])
    return paths or None


def _coverage_quorum_threshold(cwd: Path) -> float:
    """Resolve the coverage-eligibility threshold for *cwd* (D5).

    Reads the two-layer review-rules sidecar (project override over the
    embedded default) via :mod:`review_rules`, degrading to its documented
    default on any error — a missing or unreadable project file is already
    handled inside ``review_rules.load_config``; this catches the case
    where the module itself cannot be imported (a repo vendoring only this
    file).
    """
    try:
        import review_rules

        return review_rules.load_config(cwd).coverage_quorum_threshold
    except Exception:  # noqa: BLE001 — degrade to the documented default
        return 0.8


def _coerce_coverage_reasons(findings: dict[str, Any]) -> list[str]:
    """Fill a missing ``reason`` on each ``coverage.skipped[]`` entry in place.

    A vendor coverage block otherwise fails canonical-schema validation
    entirely for one missing string (the schema requires ``path`` and
    ``reason`` on every skipped entry) — the "Skipped file needs a reason"
    scenario names this: coercion fills ``reason: unspecified`` instead of
    losing the whole payload. Must run before ``_validate_findings_or_error``.
    """
    notes: list[str] = []
    coverage = findings.get("coverage")
    if not isinstance(coverage, dict):
        return notes
    skipped = coverage.get("skipped")
    if not isinstance(skipped, list):
        return notes
    for entry in skipped:
        if isinstance(entry, dict) and not entry.get("reason"):
            entry["reason"] = "unspecified"
            notes.append(f"coverage.skipped[{entry.get('path', '?')}].reason->unspecified")
    return notes


def _score_coverage(
    findings: dict[str, Any],
    selected_files: list[str] | None,
    quorum_threshold: float,
) -> tuple[float | None, str, str]:
    """Score a vendor's optional ``coverage`` block against selected files (D5).

    Returns ``(coverage_rate, coverage_eligibility, coverage_status)``.
    Writes the computed rate back into ``findings["coverage"]["rate"]`` —
    the canonical schema documents that field as dispatcher-computed. A
    vendor that emits no ``coverage`` block, or whose ``coverage`` cannot be
    scored because the selected-file list is unknown (the async-poll
    dispatch path does not thread the prompt through — see
    ``poll_for_result``), is full coverage, unreported: absent coverage
    never penalizes a vendor.
    """
    coverage = findings.get("coverage")
    if not isinstance(coverage, dict) or not selected_files:
        return None, "full", "unreported"
    selected = set(selected_files)
    if not selected:
        return None, "full", "unreported"
    reviewed = {p for p in (coverage.get("reviewed") or []) if isinstance(p, str)}
    rate = len(reviewed & selected) / len(selected)
    coverage["rate"] = rate
    eligibility = "partial" if rate < quorum_threshold else "full"
    return rate, eligibility, "reported"


def _validate_findings_or_error(
    findings: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate parsed vendor findings against the canonical schema.

    Returns ``(findings, None)`` when valid (or when validation is
    unavailable), and ``(None, error)`` when the findings violate the schema —
    so a drifted finding fails loudly here rather than flowing downstream into
    the consensus synthesizer as if it conformed.
    """
    if findings is None:
        return None, None
    mod = _schema_mod()
    if mod is None:
        # The canonical schema module is what makes this check meaningful.
        # Returning the payload as valid here would report success for findings
        # nothing ever inspected — the false-consensus failure ri-14 exists to
        # prevent — so an unloadable module fails the dispatch instead.
        msg = (
            "review-findings schema module could not be loaded; refusing to "
            "accept unvalidated findings (expected review_findings_schema.py "
            f"beside {Path(__file__).name})"
        )
        print(f"[ERROR] {msg}", file=sys.stderr)
        return None, msg
    try:
        errors = mod.validate_findings_payload(findings)
    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed
        # Includes ValidationUnavailableError (jsonschema missing) and a
        # missing/malformed canonical schema file. Every one of those means the
        # contract could not be checked, which is not the same as it holding.
        msg = f"review-findings validation could not run: {exc}"
        print(f"[ERROR] {msg}", file=sys.stderr)
        return None, msg
    if errors:
        detail = "; ".join(errors[:5])
        msg = f"Findings failed review-findings schema validation: {detail}"
        print(f"[WARN] {msg}", file=sys.stderr)
        return None, msg
    return findings, None


_PLACEHOLDER_ONLY_PATTERNS = (
    re.compile(
        r"^placeholder(?:"
        r"\s+while\s+(?:the\s+)?(?:review|analysis)\s+"
        r"(?:runs|is\s+(?:running|in[ -]progress))"
        r"|\s+pending(?:\s+(?:(?:plan|implementation|artifact)"
        r"(?:\s+artifact)?\s+)?review)?"
        r"|\s+until\s+(?:the\s+)?(?:review|analysis)\s+"
        r"(?:runs|completes?|finishes)"
        r")?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:review|analysis)(?:\s+is)?\s+"
        r"(?:pending|in[ -]progress|running)[.!]?$",
        re.IGNORECASE,
    ),
)


def _is_placeholder_message(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.strip().split())
    return any(pattern.fullmatch(normalized) for pattern in _PLACEHOLDER_ONLY_PATTERNS)


def _is_placeholder_only_response(
    findings: dict[str, Any],
    stdout: str,
) -> bool:
    """Return True only when the complete response is provisional text."""
    items = findings.get("findings") or []
    if items:
        descriptions = [
            item.get("description")
            for item in items
            if isinstance(item, dict)
        ]
        return bool(descriptions) and all(
            _is_placeholder_message(description) for description in descriptions
        )

    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(envelope, dict):
        return False
    return any(
        _is_placeholder_message(envelope.get(key))
        for key in ("text", "output", "response")
    )


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class SchemaInjectionError(RuntimeError):
    """Raised when the canonical review-findings schema cannot be injected.

    A configuration fault, not a vendor fault: agents.yaml asked for the
    schema sentinel and the schema could not be resolved to fill it.
    """


class ErrorClass(str, Enum):
    """Classification of vendor subprocess errors."""

    CAPACITY = "capacity_exhausted"
    AUTH = "auth_required"
    TRANSIENT = "transient"
    UNAVAILABLE = "vendor_unavailable"
    UNKNOWN = "unknown"


_CAPACITY_PATTERNS = ["429", "resource_exhausted", "capacity", "rate limit", "rate_limit"]
_AUTH_PATTERNS = ["401", "unauthenticated", "token expired", "login required", "unauthorized"]
_TRANSIENT_PATTERNS = ["500", "503", "unavailable", "internal server error"]
_UNAVAILABLE_PATTERNS = [
    "insufficient credits",
    "insufficient_credits",
    "payment required",
    "payment_required",
    "insufficient_quota",
]
# HTTP 402 as a standalone token — not part of a larger number ("8,402 items")
# or an identifier ("v402").
_UNAVAILABLE_402_RE = re.compile(r"(?<![\d,.\w])402(?![\d\w])")

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


# ---------------------------------------------------------------------------
# Degraded-gate reporting (OpenSpec introduce-fitness-function-gates, D6)
# ---------------------------------------------------------------------------

# Cross-vendor review needs at least two vendors. One vendor is a single
# opinion, not a convergence. Falling below this is a documented fail-open
# path, so it must announce itself rather than passing silently.
MIN_REVIEW_VENDORS = 2

DEGRADED_STATUS = "DEGRADED"


def report_degraded(what_was_not_checked: str) -> str:
    """Emit a DEGRADED line naming what was not checked and why.

    Returns the emitted line so callers can also record it in a report. Written
    to stderr so it survives callers that parse stdout as JSON.
    """
    line = f"{DEGRADED_STATUS}: {what_was_not_checked}"
    print(line, file=sys.stderr, flush=True)
    return line


def classify_error(text: str) -> ErrorClass:
    """Classify a vendor error from its output text.

    Accepts stderr OR stdout — some CLIs (pi) exit 0 with the provider's
    error body on stdout (issue #383), so classification cannot assume the
    text arrived on stderr. UNAVAILABLE is checked first: a billing body
    ("Insufficient credits … upgrade your limit") contains words that would
    otherwise false-positive the capacity patterns.
    """
    lower = text.lower()
    if any(p in lower for p in _UNAVAILABLE_PATTERNS) or _UNAVAILABLE_402_RE.search(lower):
        return ErrorClass.UNAVAILABLE
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
    """Structured-status polling configuration for async dispatch modes."""

    command_template: list[str]
    result_protocol: str = "vendor-envelope-v1"
    interval_seconds: int = 30
    timeout_seconds: int = 600


@dataclass
class ModeConfig:
    """CLI args for a single dispatch mode."""

    args: list[str]
    async_dispatch: bool = False
    poll: PollConfig | None = None
    isolation: str | None = None
    enforcement_scope: str = "execution"
    write_capable: bool = False


@dataclass
class CliConfig:
    """CLI dispatch configuration for an agent."""

    command: str
    dispatch_modes: dict[str, ModeConfig]
    model_flag: str
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)
    prompt_via_stdin: bool = False
    # When set, the prompt is attached as the value of this flag (e.g. agy's
    # ``--prompt``) rather than as a trailing positional or via stdin. E7:
    # antigravity ignores stdin and a trailing positional — the prompt must be
    # the value of ``--prompt``/``-p``.
    prompt_via_flag: str | None = None
    # Env var the CLI resolves its provider credential from (pi:
    # OPENROUTER_API_KEY). A present binary with this var unset cannot serve
    # a request — can_dispatch() fails closed on it (issue #383).
    api_key_env: str = ""
    state_env_keys: list[str] = field(default_factory=list)


@dataclass
class SdkConfig:
    """SDK dispatch configuration for an agent."""

    package: str
    model: str
    method: str = "messages.create"
    model_fallbacks: list[str] = field(default_factory=list)
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


class VendorResultProtocolError(ValueError):
    """Raised when a vendor does not emit the contracted result envelope."""


@dataclass(frozen=True)
class VendorResultEnvelope:
    """Versioned, normalized vendor result returned by CLI adapter commands."""

    version: int
    state: str
    vendor_task_id: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in {"succeeded", "failed", "cancelled"}

    def as_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation persisted in the ledger."""
        return {
            "version": self.version,
            "state": self.state,
            "vendor_task_id": self.vendor_task_id,
            "result": self.result,
            "error": self.error,
        }


def parse_vendor_result_envelope(payload: str) -> VendorResultEnvelope:
    """Parse one CLI result without a legacy stdout-regex fallback."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VendorResultProtocolError("invalid JSON vendor result envelope") from exc
    if not isinstance(data, dict):
        raise VendorResultProtocolError("vendor result envelope must be an object")
    allowed_fields = {"version", "state", "vendor_task_id", "result", "error"}
    unexpected_fields = sorted(set(data) - allowed_fields)
    if unexpected_fields:
        raise VendorResultProtocolError(
            f"vendor result envelope has unexpected field: {unexpected_fields[0]}"
        )
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise VendorResultProtocolError("unsupported vendor result envelope version")
    state = data.get("state")
    valid_states = {"submitted", "running", "succeeded", "failed", "cancelled"}
    if state not in valid_states:
        raise VendorResultProtocolError("vendor result envelope has invalid state")
    vendor_task_id = data.get("vendor_task_id")
    if vendor_task_id is not None and not isinstance(vendor_task_id, str):
        raise VendorResultProtocolError("vendor_task_id must be a string or null")
    if vendor_task_id == "":
        raise VendorResultProtocolError("vendor_task_id must not be empty")
    if state in {"submitted", "running"} and not vendor_task_id:
        raise VendorResultProtocolError(
            "nonterminal vendor result envelope requires vendor_task_id"
        )
    result = data.get("result")
    error = data.get("error")
    if result is not None and not isinstance(result, dict):
        raise VendorResultProtocolError("vendor result envelope result must be an object")
    if error is not None and not isinstance(error, dict):
        raise VendorResultProtocolError("vendor result envelope error must be an object")
    if state == "succeeded" and result is None:
        raise VendorResultProtocolError(
            "succeeded vendor result envelope requires result"
        )
    if state in {"failed", "cancelled"} and error is None:
        raise VendorResultProtocolError(
            f"{state} vendor result envelope requires error"
        )
    if isinstance(error, dict):
        message = error.get("message")
        if not isinstance(message, str):
            raise VendorResultProtocolError(
                "vendor result envelope error requires a message"
            )
        if not message:
            raise VendorResultProtocolError("error message must not be empty")
        error_code = error.get("code")
        if error_code is not None and (not isinstance(error_code, str) or not error_code):
            raise VendorResultProtocolError("error code must be a non-empty string")
    return VendorResultEnvelope(
        version=1,
        state=state,
        vendor_task_id=vendor_task_id,
        result=result,
        error=error,
    )


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
    ledger_task_id: str | None = None
    # OpenRouter/OpenAI-compatible generation id for spend reconciliation
    # (OpenSpec add-adaptive-model-router, D7/D10). None for CLI/SDK adapters.
    generation_id: str | None = None
    raw_stdout: str | None = None
    raw_stderr: str | None = None
    coercions: list[str] = field(default_factory=list)
    # Count of findings whose existing_code snippet did not resolve to a
    # line_range (line_resolution="unresolved"). 0 when resolution did not
    # run (no packet_diff available to _ingest_stdout) — see
    # _extract_diff_from_prompt and line_resolver.resolve_all.
    unanchored_findings: int = 0
    # Per-vendor coverage scoring (add-deterministic-review-preprocessing,
    # D5) — see _score_coverage. coverage_rate is None when the vendor
    # reported no coverage block, or none could be scored (no selected-file
    # list available); coverage_eligibility is "full" unless the rate fell
    # below the contracted threshold; coverage_status is "unreported" unless
    # a rate was actually computed.
    coverage_rate: float | None = None
    coverage_eligibility: str = "full"
    coverage_status: str = "unreported"
    # Exact lane and optional capacity metadata are additive for old callers.
    agent_id: str | None = None
    capacity_scope: str | None = None
    capacity_model: str | None = None
    capacity_reset_at: str | None = None
    capacity_retry_after_seconds: int | None = None
    # Immutable routing/enforcement evidence for one process attempt.
    routing_digest: str | None = None
    requested_isolation: str | None = None
    applied_isolation: str | None = None
    endpoint_digest: str | None = None
    policy_revision: str | None = None
    runtime_version: str | None = None
    settings_digest: str | None = None
    snapshot_content_digest: str | None = None
    collection_state: str | None = None
    cleanup_status: str | None = None
    cleanup_residual_paths: list[str] = field(default_factory=list)
    sandbox_host_commit_required: bool = False


def _notify_capacity(
    callback: Callable[[ReviewResult], Any] | None,
    result: ReviewResult,
) -> None:
    """Keep optional reporting failures from changing dispatch outcomes."""
    if callback is None:
        return
    try:
        callback(result)
    except Exception as exc:  # noqa: BLE001 — reporting is best-effort
        logger.warning(
            "Capacity reporting failed for agent_id=%s: %s",
            result.agent_id,
            exc,
        )


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
        ledger_submitter: Callable[..., dict[str, Any]] = try_submit_work,
        ledger_completer: Callable[..., dict[str, Any]] = try_complete_work,
    ) -> None:
        self.agent_id = agent_id
        self.vendor = vendor
        self.cli_config = cli_config
        self.transport = transport
        self._ledger_submitter = ledger_submitter
        self._ledger_completer = ledger_completer

    def _sandbox_activation_context(
        self,
        mode: str,
        cwd: Path,
        model: str | None,
    ) -> SandboxActivationContext | None:
        mode_config = self.cli_config.dispatch_modes[mode]
        if (mode_config.isolation or "none") != "sandbox":
            return None
        return resolve_activation_context(
            agent_id=self.agent_id,
            dispatch_mode=mode,
            model=model or self.cli_config.model or "vendor-default",
            worktree_root=cwd,
        )

    @staticmethod
    def _ledger_response_error(response: dict[str, Any]) -> str:
        data = response.get("data")
        reason = response.get("reason") or response.get("error")
        if isinstance(data, dict):
            reason = data.get("reason") or data.get("error") or reason
        return str(reason or response.get("status") or "unknown ledger error")

    def _open_completion_ledger(self, mode: str) -> tuple[str | None, str | None]:
        """Create and claim one queue row before remote work can start."""
        correlation_id = str(uuid4())
        task_type = f"vendor-dispatch-{correlation_id}"
        response = self._ledger_submitter(
            task_type=task_type,
            task_description=(
                f"Track {self.agent_id} {mode} vendor dispatch {correlation_id}"
            ),
            input_data={
                "correlation_id": correlation_id,
                "vendor": self.vendor,
                "vendor_agent_id": self.agent_id,
                "dispatch_mode": mode,
            },
            priority=5,
            claim_immediately=True,
        )
        data = response.get("data")
        ledger_task_id = data.get("task_id") if isinstance(data, dict) else None
        if (
            response.get("status") != "ok"
            or not isinstance(data, dict)
            or data.get("success") is False
            or not isinstance(ledger_task_id, str)
            or not ledger_task_id
        ):
            return None, self._ledger_response_error(response)

        if data.get("status") != "claimed":
            return None, "atomic ledger submission did not return claimed status"
        return ledger_task_id, None

    def _complete_completion_ledger(
        self,
        ledger_task_id: str,
        *,
        success: bool,
        envelope: VendorResultEnvelope | None = None,
        error_message: str | None = None,
    ) -> str | None:
        """Persist terminal state and return an error when it was not recorded."""
        result = (
            {"vendor_result": envelope.as_dict()}
            if envelope is not None
            else None
        )
        response = self._ledger_completer(
            task_id=ledger_task_id,
            agent_id=None,
            success=success,
            result=result,
            error_message=error_message,
        )
        data = response.get("data")
        if (
            response.get("status") != "ok"
            or not isinstance(data, dict)
            or data.get("success") is not True
        ):
            return self._ledger_response_error(response)
        return None

    def can_dispatch(self, mode: str) -> bool:
        """Check if this adapter can dispatch the given mode.

        A binary on PATH is not enough when the config declares a required
        credential env var: pi with OPENROUTER_API_KEY unset cannot serve a
        single request, so it must not count as available (issue #383).

        The ocr vendor is a further special case: its configured
        ``command`` is ``python3`` (the wrapper script's interpreter,
        always present), which cannot itself indicate whether the `ocr`
        binary and its LLM endpoint are actually available — see
        ``_ocr_adapter_can_dispatch``.
        """
        if mode not in self.cli_config.dispatch_modes:
            return False
        if shutil.which(self.cli_config.command) is None:
            return False
        if self.cli_config.api_key_env and not os.environ.get(self.cli_config.api_key_env):
            return False
        if self.vendor == "ocr" and not _ocr_adapter_can_dispatch():
            return False
        return True

    def _resolve_args(self, args: list[str]) -> list[str]:
        """Expand config placeholders in a mode's args.

        The grok schema sentinel (``@review-findings-schema``) is replaced with
        the schema derived from the canonical ``review-findings.schema.json``.
        This is what keeps agents.yaml from carrying a hand-copied — and
        drift-prone — ``--json-schema`` blob: the schema is injected here from
        the single canonical file at dispatch time.

        Raises :class:`SchemaInjectionError` when the schema cannot be resolved.
        Dropping ``--json-schema`` and dispatching anyway used to look like
        graceful degradation, but grok only populates ``structuredOutput`` when
        that flag is present (see the agents.yaml comment on the review mode) —
        so the "degraded" path reliably produced output the dispatcher then
        rejected as invalid JSON, while the real cause (an unresolvable
        canonical schema) appeared only as a warning. Failing here names the
        actual problem.
        """
        mod = _schema_mod()
        sentinel = getattr(mod, "GROK_SCHEMA_SENTINEL", "@review-findings-schema")
        if sentinel not in args:
            return list(args)

        if mod is None:
            raise SchemaInjectionError(
                "review_findings_schema module could not be loaded, so the "
                f"{sentinel!r} placeholder in agents.yaml cannot be resolved"
            )
        try:
            schema_arg = mod.grok_schema_arg()
        except Exception as exc:  # noqa: BLE001 — re-raised with context
            raise SchemaInjectionError(
                f"could not derive the canonical review-findings schema: {exc}"
            ) from exc

        return [schema_arg if arg == sentinel else arg for arg in args]

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

        ``thinking`` is translated to vendor CLI flags from the authored
        tier map (archetypes.yaml), not from hard-coded agents.yaml args.
        """
        mode_config = self.cli_config.dispatch_modes[mode]
        cmd = [self.cli_config.command, *self._resolve_args(mode_config.args)]
        # Drop any stale effort flags left in agents.yaml; tier thinking wins.
        cmd = _strip_thinking_flags(self.vendor, cmd)
        thinking_flags = _thinking_cli_flags(self.vendor, thinking)
        if thinking_flags:
            # Insert after the binary so mode flags still lead.
            cmd[1:1] = thinking_flags
        effective_model = model or self.cli_config.model
        if effective_model:
            cmd.extend([self.cli_config.model_flag, effective_model])
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
        thinking: str | None = None,
        repair_attempted: bool = False,
        capacity_callback: Callable[[ReviewResult], Any] | None = None,
    ) -> ReviewResult:
        """Dispatch a review with model fallback on capacity errors.

        Tries the primary model first, then each fallback in order.
        Returns the first successful result or the final failure.

        Args:
            archetype_model: Optional model override from archetype resolution.
                When provided, overrides the agent's default primary model
                but reuses the existing fallback chain (design decision D4).
            thinking: Optional thinking/effort level from the tier map; when
                omitted, resolved from archetypes.yaml premium for this vendor.
        """
        capacity_callback = capacity_callback or getattr(
            self, "_capacity_callback", None
        )
        resolved_model, resolved_thinking = _resolve_review_model_spec(self.vendor)
        primary = archetype_model or self.cli_config.model or resolved_model
        effective_thinking = thinking if thinking is not None else resolved_thinking
        models_to_try: list[str | None] = [primary]
        # Prefer authored standard/economy tiers as capacity fallbacks when
        # agents.yaml does not declare an explicit chain.
        fallbacks = list(self.cli_config.model_fallbacks)
        if not fallbacks:
            fallbacks = _derived_tier_fallbacks(self.vendor)
        models_to_try.extend(fallbacks)

        models_attempted: list[str] = []
        last_error = ""
        last_error_class = ErrorClass.UNKNOWN
        dispatch_start = time.monotonic()

        for model_index, model in enumerate(models_to_try):
            has_fallback = model_index < len(models_to_try) - 1
            model_name = model or "(default)"
            models_attempted.append(model_name)

            try:
                cmd = self.build_command(
                    mode, prompt, model, thinking=effective_thinking
                )
            except SchemaInjectionError as exc:
                # Fail this vendor, not the whole panel: the other vendors'
                # dispatches are independent and a partial panel beats none.
                # Retrying the fallback models would not help — schema
                # resolution is model-independent.
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - dispatch_start,
                    error=f"Schema injection failed: {exc}",
                    error_class=ErrorClass.UNKNOWN,
                )
            stdin_text = prompt if self.cli_config.prompt_via_stdin else None
            start = time.monotonic()

            try:
                result = _run_cli_process(
                    cmd,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=str(cwd),
                    isolation=(
                        self.cli_config.dispatch_modes[mode].isolation or "none"
                    ),
                    activation_context=self._sandbox_activation_context(
                        mode, cwd, model,
                    ),
                )
                elapsed = time.monotonic() - start

                if result.returncode == 0:
                    ingested = self._ingest_stdout(
                        result.stdout,
                        result.stderr,
                        elapsed=elapsed,
                        model_name=model_name,
                        models_attempted=models_attempted,
                        packet_diff=_extract_diff_from_prompt(prompt),
                        selected_files=_extract_selected_files_from_prompt(prompt),
                        coverage_quorum_threshold=_coverage_quorum_threshold(cwd),
                    )
                    self._stamp_process_metadata(ingested, result, mode=mode)
                    if ingested.success or ingested.error_class in (
                        ErrorClass.AUTH, ErrorClass.UNAVAILABLE,
                    ):
                        return ingested
                    if ingested.error == "non_substantive_placeholder":
                        return ingested
                    if ingested.error_class == ErrorClass.CAPACITY:
                        last_error = ingested.error or ""
                        last_error_class = ErrorClass.CAPACITY
                        if has_fallback and capacity_callback is not None:
                            _notify_capacity(capacity_callback, ReviewResult(
                                vendor=self.vendor,
                                success=False,
                                agent_id=self.agent_id,
                                error=last_error,
                                error_class=ErrorClass.CAPACITY,
                                capacity_scope="model",
                                capacity_model=model_name,
                            ))
                        continue
                    if not repair_attempted:
                        repair_prompt = (
                            f"{prompt}\n\nPREVIOUS OUTPUT FAILED VALIDATION:\n"
                            f"{ingested.error or 'not valid JSON'}\n"
                            "Emit ONLY a JSON object with a top-level `findings` "
                            "array. No prose.\n"
                        )
                        return self.dispatch(
                            mode,
                            repair_prompt,
                            cwd,
                            timeout_seconds=timeout_seconds,
                            archetype_model=archetype_model,
                            repair_attempted=True,
                            capacity_callback=capacity_callback,
                        )
                    return ingested
                else:
                    # Non-zero exit — classify error
                    last_error = result.stderr
                    last_error_class = classify_error(result.stderr)

                if last_error_class in (ErrorClass.AUTH, ErrorClass.UNAVAILABLE):
                    # Neither auth nor billing/entitlement errors can be fixed
                    # by model fallback — they are account-scoped.
                    relogin = _relogin_hint(self.cli_config.command)
                    if last_error_class == ErrorClass.AUTH:
                        summary = f"Auth expired. Run: {relogin}"
                    else:
                        summary = (
                            f"Vendor unavailable (billing/credits): "
                            f"{last_error[:500] if last_error else 'no error output'}"
                        )
                    msg = (
                        f"[WARN] {self.vendor} review failed: "
                        f"{last_error_class.value}.\n       {summary}"
                    )
                    print(msg, file=sys.stderr)
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        models_attempted=models_attempted,
                        elapsed_seconds=time.monotonic() - start,
                        error=summary,
                        error_class=last_error_class,
                    )

                if last_error_class == ErrorClass.CAPACITY:
                    # Report this model before fallback; final success must not erase it.
                    if has_fallback and capacity_callback is not None:
                        _notify_capacity(capacity_callback, ReviewResult(
                            vendor=self.vendor,
                            success=False,
                            agent_id=self.agent_id,
                            error=last_error[:500] if last_error else "capacity_exhausted",
                            error_class=ErrorClass.CAPACITY,
                            capacity_scope="model",
                            capacity_model=model_name,
                        ))
                    logger.info(
                        "%s model %s capacity exhausted, trying fallback",
                        self.vendor, model_name,
                    )
                    continue

                # Non-capacity, non-auth error — don't retry
                break

            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - start
                timed_out_stdout = exc.output if isinstance(exc.output, str) else None
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    error=f"Timeout after {timeout_seconds}s",
                    error_class=ErrorClass.TRANSIENT,
                    raw_stdout=timed_out_stdout,
                )
            except (OSError, SandboxActivationError) as exc:
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - start,
                    error=f"Sandbox enforcement blocked dispatch: {exc}",
                    error_class=ErrorClass.UNKNOWN,
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

    def _stamp_process_metadata(
        self,
        review: ReviewResult,
        process: subprocess.CompletedProcess[str],
        *,
        mode: str,
    ) -> ReviewResult:
        metadata = getattr(process, "sandbox_metadata", {})
        if not isinstance(metadata, dict):
            return review
        for field_name in (
            "routing_digest", "requested_isolation", "applied_isolation",
            "endpoint_digest", "policy_revision", "runtime_version",
            "settings_digest", "snapshot_content_digest", "cleanup_status",
        ):
            value = metadata.get(field_name)
            if value is not None:
                setattr(review, field_name, value)
        residual = metadata.get("cleanup_residual_paths")
        if isinstance(residual, list) and all(isinstance(path, str) for path in residual):
            review.cleanup_residual_paths = list(residual)
        review.collection_state = "collected" if review.success else "failed"
        mode_config = self.cli_config.dispatch_modes[mode]
        review.sandbox_host_commit_required = bool(
            mode_config.write_capable
            and review.requested_isolation == "sandbox"
            and review.success
        )
        return review

    def _ingest_stdout(
        self,
        stdout: str,
        stderr: str,
        *,
        elapsed: float,
        model_name: str,
        models_attempted: list[str],
        enforce_empty_findings_grace: bool = True,
        packet_diff: str | None = None,
        selected_files: list[str] | None = None,
        coverage_quorum_threshold: float = 0.8,
    ) -> ReviewResult:
        """Parse, coerce, validate, stamp, line-resolve, and coverage-score
        one vendor stdout blob.

        ``packet_diff`` is the raw diff text the reviewer was shown (see
        ``_extract_diff_from_prompt``). When supplied and non-empty, every
        validated finding runs through ``line_resolver.resolve_all`` so a
        vendor-supplied ``existing_code`` snippet gets a ``line_range``
        without a model call. ``selected_files`` is the packet's selected
        paths (see ``_extract_selected_files_from_prompt``), used to score
        an optional ``coverage`` block via ``_score_coverage``. Both are
        ``None`` on the async-poll path today (it does not thread the
        prompt through) — resolution and coverage scoring are simply
        skipped, findings are returned exactly as validated, same as before
        either parameter existed.
        """
        from review_findings_schema import (
            coerce_findings_payload,
            empty_findings_min_seconds,
            stamp_judgment_ingest,
        )

        raw = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        excerpt = raw[:500]
        findings = self._parse_findings(stdout)
        coercions: list[str] = []
        unanchored_findings = 0
        if findings is not None:
            coverage_notes = _coerce_coverage_reasons(findings)
            findings, generic_notes = coerce_findings_payload(findings)
            coercions = coverage_notes + generic_notes
            findings, schema_error = _validate_findings_or_error(findings)
            if findings is not None:
                findings = stamp_judgment_ingest(findings)
                coverage_rate, coverage_eligibility, coverage_status = _score_coverage(
                    findings, selected_files, coverage_quorum_threshold,
                )
                if packet_diff:
                    resolved, unanchored_findings = line_resolver.resolve_all(
                        findings.get("findings", []), packet_diff,
                    )
                    findings["findings"] = resolved
                if _is_placeholder_only_response(findings, stdout):
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        model_used=model_name,
                        models_attempted=models_attempted,
                        elapsed_seconds=elapsed,
                        error="non_substantive_placeholder",
                        raw_stdout=stdout,
                        raw_stderr=stderr or None,
                        coercions=coercions,
                    )
                arr = findings.get("findings") or []
                if (
                    enforce_empty_findings_grace
                    and arr == []
                    and elapsed < empty_findings_min_seconds()
                ):
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        model_used=model_name,
                        models_attempted=models_attempted,
                        elapsed_seconds=elapsed,
                        error="empty_findings_too_fast",
                        raw_stdout=stdout,
                        raw_stderr=stderr or None,
                        coercions=coercions,
                    )
                return ReviewResult(
                    vendor=self.vendor,
                    success=True,
                    findings=findings,
                    model_used=model_name,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    raw_stdout=stdout,
                    raw_stderr=stderr or None,
                    coercions=coercions,
                    unanchored_findings=unanchored_findings,
                    coverage_rate=coverage_rate,
                    coverage_eligibility=coverage_eligibility,
                    coverage_status=coverage_status,
                )
            zero_exit_class = classify_error(raw)
            if zero_exit_class in (ErrorClass.AUTH, ErrorClass.UNAVAILABLE, ErrorClass.CAPACITY):
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    model_used=model_name,
                    models_attempted=models_attempted,
                    elapsed_seconds=elapsed,
                    error=excerpt or schema_error,
                    error_class=zero_exit_class,
                    raw_stdout=stdout,
                    raw_stderr=stderr or None,
                    coercions=coercions,
                )
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                model_used=model_name,
                models_attempted=models_attempted,
                elapsed_seconds=elapsed,
                error=schema_error or f"Invalid JSON output: {excerpt}",
                raw_stdout=stdout,
                raw_stderr=stderr or None,
                coercions=coercions,
            )

        zero_exit_class = classify_error(raw)
        if zero_exit_class in (ErrorClass.AUTH, ErrorClass.UNAVAILABLE, ErrorClass.CAPACITY):
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                model_used=model_name,
                models_attempted=models_attempted,
                elapsed_seconds=elapsed,
                error=excerpt,
                error_class=zero_exit_class,
                raw_stdout=stdout,
                raw_stderr=stderr or None,
            )
        return ReviewResult(
            vendor=self.vendor,
            success=False,
            model_used=model_name,
            models_attempted=models_attempted,
            elapsed_seconds=elapsed,
            error=(
                f"Invalid JSON output: {excerpt}" if excerpt
                else "Invalid JSON output (empty stdout)"
            ),
            raw_stdout=stdout,
            raw_stderr=stderr or None,
        )

    @staticmethod
    def _extract_findings(data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract findings from a parsed JSON dict.

        Handles both direct findings objects and vendor CLI envelopes. grok
        ``--output-format json --json-schema`` places the schema-conforming
        object under ``structuredOutput`` (E6), while agy places the schema
        object under ``structured_output`` or JSON text under ``response``.
        Unwrap any when the top level is not already a findings object.
        """
        if "findings" in data:
            return data
        # grok uses structuredOutput; agy uses structured_output or response.
        # Each envelope may carry the parsed object or schema-valid JSON text.
        for key in ("structuredOutput", "structured_output", "response"):
            nested = data.get(key)
            if isinstance(nested, dict) and "findings" in nested:
                return nested
            if isinstance(nested, str):
                try:
                    inner = json.loads(nested)
                    if isinstance(inner, dict) and "findings" in inner:
                        return inner
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _parse_json_blob(text: str) -> dict[str, Any] | None:
        """Parse a findings object from a single text blob.

        Handles a bare JSON object, vendor envelopes (grok
        ``structuredOutput``, agy ``structured_output``, and agy
        ``response``), and prose wrapped around the JSON.
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
        capacity_callback: Callable[[ReviewResult], Any] | None = None,
    ) -> ReviewResult:
        """Open a ledger lifecycle, submit remote work, and return both IDs."""
        capacity_callback = capacity_callback or getattr(
            self, "_capacity_callback", None
        )
        mode_config = self.cli_config.dispatch_modes[mode]
        if not mode_config.async_dispatch or not mode_config.poll:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Mode is not configured for async dispatch",
            )
        if mode_config.poll.result_protocol != "vendor-envelope-v1":
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                error=(
                    "Unsupported result protocol: "
                    f"{mode_config.poll.result_protocol}"
                ),
            )

        ledger_task_id, ledger_error = self._open_completion_ledger(mode)
        if ledger_task_id is None:
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                error=f"Completion ledger submission failed: {ledger_error}",
                error_class=ErrorClass.UNKNOWN,
            )

        def fail(
            message: str,
            *,
            error_class: ErrorClass = ErrorClass.UNKNOWN,
            elapsed: float = 0.0,
            envelope: VendorResultEnvelope | None = None,
        ) -> ReviewResult:
            completion_error = self._complete_completion_ledger(
                ledger_task_id,
                success=False,
                envelope=envelope,
                error_message=message,
            )
            if completion_error:
                message = (
                    f"{message}; completion ledger update failed: "
                    f"{completion_error}"
                )
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                models_attempted=models_attempted,
                elapsed_seconds=elapsed,
                error=message,
                error_class=error_class,
                ledger_task_id=ledger_task_id,
            )

        # Model fallback: prefer archetype premium, then agents.yaml, then tiers.
        resolved_model, resolved_thinking = _resolve_review_model_spec(self.vendor)
        primary = self.cli_config.model or resolved_model
        models_to_try: list[str | None] = [primary]
        fallbacks = list(self.cli_config.model_fallbacks) or _derived_tier_fallbacks(
            self.vendor
        )
        models_to_try.extend(fallbacks)

        models_attempted: list[str] = []

        for model_index, model in enumerate(models_to_try):
            has_fallback = model_index < len(models_to_try) - 1
            model_name = model or "(default)"
            models_attempted.append(model_name)

            try:
                cmd = self.build_command(
                    mode, prompt, model, thinking=resolved_thinking
                )
            except SchemaInjectionError as exc:
                # Same posture as the sync path: fail this vendor loudly rather
                # than submitting a schema-less async task whose result would
                # be unparseable for a reason the logs never name.
                return fail(
                    f"Schema injection failed: {exc}",
                )
            stdin_text = prompt if self.cli_config.prompt_via_stdin else None
            start = time.monotonic()

            try:
                result = _run_cli_process(
                    cmd,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=120,  # submit timeout (not execution timeout)
                    cwd=str(cwd),
                    isolation=mode_config.isolation or "none",
                    activation_context=self._sandbox_activation_context(
                        mode, cwd, model,
                    ),
                )
            except subprocess.TimeoutExpired:
                return fail(
                    "Timeout submitting async task",
                    error_class=ErrorClass.TRANSIENT,
                )
            except (OSError, SandboxActivationError) as exc:
                return fail(
                    f"Async submission command failed: {exc}",
                    error_class=ErrorClass.UNKNOWN,
                    elapsed=time.monotonic() - start,
                )

            elapsed = time.monotonic() - start

            # Process errors before reading the structured envelope.
            if result.returncode != 0:
                error_class = classify_error(result.stderr)
                if error_class == ErrorClass.AUTH:
                    relogin = _relogin_hint(self.cli_config.command)
                    print(
                        f"[WARN] {self.vendor} async dispatch failed: "
                        f"auth expired.\n       Run: {relogin}",
                        file=sys.stderr,
                    )
                    return fail(
                        f"Auth expired. Run: {relogin}",
                        error_class=ErrorClass.AUTH,
                        elapsed=elapsed,
                    )
                if error_class == ErrorClass.CAPACITY:
                    if has_fallback and capacity_callback is not None:
                        _notify_capacity(capacity_callback, ReviewResult(
                            vendor=self.vendor,
                            success=False,
                            agent_id=self.agent_id,
                            error=result.stderr[:500] or "capacity_exhausted",
                            error_class=ErrorClass.CAPACITY,
                            capacity_scope="model",
                            capacity_model=model_name,
                        ))
                    logger.info(
                        "%s async model %s capacity exhausted%s",
                        self.vendor,
                        model_name,
                        ", trying fallback" if has_fallback else "",
                    )
                    continue
                # Non-retryable error
                return fail(
                    result.stderr[:500] or "async submission command failed",
                    error_class=error_class,
                    elapsed=elapsed,
                )

            try:
                envelope = parse_vendor_result_envelope(result.stdout)
            except VendorResultProtocolError as exc:
                return fail(
                    f"Invalid structured async submission: {exc}",
                    elapsed=elapsed,
                )
            if envelope.is_terminal:
                return fail(
                    (envelope.error or {}).get(
                        "message", "async submission was terminal"
                    ),
                    elapsed=elapsed,
                    envelope=envelope,
                )
            logger.info(
                "Async task submitted for %s: vendor_task_id=%s ledger_task_id=%s",
                self.vendor,
                envelope.vendor_task_id,
                ledger_task_id,
            )
            return ReviewResult(
                vendor=self.vendor,
                success=True,
                models_attempted=models_attempted,
                elapsed_seconds=elapsed,
                async_dispatch=True,
                task_id=envelope.vendor_task_id,
                ledger_task_id=ledger_task_id,
            )

        # All models exhausted
        return fail(
            "All models exhausted for async dispatch",
            error_class=ErrorClass.CAPACITY,
        )

    def poll_for_result(
        self,
        task_id: str,
        poll_config: PollConfig,
        cwd: Path | None = None,
        *,
        review_started_at: float | None = None,
        ledger_task_id: str | None = None,
        isolation: str = "none",
    ) -> ReviewResult:
        """Poll structured status and persist terminal state before ingestion.

        Args:
            task_id: Vendor task identifier from the submission envelope.
            poll_config: Polling configuration from the mode config.
            cwd: Working directory for poll commands (optional).
            review_started_at: Local monotonic timestamp from before submission,
                when the caller owns the submission lifecycle.
            ledger_task_id: Coordinator work id created before vendor launch.

        Returns:
            ReviewResult with findings if successful, error otherwise.
        """
        if not ledger_task_id:
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                error="Completion ledger task id is required for async polling",
                error_class=ErrorClass.UNKNOWN,
                task_id=task_id,
            )

        poll_cmd = [
            arg.replace("{task_id}", task_id)
            for arg in poll_config.command_template
        ]
        poll_mode = next(
            (
                name
                for name, config in self.cli_config.dispatch_modes.items()
                if config.poll is poll_config or config.poll == poll_config
            ),
            "alternative",
        )

        start = time.monotonic()
        elapsed_start = review_started_at if review_started_at is not None else start
        deadline = start + poll_config.timeout_seconds
        attempts = 0
        enforcement_block: str | None = None

        while time.monotonic() < deadline:
            attempts += 1
            logger.info(
                "Polling %s task %s (attempt %d)", self.vendor, task_id, attempts,
            )

            try:
                result = _run_cli_process(
                    poll_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(cwd) if cwd else None,
                    isolation=isolation,
                    activation_context=(
                        self._sandbox_activation_context(
                            poll_mode,
                            cwd or Path.cwd(),
                            self.cli_config.model,
                        )
                        if isolation == "sandbox"
                        else None
                    ),
                )
            except subprocess.TimeoutExpired:
                logger.warning("Poll command timed out, retrying")
                time.sleep(poll_config.interval_seconds)
                continue
            except (VendorProcessBlocked, SandboxActivationError) as exc:
                enforcement_block = str(exc)
                logger.warning("Poll enforcement blocked, retrying: %s", exc)
                time.sleep(poll_config.interval_seconds)
                continue
            except OSError as exc:
                message = f"Async status command failed: {exc}"
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=False,
                    error_message=message,
                )
                if ledger_error:
                    message += f"; completion ledger update failed: {ledger_error}"
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - elapsed_start,
                    error=message,
                    error_class=ErrorClass.UNKNOWN,
                    task_id=task_id,
                    ledger_task_id=ledger_task_id,
                )

            if result.returncode != 0:
                message = result.stderr[:500] or "async status command failed"
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=False,
                    error_message=message,
                )
                if ledger_error:
                    message += f"; completion ledger update failed: {ledger_error}"
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - elapsed_start,
                    error=message,
                    error_class=classify_error(result.stderr),
                    task_id=task_id,
                    ledger_task_id=ledger_task_id,
                )
            try:
                envelope = parse_vendor_result_envelope(result.stdout)
            except VendorResultProtocolError as exc:
                message = f"Invalid structured async status: {exc}"
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=False,
                    error_message=message,
                )
                if ledger_error:
                    message += f"; completion ledger update failed: {ledger_error}"
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - elapsed_start,
                    error=message,
                    error_class=ErrorClass.UNKNOWN,
                    task_id=task_id,
                    ledger_task_id=ledger_task_id,
                )
            if envelope.vendor_task_id != task_id:
                message = (
                    "Invalid structured async status: vendor_task_id does not "
                    "match submitted task"
                )
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=False,
                    envelope=envelope,
                    error_message=message,
                )
                if ledger_error:
                    message += f"; completion ledger update failed: {ledger_error}"
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - elapsed_start,
                    error=message,
                    error_class=ErrorClass.UNKNOWN,
                    task_id=task_id,
                    ledger_task_id=ledger_task_id,
                )
            if envelope.state in {"failed", "cancelled"}:
                message = (envelope.error or {}).get("message", envelope.state)
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=False,
                    envelope=envelope,
                    error_message=message,
                )
                if ledger_error:
                    message += f"; completion ledger update failed: {ledger_error}"
                return ReviewResult(
                    vendor=self.vendor,
                    success=False,
                    elapsed_seconds=time.monotonic() - elapsed_start,
                    error=message,
                    error_class=ErrorClass.UNKNOWN,
                    task_id=task_id,
                    ledger_task_id=ledger_task_id,
                )
            if envelope.state == "succeeded":
                findings_payload = json.dumps(envelope.result)
                ingested = self._ingest_stdout(
                    findings_payload,
                    result.stderr,
                    elapsed=time.monotonic() - elapsed_start,
                    model_name="(async)",
                    models_attempted=[],
                    enforce_empty_findings_grace=review_started_at is not None,
                )
                self._stamp_process_metadata(ingested, result, mode=poll_mode)
                ledger_error = self._complete_completion_ledger(
                    ledger_task_id,
                    success=ingested.success,
                    envelope=envelope,
                    error_message=None if ingested.success else ingested.error,
                )
                if ledger_error:
                    message = (
                        "Completion ledger update failed before result "
                        f"consumption: {ledger_error}"
                    )
                    if not ingested.success and ingested.error:
                        message = f"{ingested.error}; {message}"
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        elapsed_seconds=time.monotonic() - elapsed_start,
                        error=message,
                        error_class=ErrorClass.UNKNOWN,
                        task_id=task_id,
                        ledger_task_id=ledger_task_id,
                    )
                ingested.task_id = task_id
                ingested.ledger_task_id = ledger_task_id
                return ingested
            time.sleep(poll_config.interval_seconds)

        # Timeout
        if enforcement_block is not None:
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                elapsed_seconds=time.monotonic() - elapsed_start,
                error=f"remote_state_unknown: {enforcement_block}",
                error_class=ErrorClass.TRANSIENT,
                task_id=task_id,
                ledger_task_id=ledger_task_id,
            )
        message = (
            f"Polling timed out after {poll_config.timeout_seconds}s "
            f"({attempts} attempts)"
        )
        ledger_error = self._complete_completion_ledger(
            ledger_task_id,
            success=False,
            error_message=message,
        )
        if ledger_error:
            message += f"; completion ledger update failed: {ledger_error}"
        return ReviewResult(
            vendor=self.vendor,
            success=False,
            elapsed_seconds=time.monotonic() - elapsed_start,
            error=message,
            error_class=ErrorClass.TRANSIENT,
            task_id=task_id,
            ledger_task_id=ledger_task_id,
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
        capacity_callback: Callable[[ReviewResult], Any] | None = None,
    ) -> ReviewResult:
        """Dispatch a review via vendor SDK with model fallback."""
        if mode != "review":
            return ReviewResult(
                vendor=self.vendor,
                success=False,
                error=f"SDK dispatch mode {mode!r} is unsupported",
            )
        capacity_callback = capacity_callback or getattr(
            self, "_capacity_callback", None
        )
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

        for model_index, model in enumerate(models_to_try):
            has_fallback = model_index < len(models_to_try) - 1
            models_attempted.append(model)
            try:
                findings = self._call_sdk(
                    prompt=prompt,
                    model=model,
                    api_key=api_key,
                    timeout=timeout_seconds,
                )
                raw_stdout = json.dumps(findings) if findings is not None else None
                parse_error = None if findings else "Invalid JSON in SDK response"
                findings, schema_error = _validate_findings_or_error(findings)
                if (
                    findings is not None
                    and _is_placeholder_only_response(findings, raw_stdout or "")
                ):
                    return ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        model_used=model,
                        models_attempted=models_attempted,
                        elapsed_seconds=time.monotonic() - dispatch_start,
                        error="non_substantive_placeholder",
                        raw_stdout=raw_stdout,
                    )
                return ReviewResult(
                    vendor=self.vendor,
                    success=findings is not None,
                    findings=findings,
                    model_used=model,
                    models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - dispatch_start,
                    error=schema_error or parse_error,
                    raw_stdout=raw_stdout,
                )
            except _SdkCapacityError:
                if has_fallback and capacity_callback is not None:
                    _notify_capacity(capacity_callback, ReviewResult(
                        vendor=self.vendor,
                        success=False,
                        agent_id=self.agent_id,
                        error="capacity_exhausted",
                        error_class=ErrorClass.CAPACITY,
                        capacity_scope="model",
                        capacity_model=model,
                    ))
                logger.info(
                    "%s SDK model %s capacity exhausted%s",
                    self.vendor,
                    model,
                    ", trying fallback" if has_fallback else "",
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
    ) -> dict[str, Any] | None:
        """Call the vendor SDK and parse JSON findings from response."""
        pkg = self.sdk_config.package
        if pkg == "anthropic":
            return self._call_anthropic(prompt, model, api_key, timeout)
        elif pkg == "openai":
            return self._call_openai(prompt, model, api_key, timeout)
        elif pkg == "google-generativeai":
            return self._call_google(prompt, model, api_key, timeout)
        else:
            raise ValueError(f"Unknown SDK package: {pkg}")

    def _call_anthropic(
        self, prompt: str, model: str, api_key: str, timeout: int,
    ) -> dict[str, Any] | None:
        """Dispatch via Anthropic SDK."""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=self.sdk_config.max_tokens,
                system=_SDK_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
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
    ) -> dict[str, Any] | None:
        """Dispatch via OpenAI SDK."""
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=timeout)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=self.sdk_config.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SDK_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
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
    ) -> dict[str, Any] | None:
        """Dispatch via Google Generative AI SDK."""
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        try:
            response = gen_model.generate_content(
                f"{_SDK_SYSTEM_PROMPT}\n\n{prompt}",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=self.sdk_config.max_tokens,
                ),
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
# Detached snapshot fallback for concurrent git-index errors (D2)
# ---------------------------------------------------------------------------

# Substring markers — same style as classify_error, not a result-path regex.
_GIT_INDEX_ERROR_MARKERS = (
    "index.lock",
    "unable to access index",
    "another git process",
)


def _is_concurrent_git_error(result: ReviewResult) -> bool:
    """True when a vendor CLI failed because of concurrent git index access."""
    blob = "\n".join(
        part for part in (result.error, result.raw_stderr, result.raw_stdout) if part
    ).lower()
    return any(marker in blob for marker in _GIT_INDEX_ERROR_MARKERS)


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or "unknown"


def _round_id_from_packet(packet_path: Path | None) -> str:
    if packet_path is None:
        return "default"
    name = Path(packet_path).parent.name
    return _safe_path_component(name) if name else "default"


def _main_repo_from_cwd(cwd: Path) -> Path:
    """Resolve the main repository root even when *cwd* is a linked worktree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Path(cwd)
    if proc.returncode != 0 or not proc.stdout.strip():
        return Path(cwd)
    git_common = proc.stdout.strip()
    if git_common == ".git":
        try:
            top = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return Path(cwd)
        if top.returncode == 0 and top.stdout.strip():
            return Path(top.stdout.strip())
        return Path(cwd)
    common_path = Path(git_common)
    if not common_path.is_absolute():
        common_path = (Path(cwd) / common_path).resolve()
    if common_path.name == ".git":
        return common_path.parent
    return common_path


def review_snapshot_path(cwd: Path, round_id: str, vendor: str) -> Path:
    """Return one registered read-only review snapshot path."""
    root = _main_repo_from_cwd(cwd) / ".git-worktrees" / ".review-snapshots"
    return root / (
        f"{_safe_path_component(round_id)}--{_safe_path_component(vendor)}"
    )


def workspace_content_digest(cwd: Path) -> str:
    """Digest the exact index plus tracked/worktree/nonignored-untracked content."""

    index = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    ).stdout
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    ).stdout
    if isinstance(index, str):
        index = index.encode()
    if isinstance(listed, str):
        listed = listed.encode()
    digest = hashlib.sha256()
    digest.update(b"index\0")
    digest.update(index)
    for raw in sorted(set(listed.split(b"\0"))):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape")
        if relative == ".git-worktrees" or relative.startswith(".git-worktrees/"):
            continue
        path = cwd / relative
        digest.update(b"path\0")
        digest.update(raw)
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(path.read_bytes())
        else:
            digest.update(b"missing\0")
    return digest.hexdigest()


def create_review_snapshot(cwd: Path, round_id: str, vendor: str) -> Path:
    """Materialize an exact detached review snapshot and prove content parity."""
    dest = review_snapshot_path(cwd, round_id, vendor)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        destroy_review_snapshot(dest, cwd)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    ).stdout
    if isinstance(untracked, str):
        untracked = untracked.encode()
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(dest), "HEAD"],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        staged = subprocess.run(
            ["git", "diff", "--binary", "--cached", "HEAD"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
        ).stdout
        if staged:
            subprocess.run(
                ["git", "apply", "--index", "--binary", "-"],
                cwd=str(dest),
                input=staged,
                check=True,
                capture_output=True,
            )
        unstaged = subprocess.run(
            ["git", "diff", "--binary"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
        ).stdout
        if unstaged:
            subprocess.run(
                ["git", "apply", "--binary", "-"],
                cwd=str(dest),
                input=unstaged,
                check=True,
                capture_output=True,
            )
        for raw in untracked.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8", errors="surrogateescape")
            source = cwd / relative
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                target.symlink_to(os.readlink(source))
            else:
                shutil.copy2(source, target)
        if workspace_content_digest(cwd) != workspace_content_digest(dest):
            raise RuntimeError("review snapshot content digest mismatch")
    except Exception:
        destroy_review_snapshot(dest, cwd)
        raise
    return dest


def destroy_review_snapshot(snapshot: Path, git_cwd: Path) -> None:
    """Remove a review snapshot worktree after collect. Best-effort."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(snapshot)],
            cwd=str(git_cwd),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Failed to remove review snapshot %s: %s", snapshot, exc)
    if Path(snapshot).exists():
        shutil.rmtree(snapshot, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(git_cwd),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _dispatch_with_snapshot_fallback(
    *,
    vendor: str,
    cwd: Path,
    round_id: str,
    run: Callable[[Path], ReviewResult],
    write_capable: bool = False,
) -> ReviewResult:
    """Run *run(cwd)*; on concurrent git-index failure, retry on a snapshot."""
    result = run(cwd)
    if result.success or write_capable or not _is_concurrent_git_error(result):
        return result
    logger.warning(
        "Concurrent git access error for %s; retrying on detached snapshot",
        vendor,
    )
    snapshot: Path | None = None
    try:
        snapshot = create_review_snapshot(cwd, round_id, vendor)
        return run(snapshot)
    except Exception as exc:  # noqa: BLE001 — keep the original vendor error
        logger.warning("Snapshot fallback failed for %s: %s", vendor, exc)
        return result
    finally:
        if snapshot is not None:
            destroy_review_snapshot(snapshot, cwd)


# ---------------------------------------------------------------------------
# Review orchestrator
# ---------------------------------------------------------------------------

class ReviewOrchestrator:
    """Multi-vendor review dispatch orchestrator.

    Supports CLI, SDK, and OpenAI-compatible adapters with ordered selection:
    Tier 1 (Local CLI) → Tier 2 (SDK/API) → Tier 2.5 (OpenAI-compatible)
    → Tier 3 (Skip).
    """

    def __init__(
        self,
        adapters: dict[str, CliVendorAdapter],
        sdk_adapters: dict[str, SdkVendorAdapter] | None = None,
        openai_adapters: dict[str, Any] | None = None,
        openai_key_envs: dict[str, str] | None = None,
        openai_role_ids: dict[str, str | None] | None = None,
    ) -> None:
        self.adapters = adapters
        self.sdk_adapters = sdk_adapters or {}
        self.openai_adapters = openai_adapters or {}
        self.openai_key_envs = openai_key_envs or {}
        self.openai_role_ids = openai_role_ids or {}

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ReviewOrchestrator":
        """Create orchestrator from a config dict (as returned by coordinator).

        The dict should have an ``agents`` key containing a list of agent
        config dicts, each with ``agent_id``, ``type``, ``cli``, and
        optionally ``sdk``.
        """
        adapters: dict[str, CliVendorAdapter] = {}
        sdk_adapters: dict[str, SdkVendorAdapter] = {}
        openai_adapters: dict[str, Any] = {}
        openai_key_envs: dict[str, str] = {}
        openai_role_ids: dict[str, str | None] = {}
        for agent in data.get("agents", []):
            cli = agent.get("cli")
            sdk = agent.get("sdk")
            endpoint_kind = agent.get("endpoint_kind")
            base_url = agent.get("base_url")
            if not cli and not sdk and not (
                endpoint_kind in {"openrouter", "local"} and base_url
            ):
                continue

            # Build CLI adapter
            if cli:
                dispatch_modes: dict[str, ModeConfig] = {}
                for mode_name, mode_data in cli.get("dispatch_modes", {}).items():
                    poll_data = mode_data.get("poll")
                    poll_cfg = PollConfig(
                        command_template=poll_data["command_template"],
                        result_protocol=poll_data.get(
                            "result_protocol", "vendor-envelope-v1"
                        ),
                        interval_seconds=poll_data.get("interval_seconds", 30),
                        timeout_seconds=poll_data.get("timeout_seconds", 600),
                    ) if poll_data else None
                    dispatch_modes[mode_name] = ModeConfig(
                        args=mode_data["args"],
                        async_dispatch=mode_data.get("async", False),
                        poll=poll_cfg,
                        isolation=mode_data.get("isolation"),
                        enforcement_scope=mode_data.get(
                            "enforcement_scope", "execution"
                        ),
                        write_capable=mode_data.get("write_capable", False),
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
                        prompt_via_flag=cli.get("prompt_via_flag"),
                        api_key_env=cli.get("api_key_env") or "",
                        state_env_keys=list(cli.get("state_env_keys") or []),
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
                        api_key_env=sdk.get("api_key_env", ""),
                        max_tokens=sdk.get("max_tokens", 16384),
                    ),
                    openbao_role_id=agent.get("openbao_role_id"),
                )

            if endpoint_kind in {"openrouter", "local"} and base_url:
                from openai_compat_adapter import OpenAICompatAdapter

                model, _thinking = _resolve_review_model_spec(agent["type"])
                derived_fallbacks = _derived_tier_fallbacks(agent["type"])
                configured_model = (
                    (sdk or {}).get("model")
                    or (cli or {}).get("model")
                    or model
                    or (derived_fallbacks[0] if derived_fallbacks else None)
                )
                if configured_model:
                    agent_id = agent["agent_id"]
                    openai_adapters[agent_id] = OpenAICompatAdapter(
                        agent_id=agent_id,
                        vendor=agent["type"],
                        model=configured_model,
                        base_url=base_url,
                        endpoint_kind=endpoint_kind,
                        model_fallbacks=(sdk or {}).get("model_fallbacks")
                        or (cli or {}).get("model_fallbacks", derived_fallbacks[1:]),
                    )
                    openai_key_envs[agent_id] = (
                        agent.get("api_key_env")
                        or (sdk or {}).get("api_key_env")
                        or (cli or {}).get("api_key_env")
                        or (
                            "OPENROUTER_API_KEY"
                            if endpoint_kind == "openrouter"
                            else ""
                        )
                    )
                    openai_role_ids[agent_id] = agent.get("openbao_role_id")

        return cls(
            adapters, sdk_adapters, openai_adapters, openai_key_envs, openai_role_ids
        )

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
            endpoint_kind = agent.get("endpoint_kind")
            base_url = agent.get("base_url")
            if not cli and not sdk and not (
                endpoint_kind in {"openrouter", "local"} and base_url
            ):
                continue
            agents_out.append({
                "agent_id": agent_id,
                "type": agent.get("type"),
                "transport": agent.get("transport", "mcp"),
                "openbao_role_id": agent.get("openbao_role_id"),
                "endpoint_kind": endpoint_kind,
                "base_url": base_url,
                "api_key_env": agent.get("api_key_env"),
                "cli": (
                    {
                        **cli,
                        "dispatch_modes": {
                            name: {
                                **mode,
                                "isolation": mode.get("isolation")
                                or agent.get("isolation", "none"),
                            }
                            for name, mode in cli.get("dispatch_modes", {}).items()
                        },
                    }
                    if cli
                    else None
                ),
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
        """Discover available reviewers with ordered transport selection.

        For each vendor, selects the best available dispatch method:
        Tier 1 (Local CLI) → Tier 2 (SDK/API) → Tier 2.5
        (OpenAI-compatible) → Tier 3 (Skip).
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

        openai_by_vendor: dict[str, tuple[str, Any]] = {}
        for agent_id, adapter in self.openai_adapters.items():
            if exclude_vendor and adapter.vendor == exclude_vendor:
                continue
            if adapter.vendor not in openai_by_vendor:
                openai_by_vendor[adapter.vendor] = (agent_id, adapter)

        all_vendors = (
            set(cli_by_vendor.keys())
            | set(sdk_by_vendor.keys())
            | set(openai_by_vendor.keys())
        )
        reviewers: list[ReviewerInfo] = []

        for vendor in sorted(all_vendors):
            # Tier 1: Local CLI. can_dispatch() checks mode + PATH + declared
            # credential env — a pi binary without OPENROUTER_API_KEY must not
            # be reported available (issue #383).
            if vendor in cli_by_vendor:
                agent_id, cli_adapter = cli_by_vendor[vendor]
                if cli_adapter.can_dispatch(dispatch_mode):
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

            # Tier 2.5: OpenAI-compatible HTTP endpoint. This follows SDK so
            # existing local/provider-native paths remain the preferred route.
            if vendor in openai_by_vendor:
                agent_id, openai_adapter = openai_by_vendor[vendor]
                if openai_adapter.can_dispatch(dispatch_mode):
                    logger.info(
                        "Tier 2.5 (OpenAI-compatible) selected for %s: %s",
                        vendor,
                        agent_id,
                    )
                    reviewers.append(ReviewerInfo(
                        vendor=vendor,
                        agent_id=agent_id,
                        available=True,
                        dispatch_tier="openai",
                    ))
                    continue

            # Tier 3: Skip
            logger.info(
                "Tier 3 (skip) for %s: no CLI, SDK, or OpenAI endpoint available",
                vendor,
            )

        return reviewers

    def dispatch_and_wait(
        self,
        review_type: str,
        dispatch_mode: str,
        prompt: str,
        cwd: Path,
        timeout_seconds: int | None = None,
        exclude_vendor: str | None = None,
        packet_path: Path | str | None = None,
        result_callback: Callable[[ReviewResult, int], None] | None = None,
    ) -> list[ReviewResult]:
        """Dispatch reviews to available vendors concurrently and collect results.

        Uses three-tier selection: CLI → SDK → skip. A thread pool sized to
        the available vendors overlaps subprocesses. Async CLI vendors are
        all submitted first, then polled. Review cwd is the shared worktree
        (read-only). ``packet_path`` is accepted for callers that pack the
        prompt; the packet body is already in ``prompt``.
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
            report_degraded(
                f"{review_type} review NOT CHECKED — no vendor is dispatchable "
                f"(no CLI on PATH and no SDK key); zero reviews were run.",
            )
            return []

        if len({r.vendor for r in available}) < MIN_REVIEW_VENDORS:
            report_degraded(
                f"Cross-vendor {review_type} review NOT CHECKED — only "
                f"{len({r.vendor for r in available})} of {MIN_REVIEW_VENDORS} "
                f"required vendors dispatchable "
                f"({', '.join(sorted({r.vendor for r in available}))}); findings "
                f"are a single vendor's opinion with no consensus cross-check.",
            )

        api_key_resolver = ApiKeyResolver()
        cwd = Path(cwd)
        packet = Path(packet_path) if packet_path is not None else None
        if packet is not None:
            logger.info("Review packet path: %s", packet)
        round_id = _round_id_from_packet(packet)

        from review_findings_schema import timeout_for_vendor

        def _safe_vendor_call(vendor: str, fn: Callable[[], ReviewResult]) -> ReviewResult:
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 — surface as a vendor failure
                logger.exception("Vendor %s dispatch raised", vendor)
                return ReviewResult(
                    vendor=vendor,
                    success=False,
                    error=str(exc),
                    error_class=ErrorClass.UNKNOWN,
                )

        async_jobs: list[dict[str, Any]] = []
        sync_jobs: list[tuple[int, str, int, Callable[[], ReviewResult]]] = []
        job_agent_ids: dict[int, str] = {}
        next_index = 0

        for reviewer in available:
            vendor_timeout = timeout_for_vendor(reviewer.vendor, timeout_seconds)
            if reviewer.dispatch_tier == "cli":
                adapter = self.adapters[reviewer.agent_id]
                adapter._capacity_callback = report_vendor_limit_result
                if not adapter.can_dispatch(dispatch_mode):
                    logger.info(
                        "Skipping %s: dispatch mode '%s' not configured",
                        reviewer.agent_id, dispatch_mode,
                    )
                    continue

                mode_config = adapter.cli_config.dispatch_modes[dispatch_mode]
                idx = next_index
                next_index += 1
                job_agent_ids[idx] = reviewer.agent_id

                if mode_config.async_dispatch:
                    logger.info(
                        "Async CLI dispatching %s review to %s",
                        review_type, reviewer.agent_id,
                    )
                    async_jobs.append({
                        "index": idx,
                        "vendor": reviewer.vendor,
                        "adapter": adapter,
                        "mode_config": mode_config,
                        "timeout": vendor_timeout,
                    })
                else:
                    logger.info(
                        "Sync CLI dispatching %s review to %s",
                        review_type, reviewer.agent_id,
                    )
                    sync_jobs.append((
                        idx,
                        reviewer.vendor,
                        vendor_timeout,
                        partial(
                            _dispatch_with_snapshot_fallback,
                            vendor=reviewer.vendor,
                            cwd=cwd,
                            round_id=round_id,
                            write_capable=mode_config.write_capable,
                            run=lambda run_cwd, a=adapter, t=vendor_timeout: a.dispatch(
                                dispatch_mode,
                                prompt,
                                run_cwd,
                                t,
                            ),
                        ),
                    ))

            elif reviewer.dispatch_tier == "sdk":
                sdk_adapter = self.sdk_adapters[reviewer.agent_id]
                sdk_adapter._capacity_callback = report_vendor_limit_result
                api_key = api_key_resolver.resolve(
                    sdk_adapter.openbao_role_id,
                    sdk_adapter.sdk_config.api_key_env,
                )
                logger.info(
                    "SDK dispatching %s review to %s (key: %s)",
                    review_type, reviewer.agent_id,
                    "resolved" if api_key else "missing",
                )
                idx = next_index
                next_index += 1
                job_agent_ids[idx] = reviewer.agent_id
                if not api_key:
                    sync_jobs.append((
                        idx,
                        reviewer.vendor,
                        vendor_timeout,
                        lambda v=reviewer.vendor: ReviewResult(
                            vendor=v,
                            success=False,
                            error="No API key available for SDK dispatch",
                        ),
                    ))
                    continue

                sync_jobs.append((
                    idx,
                    reviewer.vendor,
                    vendor_timeout,
                    partial(
                        sdk_adapter.dispatch,
                        dispatch_mode,
                        prompt,
                        cwd,
                        vendor_timeout,
                        api_key,
                    ),
                ))

            elif reviewer.dispatch_tier == "openai":
                openai_adapter = self.openai_adapters[reviewer.agent_id]
                api_key = api_key_resolver.resolve(
                    self.openai_role_ids.get(reviewer.agent_id),
                    self.openai_key_envs.get(reviewer.agent_id, ""),
                )
                logger.info(
                    "OpenAI-compatible dispatching %s review to %s (key: %s)",
                    review_type,
                    reviewer.agent_id,
                    "resolved" if api_key else "not-required-or-missing",
                )
                idx = next_index
                next_index += 1
                job_agent_ids[idx] = reviewer.agent_id
                sync_jobs.append((
                    idx,
                    reviewer.vendor,
                    vendor_timeout,
                    partial(
                        openai_adapter.dispatch,
                        dispatch_mode,
                        prompt,
                        cwd,
                        vendor_timeout,
                        api_key,
                    ),
                ))

        job_count = len(async_jobs) + len(sync_jobs)
        if job_count == 0:
            return []

        collected: dict[int, ReviewResult] = {}

        def _collect(index: int, result: ReviewResult) -> None:
            if result.agent_id is None:
                result.agent_id = job_agent_ids[index]
            if result.error_class == ErrorClass.CAPACITY:
                report_vendor_limit_result(result)
            if result_callback is not None:
                result_callback(result, job_count)
            collected[index] = result

        for job in async_jobs:
            job["review_started_at"] = time.monotonic()

        with ThreadPoolExecutor(max_workers=job_count) as pool:
            submit_futs = {
                pool.submit(
                    _safe_vendor_call,
                    job["vendor"],
                    partial(
                        _dispatch_with_snapshot_fallback,
                        vendor=job["vendor"],
                        cwd=cwd,
                        round_id=round_id,
                        write_capable=job["mode_config"].write_capable,
                        run=lambda run_cwd, a=job["adapter"]: a.dispatch_async(
                            dispatch_mode,
                            prompt,
                            run_cwd,
                        ),
                    ),
                ): job
                for job in async_jobs
            }
            sync_futs = {
                pool.submit(_safe_vendor_call, vendor, thunk): idx
                for idx, vendor, _timeout, thunk in sync_jobs
            }
            poll_futs: dict[Any, dict[str, Any]] = {}

            def _start_poll(
                job: dict[str, Any], submit_result: ReviewResult,
            ) -> None:
                mode_config = job["mode_config"]
                adapter = job["adapter"]
                task_id = submit_result.task_id
                ledger_task_id = submit_result.ledger_task_id
                poll_config = mode_config.poll
                review_started_at = job["review_started_at"]
                assert task_id is not None
                assert ledger_task_id is not None
                assert poll_config is not None

                def _poll_run(
                    run_cwd: Path,
                    a: CliVendorAdapter = adapter,
                    tid: str = task_id,
                    ledger_id: str = ledger_task_id,
                    pc: PollConfig = poll_config,
                    started: float = review_started_at,
                ) -> ReviewResult:
                    return a.poll_for_result(
                        tid,
                        pc,
                        cwd=run_cwd,
                        review_started_at=started,
                        ledger_task_id=ledger_id,
                        isolation=mode_config.isolation or "none",
                    )

                poll_futs[pool.submit(
                    _safe_vendor_call,
                    job["vendor"],
                    partial(
                        _dispatch_with_snapshot_fallback,
                        vendor=job["vendor"],
                        cwd=cwd,
                        round_id=round_id,
                        write_capable=mode_config.write_capable,
                        run=_poll_run,
                    ),
                )] = job

            pending_submits = set(submit_futs)
            pending_sync = set(sync_futs)
            while pending_submits:
                done, _pending = wait(
                    pending_submits | pending_sync,
                    return_when=FIRST_COMPLETED,
                )
                for fut in done:
                    if fut in pending_sync:
                        pending_sync.remove(fut)
                        _collect(sync_futs[fut], fut.result())
                        continue
                    pending_submits.remove(fut)
                    job = submit_futs[fut]
                    submit_result = fut.result()
                    mode_config = job["mode_config"]
                    if (
                        submit_result.success
                        and submit_result.task_id
                        and mode_config.poll
                    ):
                        _start_poll(job, submit_result)
                    else:
                        _collect(job["index"], submit_result)

            for fut in as_completed(pending_sync | set(poll_futs)):
                result = fut.result()
                if fut in sync_futs:
                    _collect(sync_futs[fut], result)
                else:
                    _collect(poll_futs[fut]["index"], result)

        return [collected[i] for i in sorted(collected)]

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

        dispatches = [
            {
                "vendor": r.vendor,
                "success": r.success,
                "model_used": r.model_used,
                "models_attempted": r.models_attempted,
                "elapsed_seconds": r.elapsed_seconds,
                "error": r.error,
                "error_class": r.error_class.value if r.error_class else None,
                "async_dispatch": r.async_dispatch,
                "task_id": r.task_id,
                "ledger_task_id": r.ledger_task_id,
                "routing_digest": r.routing_digest,
                "requested_isolation": r.requested_isolation,
                "applied_isolation": r.applied_isolation,
                "endpoint_digest": r.endpoint_digest,
                "policy_revision": r.policy_revision,
                "runtime_version": r.runtime_version,
                "settings_digest": r.settings_digest,
                "snapshot_content_digest": r.snapshot_content_digest,
                "collection_state": r.collection_state,
                "cleanup_status": r.cleanup_status,
                "cleanup_residual_paths": r.cleanup_residual_paths,
                "sandbox_host_commit_required": r.sandbox_host_commit_required,
            }
            for r in results
        ]
        _cf_write_manifest(
            output_path.parent,
            review_type=review_type,
            target=target,
            vendors=list(vendors) if vendors is not None else [],
            change_id=None,
            dispatches=dispatches,
            quorum_requested=len(results),
            quorum_received=sum(1 for r in results if r.success),
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
    cwd: Path | None = None,
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
        orch = _orchestrator_for_dispatch(agents_yaml, cwd or Path("."))
        reviewers = orch.discover_reviewers(
            exclude_vendor=exclude_vendor,
            dispatch_mode=dispatch_mode,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on any resolution error
        print(
            f"check-vendors: unable to resolve vendor roster ({exc})",
            file=sys.stderr,
        )
        report_degraded(
            f"Vendor availability NOT CHECKED — the roster could not be "
            f"resolved ({exc}); multi-vendor review is unavailable.",
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
        report_degraded(
            f"Cross-vendor review NOT CHECKED — only {len(names)} of "
            f"{min_vendors} required vendors dispatchable "
            f"({', '.join(names) or 'none'}); the review either does not run "
            f"or produces a single vendor's unreviewed opinion.",
        )
        return CHECK_VENDORS_BELOW_QUORUM
    return 0


def _orchestrator_for_dispatch(
    agents_yaml: str | None,
    cwd: Path,
) -> ReviewOrchestrator:
    """Resolve dispatch config from the reviewed checkout before global state."""
    if agents_yaml:
        return ReviewOrchestrator.from_agents_yaml(Path(agents_yaml))

    local = ReviewOrchestrator._find_local_agents_yaml(cwd)
    if local is not None:
        return ReviewOrchestrator.from_agents_yaml(local)

    orchestrator = ReviewOrchestrator.from_coordinator()
    if (
        not orchestrator.adapters
        and not orchestrator.sdk_adapters
        and not orchestrator.openai_adapters
    ):
        logger.info("Coordinator unavailable, trying agents.yaml on disk")
        orchestrator = ReviewOrchestrator.from_agents_yaml()
    return orchestrator


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
        "--timeout", type=int, default=None,
        help="Override per-vendor timeout budget for every vendor (seconds)",
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
            cwd=Path(args.cwd),
            exclude_vendor=args.exclude_vendor,
            min_vendors=args.min_vendors,
            dispatch_mode=args.mode,
        )

    # --list-agents: show available agents and exit
    if args.list_agents:
        orch = _orchestrator_for_dispatch(args.agents_yaml, Path(args.cwd))
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

    # Review the target checkout with the vendor config from that checkout.
    orch = _orchestrator_for_dispatch(args.agents_yaml, Path(args.cwd))

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

    # Write results via the shared checkpoint_findings helper. Per-vendor
    # files preserve the existing wrapper-object shape and path layout; the
    # manifest gains the superset fields needed by the in-process converge()
    # caller while preserving everything legacy callers parse.
    from checkpoint_findings import (
        write_raw_output as _cf_write_raw_output,
        write_vendor_findings as _cf_write_vendor_findings,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    vendors_index: list[dict[str, Any]] = []
    for result in results:
        _cf_write_raw_output(
            output_dir,
            vendor=result.vendor,
            review_type=args.review_type,
            stdout=result.raw_stdout,
            stderr=result.raw_stderr,
            coercions=list(result.coercions or []),
        )
        if result.success and result.findings:
            findings_array = result.findings.get("findings", [])
            _cf_write_vendor_findings(
                output_dir,
                vendor=result.vendor,
                review_type=args.review_type,
                target="cli-dispatch",
                findings=findings_array,
                coverage=result.findings.get("coverage"),
            )
            vendors_index.append({
                "name": result.vendor,
                "findings_path": f"findings-{result.vendor}-{args.review_type}.json",
                "finding_count": len(findings_array),
                "unanchored_findings": result.unanchored_findings,
                "coverage_rate": result.coverage_rate,
                "coverage_eligibility": result.coverage_eligibility,
                "coverage": result.coverage_status,
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

    succeeded = sum(1 for r in results if r.success)
    print(f"Results: {succeeded}/{len(results)} vendors succeeded")
    if 0 < succeeded < MIN_REVIEW_VENDORS:
        report_degraded(
            f"Cross-vendor {args.review_type} review NOT CHECKED — only "
            f"{succeeded} of {MIN_REVIEW_VENDORS} required vendors returned "
            f"findings; consensus could not be computed, so these findings are "
            f"a single vendor's opinion. Record this phase as {DEGRADED_STATUS} "
            f"in validation-report.md.",
        )
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
