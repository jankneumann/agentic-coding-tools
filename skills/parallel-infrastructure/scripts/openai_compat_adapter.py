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
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from review_dispatcher import (  # type: ignore[import-untyped]
    CliVendorAdapter,
    ErrorClass,
    ReviewResult,
    classify_error,
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
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }

    def _endpoint_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def dispatch(
        self,
        mode: str,
        prompt: str,
        cwd: Path | None = None,
        timeout_seconds: int = 300,
        api_key: str | None = None,
        transport: Transport | None = None,
    ) -> ReviewResult:
        """Dispatch via the OpenAI-compatible API with model fallback.

        Captures the generation id (``response["id"]``) for spend reconciliation.
        On a capacity/rate-limit error the next fallback model is tried; other
        errors return immediately.
        """
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

            content = _extract_content(resp)
            if not content:
                return ReviewResult(
                    vendor=self.vendor, success=False,
                    error="Empty response content", error_class=ErrorClass.UNKNOWN,
                    model_used=model, models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - start,
                    generation_id=resp.get("id"),
                )
            # Parse the model output into the dispatcher's review-findings shape
            # ({"findings": [...]}) using the same extractor the CLI/SDK adapters use.
            # A non-empty response that is NOT valid review-findings JSON is a failure,
            # not a silent success with zero findings.
            findings = CliVendorAdapter._parse_findings(content)
            if findings is None:
                return ReviewResult(
                    vendor=self.vendor, success=False,
                    error="Review output was not valid review-findings JSON",
                    error_class=ErrorClass.UNKNOWN,
                    model_used=model, models_attempted=models_attempted,
                    elapsed_seconds=time.monotonic() - start,
                    generation_id=resp.get("id"),
                )
            return ReviewResult(
                vendor=self.vendor,
                success=True,
                findings=findings,
                model_used=model,
                models_attempted=models_attempted,
                elapsed_seconds=time.monotonic() - start,
                error=None,
                generation_id=resp.get("id"),
            )

        return ReviewResult(
            vendor=self.vendor, success=False,
            error=last_error or "All models exhausted",
            error_class=ErrorClass.CAPACITY, models_attempted=models_attempted,
            elapsed_seconds=time.monotonic() - start,
        )


def _extract_content(resp: dict[str, Any]) -> str | None:
    """Pull assistant text from an OpenAI-compatible chat response."""
    choices = resp.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if content else None
