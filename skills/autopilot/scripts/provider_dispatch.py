"""Provider-neutral autopilot phase dispatch adapters.

Scope note for the built-in `local` adapter: its concurrency cap
(``LOCAL_INFERENCE_MAX_CONCURRENCY``) is enforced **per process**, not host-wide.
The gate is a :class:`threading.Semaphore` owned by this module, so N concurrent
autopilot processes pointed at the same endpoint can each admit up to the cap —
the endpoint may see N x cap simultaneous requests. Host-level admission control
belongs to the serving stack in front of the GPU, not here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


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
#   LOCAL_INFERENCE_BASE_URL       required to enable; http:// or https:// only;
#                                  includes the API version prefix, e.g.
#                                  "http://gx10.local:8080/v1"
#   LOCAL_INFERENCE_API_KEY        optional bearer token
#   LOCAL_INFERENCE_MAX_CONCURRENCY  optional, default 4, clamped to 64; excess
#                                  dispatches queue (per process — see the module
#                                  docstring)
#
# With LOCAL_INFERENCE_BASE_URL unset the provider is inert: dispatch returns the
# same structured `fallback` result any unconfigured adapter returns, and no
# network call is made (Rule 4 — safe default).
_LOCAL_PROVIDER = "local"
_LOCAL_DEFAULT_MAX_CONCURRENCY = 4
# A process cannot usefully hold more in-flight local requests than this, and a
# fat-fingered env value must not turn the gate into an unbounded thread farm.
_LOCAL_MAX_MAX_CONCURRENCY = 64
# Only these schemes are dispatchable; anything else (file:, ftp:, a bare host)
# is a misconfiguration, not an endpoint.
_LOCAL_ALLOWED_SCHEMES = ("http", "https")
# Short by design: a dead endpoint must surface as adapter unavailability in
# seconds, never as a stalled phase.
_LOCAL_PROBE_TIMEOUT_SECONDS = 3.0
# Bounded per-dispatch ceiling (mirrors openai_compat_adapter's default).
_LOCAL_DISPATCH_TIMEOUT_SECONDS = 300
# Upper bound on time spent queued behind the concurrency cap. Queueing is
# required by the spec (excess dispatches queue, they are never dropped), but it
# must still terminate: a wedged slot holder degrades the waiter to the
# structured fallback instead of parking the phase forever.
_LOCAL_GATE_ACQUIRE_TIMEOUT_SECONDS = 1800
# The probe verdict is a cache, not a fact. A short TTL keeps a restarted or
# just-crashed endpoint from being pinned to a stale verdict for the whole
# process lifetime, in either direction.
_LOCAL_PROBE_TTL_SECONDS = 30.0
# Responses are JSON handoffs, not model weights: anything past this budget is a
# misbehaving endpoint and fails closed to the structured fallback.
_LOCAL_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
# Defence in depth for the resolver-side trust boundary (design D3). The
# coordinator is the single decision point, but a payload can reach this adapter
# from any client; an archetype outside this allowlist never reaches the wire.
_LOCAL_TRUSTED_ARCHETYPES = frozenset({"runner", "analyst", "documenter", "validator"})


class LocalAdapterError(RuntimeError):
    """Base for adapter-side local failures. Never escapes ``dispatch_phase``."""


class LocalDeadlineExceeded(LocalAdapterError, TimeoutError):
    """A probe or dispatch blew its wall-clock deadline."""


class LocalGateTimeout(LocalAdapterError, TimeoutError):
    """Waiting for a concurrency slot blew its bound."""


class LocalResponseTooLarge(LocalAdapterError, ValueError):
    """The endpoint sent more bytes than the response budget allows."""


_local_state_lock = threading.Lock()
# Serializes cold probes so concurrent first-callers issue one request, not N.
_local_probe_lock = threading.Lock()
# (base_url, reachable, expires_at_monotonic) — TTL'd, and invalidated whenever a
# dispatch hits a connection error.
_local_probe_cache: tuple[str, bool, float] | None = None
_local_gate_semaphore: threading.Semaphore | None = None
_local_gate_limit: int | None = None


def reset_local_adapter_state() -> None:
    """Drop the cached health probe and concurrency gate (test hook)."""
    global _local_probe_cache, _local_gate_semaphore, _local_gate_limit
    with _local_state_lock:
        _local_probe_cache = None
        _local_gate_semaphore = None
        _local_gate_limit = None


def invalidate_local_probe_cache() -> None:
    """Forget the cached probe verdict; the next caller re-probes."""
    global _local_probe_cache
    with _local_state_lock:
        _local_probe_cache = None


def _read_capped(resp: Any) -> bytes:
    """Read at most :data:`_LOCAL_MAX_RESPONSE_BYTES` from *resp*, else fail."""
    chunk = resp.read(_LOCAL_MAX_RESPONSE_BYTES + 1)
    if len(chunk) > _LOCAL_MAX_RESPONSE_BYTES:
        raise LocalResponseTooLarge(
            f"response exceeded the {_LOCAL_MAX_RESPONSE_BYTES}-byte budget"
        )
    return chunk


def _http_get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    """Real HTTP GET transport (stdlib urllib). Stubbed out in unit tests."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-set URL)
        return json.loads(_read_capped(resp).decode("utf-8"))


