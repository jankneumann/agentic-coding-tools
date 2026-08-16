"""Provider-neutral autopilot phase dispatch adapters."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class PhaseDispatchPayload:
    schema_version: int
    change_id: str
    phase: str
    provider: str
    archetype: str | None
    model: str | None
    prompt: str
    system_prompt: str | None
    isolation: str | None
    expected_outcomes: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhaseDispatchPayload":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            change_id=str(data["change_id"]),
            phase=str(data["phase"]),
            provider=str(data["provider"]),
            archetype=data.get("archetype"),
            model=data.get("model"),
            prompt=str(data["prompt"]),
            system_prompt=data.get("system_prompt"),
            isolation=data.get("isolation"),
            expected_outcomes=list(data.get("expected_outcomes") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseDispatchResult:
    schema_version: int = 1
    outcome: str = "failed"
    handoff_id: str = ""
    provider: str = ""
    model_used: str | None = None
    dispatch_tier: str = "fallback"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProviderRunner = Callable[[PhaseDispatchPayload], Any]

_SUPPORTED_PROVIDERS = {"claude_code", "codex", "antigravity", "grok", "pi", "local"}
_CLAUDE_ALIASES = {"opus", "sonnet", "haiku", "fable"}

# --- local provider adapter (OpenSpec add-local-model-provider-tier, D2/D5) ---
#
# `local` speaks the OpenAI chat-completions wire protocol to an operator-run
# endpoint (llama-server / vLLM / Ollama on the always-on host). No SDK: stdlib
# urllib only, matching parallel-infrastructure/scripts/openai_compat_adapter.py.
#
# Environment contract:
#   LOCAL_INFERENCE_BASE_URL       required to enable; includes the API version
#                                  prefix, e.g. "http://gx10.local:8080/v1"
#   LOCAL_INFERENCE_API_KEY        optional bearer token
#   LOCAL_INFERENCE_MAX_CONCURRENCY  optional, default 4; excess dispatches queue
#
# With LOCAL_INFERENCE_BASE_URL unset the provider is inert: dispatch returns the
# same structured `fallback` result any unconfigured adapter returns, and no
# network call is made (Rule 4 — safe default).
_LOCAL_PROVIDER = "local"
_LOCAL_DEFAULT_MAX_CONCURRENCY = 4
# Short by design: a dead endpoint must surface as adapter unavailability in
# seconds, never as a stalled phase.
_LOCAL_PROBE_TIMEOUT_SECONDS = 3.0
# Bounded per-dispatch ceiling (mirrors openai_compat_adapter's default).
_LOCAL_DISPATCH_TIMEOUT_SECONDS = 300

_local_state_lock = threading.Lock()
# (base_url, reachable) — one health probe per process per endpoint.
_local_probe_cache: tuple[str, bool] | None = None
_local_gate_semaphore: threading.Semaphore | None = None
_local_gate_limit: int | None = None


def reset_local_adapter_state() -> None:
    """Drop the cached health probe and concurrency gate (test hook)."""
    global _local_probe_cache, _local_gate_semaphore, _local_gate_limit
    with _local_state_lock:
        _local_probe_cache = None
        _local_gate_semaphore = None
        _local_gate_limit = None


def _http_get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    """Real HTTP GET transport (stdlib urllib). Stubbed out in unit tests."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-set URL)
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Real HTTP POST transport (stdlib urllib). Stubbed out in unit tests."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-set URL)
        return json.loads(resp.read().decode("utf-8"))


def _local_base_url() -> str | None:
    raw = os.environ.get("LOCAL_INFERENCE_BASE_URL", "").strip().rstrip("/")
    return raw or None


