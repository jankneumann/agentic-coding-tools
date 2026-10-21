"""OpenAI-compatible dispatch adapter (OpenSpec add-adaptive-model-router, D10).

Tier-2.5 adapter in review_dispatcher's vendor chain (after CLI tier-1 and SDK
tier-2). One adapter covers every endpoint that speaks the OpenAI chat-completions
API — OpenRouter (metered, under the monthly spend ceiling) and local Ollama/vLLM
endpoints — distinguished only by ``base_url`` and ``endpoint_kind``.

Design points:
- OpenRouter dispatch sets attribution headers and captures the response ``id``
  as the generation id for spend reconciliation via ``generation-get`` (D7).
- Local endpoints (Ollama/vLLM) need no attribution and tolerate a dummy key.
- The HTTP transport is injectable so the request-building, header, and
  generation-id-capture logic is unit-testable without network access.

Kept in its own module (not inlined into the ~1500-line review_dispatcher) to
keep the diff reviewable; it imports the shared ``ReviewResult`` / error
classification so it drops into the same dispatch chain.
"""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from review_dispatcher import (  # type: ignore[import-untyped]
    CliVendorAdapter,
    ErrorClass,
    ReviewResult,
    _coverage_quorum_threshold,
    _extract_diff_from_prompt,
    _extract_selected_files_from_prompt,
    classify_error,
    ingest_findings_output,
)

# transport(url, headers, body, timeout) -> parsed JSON response dict
Transport = Callable[[str, "dict[str, str]", "dict[str, Any]", int], "dict[str, Any]"]

_DEFAULT_REFERER = "https://github.com/agentic-coding-tools"
_DEFAULT_TITLE = "agentic-coding-tools"


def _default_transport(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: int
) -> dict[str, Any]:
    """Real HTTP transport (stdlib urllib). Never exercised in unit tests."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted base_url)
        return json.loads(resp.read().decode("utf-8"))


# get_transport(url, headers, timeout) -> (http_status, parsed JSON body or None).
# Raises on timeout / connection failure; an HTTP error status is *returned*, not
# raised, so the probe can classify it without ever touching the response text.
GetTransport = Callable[[str, "dict[str, str]", int], "tuple[int, dict[str, Any] | None]"]


def _default_get_transport(
    url: str, headers: dict[str, str], timeout: int
) -> tuple[int, dict[str, Any] | None]:
    """Real GET transport (stdlib urllib). Never exercised in unit tests.

    Uses the default SSL context, which honours ``SSL_CERT_FILE`` /
    ``SSL_CERT_DIR`` (needed behind the cloud egress proxy's CA bundle).
    """
    req = urllib.request.Request(url, headers=headers, method="GET")
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(  # noqa: S310 (trusted base_url)
            req, timeout=timeout, context=context
        ) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # Discard the error body unread: it may echo request details.
        exc.close()
        return exc.code, None
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None
    return status, body if isinstance(body, dict) else None


# Probe reasons (design D3). The spend_ceiling_* reasons are applied by the
# dispatcher's budget check on top of a successful probe (group 3), not here.
PROBE_AUTH_FAILED = "auth_failed"
PROBE_TIMEOUT = "probe_timeout"
PROBE_ENDPOINT_UNREACHABLE = "endpoint_unreachable"

_BUDGET_FIELDS = ("limit", "usage", "limit_remaining")

# Dispatch refusal for a packet whose sidecar has tools_overflow: true (D6).
PACKET_REQUIRES_TOOLS = "packet_requires_tools"


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of an authenticated no-op probe (design D3).

    ``budget`` holds only the numeric OpenRouter key fields ``limit``,
    ``usage`` and ``limit_remaining`` (each a float, or None when absent or
    non-numeric). It is None for local endpoints and for an OpenRouter body
    with no ``data`` object. Nothing else from the response is retained.
    """

    ok: bool
    reason: str | None = None
    budget: dict[str, float | None] | None = None


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _extract_budget(body: dict[str, Any] | None) -> dict[str, float | None] | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None
    return {name: _numeric(data.get(name)) for name in _BUDGET_FIELDS}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, (TimeoutError, socket.timeout))


