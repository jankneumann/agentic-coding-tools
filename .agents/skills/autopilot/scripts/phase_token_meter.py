"""Token-window measurement at autopilot phase boundaries.

Three execution paths (in priority order):
1. **SDK path** — call ``anthropic.messages.count_tokens(messages=...)`` to
   get the authoritative input-token count. Used in production.
2. **Proxy fallback** — when the SDK is unavailable or its call raises,
   estimate via ``sum(len(text) for text in extract(messages)) / 4``. The
   ÷4 ratio is a rough char-to-token approximation (D9: tolerable ±20%
   drift given the ≥30% reduction success criterion).
3. **Disabled path** — when ``AUTOPILOT_TOKEN_PROBE=disabled`` is set in
   the environment, return 0 immediately without calling the SDK or proxy.
   Used for offline/disconnected runs and CI.

See:
    openspec/changes/phase-record-compaction/design.md (decision D9)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DISABLED_VALUE = "disabled"
_PROBE_ENV_VAR = "AUTOPILOT_TOKEN_PROBE"


def measure_context(
    messages: list[dict[str, Any]],
    *,
    sdk_client: Any = None,
    model: str = "claude-opus-4-7",
) -> int:
    """Measure the token count of *messages* for the next-phase context window.

    Args:
        messages: List of {"role": ..., "content": ...} dicts. Content can be
            a plain string or a list of content blocks (text, tool_use, etc.).
        sdk_client: Optional pre-instantiated Anthropic client whose
            ``messages.count_tokens(...)`` method is the SDK path. If None,
            the proxy fallback is used directly.
        model: Model identifier passed to count_tokens. Used only on the
            SDK path.

    Returns:
        Estimated input-token count, or 0 when disabled / on empty input.
        Always non-negative.
    """
    # Disabled path — earliest exit, no work
    if os.environ.get(_PROBE_ENV_VAR) == _DISABLED_VALUE:
        return 0

    # SDK path
    if sdk_client is not None:
        try:
            response = sdk_client.messages.count_tokens(
                model=model,
                messages=messages,
            )
            tokens = getattr(response, "input_tokens", None)
            if isinstance(tokens, int) and tokens >= 0:
                return tokens
            logger.warning(
                "phase_token_meter: SDK count_tokens returned non-int "
                "input_tokens=%r, falling back to proxy",
                tokens,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "phase_token_meter: SDK count_tokens failed (%s: %s); "
                "falling back to proxy",
                type(exc).__name__, exc,
            )

    # Proxy fallback
    return _proxy_estimate(messages)


def _proxy_estimate(messages: list[dict[str, Any]]) -> int:
    """Approximate token count via char-length / 4.

    Handles three content shapes defensively:
    - str — len(content)
    - list of content blocks — sum of len(block["text"]) where present
    - anything else — 0 for that message
    """
    total = 0
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        total += len(text)
        # else: unknown content type → contribute 0
    return total // 4


__all__ = ["measure_context"]
