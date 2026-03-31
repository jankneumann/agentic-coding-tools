"""HTTP transport client using httpx."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from evaluation.gen_eval.descriptor import AuthConfig
from evaluation.gen_eval.models import ActionStep

from .base import StepContext, StepResult


class HttpClient:
    """Execute HTTP steps via httpx.AsyncClient with auth injection."""

    def __init__(
        self,
        base_url: str,
        auth: AuthConfig | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._default_timeout = default_timeout
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _resolve_auth_headers(self) -> dict[str, str]:
        """Build auth headers from the AuthConfig."""
        if self._auth is None or self._auth.type == "none":
            return {}

        value = self._auth.value
        if value is None and self._auth.env_var:
            value = os.environ.get(self._auth.env_var, "")

        if not value:
            return {}

        if self._auth.type == "api_key":
            return {self._auth.header: value}
        if self._auth.type == "bearer":
            return {"Authorization": f"Bearer {value}"}
        if self._auth.type == "basic":
            return {"Authorization": f"Basic {value}"}
        return {}

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._default_timeout),
            )
        return self._client

    # ------------------------------------------------------------------
    # TransportClient protocol
    # ------------------------------------------------------------------

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Send an HTTP request described by *step*."""
        start = time.perf_counter()
        try:
            client = await self._ensure_client()
            timeout = step.timeout_seconds or context.timeout_seconds

            # Merge auth + step headers
            headers: dict[str, str] = {}
            headers.update(self._resolve_auth_headers())
            if step.headers:
                headers.update(step.headers)

            method = (step.method or "GET").upper()
            url = step.endpoint or "/"

            # Substitute captured variables into URL and body
            url = self._interpolate(url, context.variables)
            body = self._interpolate_body(step.body, context.variables)

            response = await client.request(
                method,
                url,
                headers=headers,
                json=body if body is not None else None,
                timeout=httpx.Timeout(timeout),
            )

            # Parse response body
            try:
                resp_body: dict[str, Any] = response.json()
            except Exception:
                resp_body = {"raw": response.text}

            resp_headers = dict(response.headers)

            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(
                status_code=response.status_code,
                body=resp_body,
                headers=resp_headers,
                duration_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(error=str(exc), duration_ms=elapsed)

    async def health_check(self) -> bool:
        """GET /health on the base URL."""
        try:
            client = await self._ensure_client()
            resp = await client.get("/health", timeout=httpx.Timeout(5.0))
            return resp.status_code < 500
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Close the underlying httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Variable interpolation
    # ------------------------------------------------------------------

    @staticmethod
    def _interpolate(text: str, variables: dict[str, Any]) -> str:
        """Replace ``${var}`` placeholders in *text*."""
        for key, val in variables.items():
            text = text.replace(f"${{{key}}}", str(val))
        return text

    @classmethod
    def _interpolate_body(
        cls, body: Any, variables: dict[str, Any]
    ) -> Any:
        if isinstance(body, dict):
            return {k: cls._interpolate_body(v, variables) for k, v in body.items()}
        elif isinstance(body, list):
            return [cls._interpolate_body(item, variables) for item in body]
        elif isinstance(body, str):
            for key, val in variables.items():
                body = body.replace(f"${{{key}}}", str(val))
            return body
        return body