class OpenAICompatAdapter:
    """Dispatch to an OpenAI-compatible endpoint (OpenRouter or local)."""

    def __init__(
        self,
        agent_id: str,
        vendor: str,
        model: str,
        base_url: str,
        endpoint_kind: str,
        model_fallbacks: list[str] | None = None,
        referer: str = _DEFAULT_REFERER,
        title: str = _DEFAULT_TITLE,
    ) -> None:
        self.agent_id = agent_id
        self.vendor = vendor
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.endpoint_kind = endpoint_kind
        self.model_fallbacks = model_fallbacks or []
        self.referer = referer
        self.title = title

    def can_dispatch(self, mode: str) -> bool:
        # Read-only review dispatch only, matching the SDK adapter's contract.
        return mode == "review"

    def build_headers(self, api_key: str | None) -> dict[str, str]:
        """Auth + (for OpenRouter) attribution headers."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.endpoint_kind == "openrouter":
            # OpenRouter attribution (ranks the app on their leaderboard).
            headers["HTTP-Referer"] = self.referer
            headers["X-Title"] = self.title
        return headers

    def build_request(self, prompt: str, model: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        if self.endpoint_kind == "openrouter":
            # Inline usage accounting: the response then carries usage.cost (D4).
            # https://openrouter.ai/docs/use-cases/usage-accounting
            body["usage"] = {"include": True}
        return body

    def _endpoint_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _probe_url(self) -> str:
        # OpenRouter: GET /api/v1/key returns the calling key's credit
        # ``limit``, ``usage`` and ``limit_remaining`` under ``data`` and costs
        # nothing. Docs: https://openrouter.ai/docs/api-reference/limits
        # (not re-fetched on 2026-10-21: openrouter.ai unreachable from the build sandbox).
        # Local (Ollama/vLLM): GET /v1/models is the cheapest authenticated no-op.
        if self.endpoint_kind == "openrouter":
            return f"{self.base_url}/key"
        return f"{self.base_url}/models"

    def probe(
        self,
        api_key: str | None,
        transport: GetTransport | None = None,
        timeout: int = 10,
    ) -> ProbeResult:
        """Authenticated, zero-cost dry probe of the endpoint (design D3).

        Sends exactly one GET (``/key`` for OpenRouter, ``/models`` for local
        endpoints) and never a chat completion. The response is parsed in
        memory and only the numeric budget fields are kept; no header, key,
        response body or exception text is logged, printed, or returned.
        """
        if self.endpoint_kind == "openrouter" and not api_key:
            return ProbeResult(ok=False, reason=PROBE_AUTH_FAILED)

        send = transport or _default_get_transport
        headers = self.build_headers(api_key)
        try:
            status, body = send(self._probe_url(), headers, timeout)
        except Exception as exc:  # noqa: BLE001 — classified, text discarded
            reason = PROBE_TIMEOUT if _is_timeout(exc) else PROBE_ENDPOINT_UNREACHABLE
            return ProbeResult(ok=False, reason=reason)

        if status in (401, 403):
            return ProbeResult(ok=False, reason=PROBE_AUTH_FAILED)
        if not 200 <= status < 300:
            return ProbeResult(ok=False, reason=PROBE_ENDPOINT_UNREACHABLE)
        budget = _extract_budget(body) if self.endpoint_kind == "openrouter" else None
        return ProbeResult(ok=True, reason=None, budget=budget)

    def dispatch(
        self,
        mode: str,
        prompt: str,
        cwd: Path | None = None,
        timeout_seconds: int = 300,
        api_key: str | None = None,
        transport: Transport | None = None,
        *,
        tools_overflow: bool = False,
    ) -> ReviewResult:
        """Dispatch via the OpenAI-compatible API with model fallback.

        Captures the generation id (``response["id"]``) for spend reconciliation.
        On a capacity/rate-limit error the next fallback model is tried; other
        errors return immediately.

        ``tools_overflow`` is the ``tools_overflow`` flag from the sidecar of
        the packet this lane receives. HTTP lanes cannot read files, so a
        packet that needs tools is refused before any request is sent (D6):
        reviewing it blind would manufacture false consensus.
        """
        if tools_overflow:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error=PACKET_REQUIRES_TOOLS,
                error_class=ErrorClass.UNAVAILABLE,
                agent_id=self.agent_id,
            )
        # OpenRouter (metered) requires a key; local endpoints may not.
        if self.endpoint_kind == "openrouter" and not api_key:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="No API key available for OpenRouter dispatch",
                error_class=ErrorClass.AUTH,
            )

        send = transport or _default_transport
        url = self._endpoint_url()
        headers = self.build_headers(api_key)
        models_to_try = [self.model, *self.model_fallbacks]
        models_attempted: list[str] = []
        last_error = ""
        start = time.monotonic()

        for model in models_to_try:
            models_attempted.append(model)
            try:
                resp = send(url, headers, self.build_request(prompt, model), timeout_seconds)
            except Exception as exc:  # noqa: BLE001 — classify + maybe fall back
                last_error = str(exc)
                err_class = classify_error(last_error)
                if err_class in (ErrorClass.CAPACITY, ErrorClass.TRANSIENT):
                    continue  # try next fallback model
                return ReviewResult(
                    vendor=self.vendor, success=False, error=last_error,
                    error_class=err_class, models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - start,
                )

            result = self._result_from_response(
                resp, model, models_attempted, time.monotonic() - start,
                prompt=prompt, cwd=cwd,
            )
            return self._with_usage(result, resp)

        return ReviewResult(
            vendor=self.vendor, success=False,
            error=last_error or "All models exhausted",
            error_class=ErrorClass.CAPACITY, models_attempted=models_attempted,
            elapsed_seconds=time.monotonic() - start,
        )

    def _result_from_response(
        self,
        resp: dict[str, Any],
        model: str,
        models_attempted: list[str],
        elapsed: float,
        *,
        prompt: str = "",
        cwd: Path | None = None,
    ) -> ReviewResult:
        """Turn one chat-completions response into a ReviewResult.

        The message content goes through the same ingest pipeline as CLI
        stdout (``ingest_findings_output``): coerce, validate, judgment
        stamp, line resolve against the packet diff, placeholder check and
        the empty-findings floor. An HTTP lane is held to the CLI contract.
        """
        content = _extract_content(resp)
        if not content:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Empty response content", error_class=ErrorClass.UNKNOWN,
                model_used=model, models_attempted=models_attempted,
                elapsed_seconds=elapsed, generation_id=resp.get("id"),
            )
        # Parse the model output into the dispatcher's review-findings shape
        # ({"findings": [...]}) using the same extractor the CLI/SDK adapters use.
        # A non-empty response that is NOT valid review-findings JSON is a failure,
        # not a silent success with zero findings.
        if CliVendorAdapter._parse_findings(content) is None:
            return ReviewResult(
                vendor=self.vendor, success=False,
                error="Review output was not valid review-findings JSON",
                error_class=ErrorClass.UNKNOWN,
                model_used=model, models_attempted=models_attempted,
                elapsed_seconds=elapsed, generation_id=resp.get("id"),
            )
        result = ingest_findings_output(
            self.vendor,
            content,
            "",
            elapsed=elapsed,
            model_name=model,
            models_attempted=models_attempted,
            packet_diff=_extract_diff_from_prompt(prompt),
            selected_files=_extract_selected_files_from_prompt(prompt),
            coverage_quorum_threshold=(
                _coverage_quorum_threshold(cwd) if cwd is not None else 0.8
            ),
        )
        result.generation_id = resp.get("id")
        result.agent_id = self.agent_id
        # The CLI path leaves error_class unset for a schema-invalid payload
        # (it then falls through vendor fallback as an unclassified error).
        # An HTTP response that parsed but failed ingest is a model-output
        # failure, so classify it explicitly.
        if not result.success and result.error_class is None:
            result.error_class = ErrorClass.UNKNOWN
        return result

    def _with_usage(self, result: ReviewResult, resp: dict[str, Any]) -> ReviewResult:
        """Copy the response's token counts and cost onto *result* (D4).

        Applied to every result built from a response, successful or not, so
        a billed-but-rejected review still reports its spend. cost_source is
        set only for metered (OpenRouter) lanes.
        """
        usage = resp.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        result.prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
        result.completion_tokens = _int_or_none(usage.get("completion_tokens"))
        result.cost_usd = _numeric(usage.get("cost"))
        if self.endpoint_kind == "openrouter":
            result.cost_source = "reported" if result.cost_usd is not None else "estimated"
        return result


def _extract_content(resp: dict[str, Any]) -> str | None:
    """Pull assistant text from an OpenAI-compatible chat response."""
    choices = resp.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if content else None