def _local_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("LOCAL_INFERENCE_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _local_max_concurrency() -> int:
    """Simultaneous local dispatches; anything unparseable or <=0 uses the default."""
    try:
        value = int(os.environ.get("LOCAL_INFERENCE_MAX_CONCURRENCY", "").strip())
    except ValueError:
        return _LOCAL_DEFAULT_MAX_CONCURRENCY
    return value if value > 0 else _LOCAL_DEFAULT_MAX_CONCURRENCY


def _local_gate() -> threading.Semaphore:
    """Concurrency cap. Excess dispatches block (queue), they are never dropped."""
    global _local_gate_semaphore, _local_gate_limit
    limit = _local_max_concurrency()
    with _local_state_lock:
        if _local_gate_semaphore is None or _local_gate_limit != limit:
            _local_gate_semaphore = threading.Semaphore(limit)
            _local_gate_limit = limit
        return _local_gate_semaphore


def local_endpoint_available(*, force: bool = False) -> bool:
    """Whether the configured local endpoint answered its health probe.

    Probes ``GET {LOCAL_INFERENCE_BASE_URL}/models`` (the OpenAI-compatible model
    listing) once per process per base URL with a short timeout, and caches the
    verdict. Returns False when no endpoint is configured — callers (dispatch,
    and the roadmap policy engine's switch-target selection) treat that as
    "adapter unavailable", never as an error.
    """
    global _local_probe_cache
    base_url = _local_base_url()
    if base_url is None:
        return False

    with _local_state_lock:
        cached = _local_probe_cache
    if not force and cached is not None and cached[0] == base_url:
        return cached[1]

    try:
        _http_get_json(f"{base_url}/models", _local_headers(), _LOCAL_PROBE_TIMEOUT_SECONDS)
        reachable = True
    except Exception:  # noqa: BLE001 — any probe failure is adapter unavailability
        reachable = False

    with _local_state_lock:
        _local_probe_cache = (base_url, reachable)
    return reachable


def normalize_dispatch_result(
    raw: Any,
    payload: PhaseDispatchPayload,
    dispatch_tier: str,
) -> PhaseDispatchResult:
    """Normalize tuple/dict adapter output into the contract result shape."""
    warnings: list[str] = []
    outcome: str | None = None
    handoff_id: str | None = None
    model_used = payload.model

    if isinstance(raw, tuple) and len(raw) == 2:
        outcome, handoff_id = raw
    elif isinstance(raw, dict):
        outcome = raw.get("outcome")
        handoff_id = raw.get("handoff_id")
        model_used = raw.get("model_used", model_used)
        raw_warnings = raw.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(item) for item in raw_warnings]

    if not isinstance(outcome, str) or not outcome:
        outcome = "failed"
        warnings.append("adapter returned missing outcome")
    if not isinstance(handoff_id, str) or not handoff_id:
        digest = hashlib.sha256(
            json.dumps(payload.to_dict(), sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        handoff_id = f"{dispatch_tier}:{payload.provider}:{payload.phase}:{digest}"
        warnings.append("adapter returned missing handoff_id")

    return PhaseDispatchResult(
        outcome=outcome,
        handoff_id=handoff_id,
        provider=payload.provider,
        model_used=model_used,
        dispatch_tier=dispatch_tier,
        warnings=warnings,
    )


def _fallback_result(
    payload: PhaseDispatchPayload,
    warning: str,
) -> PhaseDispatchResult:
    """The structured degradation every unconfigured adapter returns."""
    return PhaseDispatchResult(
        outcome="failed",
        handoff_id=f"fallback:{payload.provider}:{payload.phase}",
        provider=payload.provider,
        model_used=payload.model,
        dispatch_tier="fallback",
        warnings=[warning],
    )


def _local_chat_request(payload: PhaseDispatchPayload) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if payload.system_prompt:
        messages.append({"role": "system", "content": payload.system_prompt})
    messages.append({"role": "user", "content": payload.prompt})
    return {
        "model": payload.model or "default",
        "messages": messages,
        "temperature": 0,
    }


def _local_message_content(response: dict[str, Any]) -> str | None:
    """Pull assistant text out of an OpenAI-compatible chat response."""
    choices = response.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) and content else None


def _local_runner(payload: PhaseDispatchPayload) -> dict[str, Any]:
    """Built-in adapter runner: one capped OpenAI chat-completions dispatch.

    Returns a dict in the shape :func:`normalize_dispatch_result` consumes.
    ``model_used`` is intentionally left out so the roster model identifier from
    the payload is what gets recorded.
    """
    base_url = _local_base_url()
    with _local_gate():
        response = _http_post_json(
            f"{base_url}/chat/completions",
            _local_headers(),
            _local_chat_request(payload),
            _LOCAL_DISPATCH_TIMEOUT_SECONDS,
        )

    content = _local_message_content(response)
    if content is None:
        return {
            "outcome": "failed",
            "warnings": ["local adapter received an empty response body"],
        }

    # Phases that answer with the structured handoff JSON get it honored;
    # anything else counts as a completed dispatch and normalize_dispatch_result
    # synthesizes the handoff id.
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        result: dict[str, Any] = {}
        if isinstance(parsed.get("outcome"), str) and parsed["outcome"]:
            result["outcome"] = parsed["outcome"]
        if isinstance(parsed.get("handoff_id"), str) and parsed["handoff_id"]:
            result["handoff_id"] = parsed["handoff_id"]
        if result:
            result.setdefault("outcome", "complete")
            return result
    return {"outcome": "complete"}


def _dispatch_local(payload: PhaseDispatchPayload) -> PhaseDispatchResult:
    """Dispatch through the built-in local adapter, degrading instead of raising."""
    if _local_base_url() is None:
        return _fallback_result(
            payload,
            "adapter unavailable for provider 'local': LOCAL_INFERENCE_BASE_URL is not set",
        )
    if not local_endpoint_available():
        return _fallback_result(
            payload,
            "adapter unavailable for provider 'local': health probe failed for "
            "the configured endpoint",
        )
    try:
        raw = _local_runner(payload)
    except Exception as exc:  # noqa: BLE001 — a dead endpoint must not fail the phase
        return _fallback_result(
            payload,
            f"adapter unavailable for provider 'local': dispatch failed ({exc})",
        )
    return normalize_dispatch_result(raw, payload, "harness")


def _dry_run_result(payload: PhaseDispatchPayload) -> PhaseDispatchResult:
    if payload.provider != "claude_code" and payload.model in _CLAUDE_ALIASES:
        return PhaseDispatchResult(
            outcome="failed",
            handoff_id=f"dry-run:{payload.provider}:{payload.phase}:invalid-model",
            provider=payload.provider,
            model_used=payload.model,
            dispatch_tier="dry_run",
            warnings=[
                f"Claude alias {payload.model!r} is not valid for provider {payload.provider!r}",
            ],
        )
    outcome = "complete"
    if payload.expected_outcomes and outcome not in payload.expected_outcomes:
        outcome = payload.expected_outcomes[0]
    digest = hashlib.sha256(
        f"{payload.provider}:{payload.phase}:{payload.model}".encode("utf-8")
    ).hexdigest()[:12]
    return PhaseDispatchResult(
        outcome=outcome,
        handoff_id=f"dry-run:{payload.provider}:{payload.phase}:{digest}",
        provider=payload.provider,
        model_used=payload.model,
        dispatch_tier="dry_run",
        warnings=[],
    )


def dispatch_phase(
    payload: PhaseDispatchPayload,
    *,
    runner: ProviderRunner | None = None,
    dry_run: bool = False,
) -> PhaseDispatchResult:
    """Dispatch a phase payload through a provider adapter.

    Production harnesses can pass *runner* to invoke their provider-specific
    execution surface. Without a runner, unsupported/nonconfigured adapters
    return a structured fallback result so the SKILL.md layer can continue
    through inline execution.
    """
    if dry_run:
        return _dry_run_result(payload)
    if payload.provider not in _SUPPORTED_PROVIDERS:
        return _fallback_result(
            payload, f"adapter unavailable for provider {payload.provider!r}"
        )
    if runner is None:
        if payload.provider == _LOCAL_PROVIDER:
            return _dispatch_local(payload)
        return _fallback_result(
            payload,
            f"adapter unavailable for provider {payload.provider!r} in this runtime",
        )
    return normalize_dispatch_result(runner(payload), payload, "harness")