def _http_post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Real HTTP POST transport (stdlib urllib). Stubbed out in unit tests."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-set URL)
        return json.loads(_read_capped(resp).decode("utf-8"))


def _call_with_deadline(fn: Callable[[], Any], deadline_seconds: float) -> Any:
    """Run *fn* under a wall-clock deadline.

    ``urllib``'s ``timeout`` is per socket operation: an endpoint that trickles a
    byte every few seconds never trips it. A bounded worker gives probe and
    dispatch a real ceiling — the caller is released at the deadline (freeing its
    concurrency slot) while the abandoned request is left to the daemon thread.
    """
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised in the caller
            box["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(deadline_seconds)
    if worker.is_alive():
        raise LocalDeadlineExceeded(
            f"local endpoint did not answer within {deadline_seconds}s"
        )
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _is_connection_error(exc: BaseException) -> bool:
    """Whether *exc* casts doubt on endpoint reachability (probe invalidation)."""
    return isinstance(exc, (OSError, LocalDeadlineExceeded, LocalGateTimeout))


def _local_base_url_raw() -> str:
    return os.environ.get("LOCAL_INFERENCE_BASE_URL", "").strip().rstrip("/")


def _local_base_url() -> str | None:
    """The configured endpoint, or None when unset or not an http(s) URL."""
    raw = _local_base_url_raw()
    if not raw:
        return None
    if urllib.parse.urlsplit(raw).scheme.lower() not in _LOCAL_ALLOWED_SCHEMES:
        return None
    return raw


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
    if value <= 0:
        return _LOCAL_DEFAULT_MAX_CONCURRENCY
    if value > _LOCAL_MAX_MAX_CONCURRENCY:
        logger.warning(
            "LOCAL_INFERENCE_MAX_CONCURRENCY=%s clamped to %s",
            value,
            _LOCAL_MAX_MAX_CONCURRENCY,
        )
        return _LOCAL_MAX_MAX_CONCURRENCY
    return value


def _local_gate() -> threading.Semaphore:
    """Concurrency cap. Excess dispatches block (queue), they are never dropped.

    The cap is read from the environment exactly once (first use, or after
    :func:`reset_local_adapter_state`). Re-reading it per dispatch would let a
    mid-run env change swap the semaphore out from under in-flight holders, and
    the new gate would admit its full limit on top of them.
    """
    global _local_gate_semaphore, _local_gate_limit
    with _local_state_lock:
        if _local_gate_semaphore is None:
            _local_gate_limit = _local_max_concurrency()
            _local_gate_semaphore = threading.Semaphore(_local_gate_limit)
        return _local_gate_semaphore


def _cached_probe_verdict(base_url: str) -> bool | None:
    """The unexpired cached verdict for *base_url*, or None when it must re-probe."""
    with _local_state_lock:
        cached = _local_probe_cache
    if cached is None or cached[0] != base_url:
        return None
    if time.monotonic() >= cached[2]:
        return None
    return cached[1]


def local_endpoint_available(*, force: bool = False) -> bool:
    """Whether the configured local endpoint answered its health probe.

    Probes ``GET {LOCAL_INFERENCE_BASE_URL}/models`` (the OpenAI-compatible model
    listing) with a short timeout and caches the verdict for
    :data:`_LOCAL_PROBE_TTL_SECONDS`. The TTL matters in both directions: a
    single transient failure must not blackhole `local` for the rest of the
    process, and an endpoint that dies after one good probe must not stay
    "available" forever. A dispatch-time connection error additionally
    invalidates the cache immediately.

    Returns False when no endpoint is configured, or when the configured value is
    not an http(s) URL — callers (dispatch, and the roadmap policy engine's
    switch-target selection) treat that as "adapter unavailable", never an error.
    """
    global _local_probe_cache
    base_url = _local_base_url()
    if base_url is None:
        raw = _local_base_url_raw()
        if raw:
            logger.warning(
                "local adapter unavailable: LOCAL_INFERENCE_BASE_URL must use one "
                "of %s (got scheme %r)",
                "/".join(_LOCAL_ALLOWED_SCHEMES),
                urllib.parse.urlsplit(raw).scheme,
            )
        return False

    if not force:
        cached = _cached_probe_verdict(base_url)
        if cached is not None:
            return cached

    # Single-flight: concurrent cold callers collapse onto one probe.
    with _local_probe_lock:
        if not force:
            cached = _cached_probe_verdict(base_url)
            if cached is not None:
                return cached
        try:
            _call_with_deadline(
                lambda: _http_get_json(
                    f"{base_url}/models",
                    _local_headers(),
                    _LOCAL_PROBE_TIMEOUT_SECONDS,
                ),
                _LOCAL_PROBE_TIMEOUT_SECONDS,
            )
            reachable = True
        except Exception as exc:  # noqa: BLE001 — any probe failure is unavailability
            logger.debug("local health probe failed for %s: %s", base_url, exc)
            reachable = False

        with _local_state_lock:
            _local_probe_cache = (
                base_url,
                reachable,
                time.monotonic() + _LOCAL_PROBE_TTL_SECONDS,
            )
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
    # payload.model is guaranteed non-empty here: _dispatch_local refuses an
    # unresolved model rather than inventing a placeholder slug.
    return {
        "model": payload.model,
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
    gate = _local_gate()
    if not gate.acquire(timeout=_LOCAL_GATE_ACQUIRE_TIMEOUT_SECONDS):
        raise LocalGateTimeout(
            f"no local dispatch slot within {_LOCAL_GATE_ACQUIRE_TIMEOUT_SECONDS}s"
        )
    try:
        response = _call_with_deadline(
            lambda: _http_post_json(
                f"{base_url}/chat/completions",
                _local_headers(),
                _local_chat_request(payload),
                _LOCAL_DISPATCH_TIMEOUT_SECONDS,
            ),
            _LOCAL_DISPATCH_TIMEOUT_SECONDS,
        )
    finally:
        gate.release()

    if not isinstance(response, dict):
        return {
            "outcome": "failed",
            "warnings": ["local adapter received a non-object response body"],
        }

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


def _local_trust_boundary_warning(payload: PhaseDispatchPayload) -> str | None:
    """Refusal reason when *payload*'s archetype may not be served by `local`.

    Design D3 puts the trust boundary in the coordinator's resolver. This is the
    adapter-side backstop for payloads that never went through it: an absent or
    non-permitted archetype is refused here, before any request is built.
    """
    archetype = payload.archetype
    permitted = ", ".join(sorted(_LOCAL_TRUSTED_ARCHETYPES))
    if not isinstance(archetype, str) or not archetype:
        return (
            "payload carries no archetype, so the 'local' provider trust boundary "
            f"cannot be satisfied (permitted: {permitted}); no dispatch attempted"
        )
    if archetype not in _LOCAL_TRUSTED_ARCHETYPES:
        return (
            f"archetype {archetype!r} is outside the 'local' provider trust "
            f"boundary (permitted: {permitted}); no dispatch attempted"
        )
    return None


def _dispatch_local(payload: PhaseDispatchPayload) -> PhaseDispatchResult:
    """Dispatch through the built-in local adapter, degrading instead of raising."""
    if _local_base_url() is None:
        if _local_base_url_raw():
            return _fallback_result(
                payload,
                "adapter unavailable for provider 'local': LOCAL_INFERENCE_BASE_URL "
                "must be an http:// or https:// URL",
            )
        return _fallback_result(
            payload,
            "adapter unavailable for provider 'local': LOCAL_INFERENCE_BASE_URL is not set",
        )
    boundary = _local_trust_boundary_warning(payload)
    if boundary is not None:
        return _fallback_result(
            payload, f"adapter unavailable for provider 'local': {boundary}"
        )
    if not payload.model:
        return _fallback_result(
            payload,
            "adapter unavailable for provider 'local': no model resolved for this "
            "phase; no dispatch attempted",
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
        logger.debug("local dispatch failed", exc_info=True)
        if _is_connection_error(exc):
            # The cached "reachable" verdict is now suspect; make the next
            # caller re-probe instead of retrying into a black hole.
            invalidate_local_probe_cache()
        return _fallback_result(
            payload,
            "adapter unavailable for provider 'local': dispatch failed "
            f"({type(exc).__name__})",
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
    if payload.provider == _LOCAL_PROVIDER:
        # Dry run models the real decision path: a payload the adapter would
        # refuse at the trust boundary must not dry-run "complete".
        boundary = _local_trust_boundary_warning(payload)
        if boundary is not None:
            return PhaseDispatchResult(
                outcome="failed",
                handoff_id=f"dry-run:{payload.provider}:{payload.phase}:trust-boundary",
                provider=payload.provider,
                model_used=payload.model,
                dispatch_tier="dry_run",
                warnings=[f"dispatch would be refused for provider 'local': {boundary}"],
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
