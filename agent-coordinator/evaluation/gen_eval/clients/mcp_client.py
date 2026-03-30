"""MCP transport client using fastmcp SDK (SSE transport)."""

from __future__ import annotations

import time
from typing import Any

from evaluation.gen_eval.models import ActionStep

from .base import StepContext, StepResult


class McpClient:
    """Execute MCP tool invocations over SSE via the fastmcp SDK."""

    def __init__(self, mcp_url: str, default_timeout: float = 30.0) -> None:
        self._mcp_url = mcp_url
        self._default_timeout = default_timeout
        self._client: Any | None = None

    async def _ensure_client(self) -> Any:
        if self._client is None:
            from fastmcp import Client as FastMCPClient

            self._client = FastMCPClient(self._mcp_url)
            await self._client.__aenter__()
        return self._client

    # ------------------------------------------------------------------
    # TransportClient protocol
    # ------------------------------------------------------------------

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Invoke an MCP tool described by *step*."""
        start = time.perf_counter()
        try:
            client = await self._ensure_client()
            tool_name = step.tool
            if not tool_name:
                elapsed = (time.perf_counter() - start) * 1000
                return StepResult(error="No tool specified in step", duration_ms=elapsed)

            params = dict(step.params or {})
            # Substitute captured variables
            for k, v in list(params.items()):
                if isinstance(v, str):
                    for var_key, var_val in context.variables.items():
                        v = v.replace(f"${{{var_key}}}", str(var_val))
                    params[k] = v

            result = await client.call_tool(tool_name, params)

            # Normalise fastmcp response into a body dict
            body: dict[str, Any] = {}
            if isinstance(result, dict):
                body = result
            elif isinstance(result, list):
                # fastmcp returns list of content blocks
                texts = []
                for item in result:
                    if hasattr(item, "text"):
                        texts.append(item.text)
                    elif isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                    else:
                        texts.append(str(item))
                body = {"result": "\n".join(texts)}
            else:
                body = {"result": str(result)}

            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(body=body, duration_ms=elapsed)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(error=str(exc), duration_ms=elapsed)

    async def health_check(self) -> bool:
        """Check MCP server reachability by listing tools."""
        try:
            client = await self._ensure_client()
            tools = await client.list_tools()
            return isinstance(tools, list)
        except Exception:
            return False

    async def cleanup(self) -> None:
        """Close the MCP client session."""
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
