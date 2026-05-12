"""Multi-vendor LLM client for structured output.

**Mode B only** — this module is used by the headless semantic
decomposer (``semantic_decomposer.py``), which is the batch/CI path
(e.g., ``autopilot-roadmap``). When plan-roadmap is invoked from an
interactive Claude Code session, use Mode A (host-assisted) via
``curator.py`` instead; the orchestrating agent performs semantic
reasoning directly, no external API key required. See ``SKILL.md`` for
the mode matrix.

Thin wrapper providing vendor-agnostic structured calls with model
fallback.  Discovers available vendors from environment variables
(ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY) and tries them
in priority order.

Borrows error-handling patterns from
``skills/parallel-infrastructure/scripts/review_dispatcher.py``
(capacity/auth/transient classification, model fallback chain)
but stays independent — the review dispatcher is tightly coupled
to the review workflow.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default models per vendor (cost/quality sweet-spot for decomposition)
# ---------------------------------------------------------------------------
_VENDOR_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "anthropic": {
        "env": ["ANTHROPIC_API_KEY"],
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "openai": {
        "env": ["OPENAI_API_KEY"],
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    "google": {
        "env": ["GOOGLE_API_KEY"],
        "models": ["gemini-2.5-flash", "gemini-2.0-flash"],
    },
}


# ---------------------------------------------------------------------------
# Result + exceptions
# ---------------------------------------------------------------------------
@dataclass
class LlmResult:
    """Result from a successful LLM call."""

    content: str
    model_used: str
    vendor: str


class LlmCapacityError(Exception):
    """Vendor returned 429 / rate-limit."""


class LlmAuthError(Exception):
    """Vendor returned 401 / invalid key."""


class LlmTransientError(Exception):
    """Network or server error."""


class LlmExhaustedError(Exception):
    """All vendors and models exhausted."""


# ---------------------------------------------------------------------------
# Vendor entry
# ---------------------------------------------------------------------------
@dataclass
class _VendorEntry:
    name: str
    api_key: str
    models: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class LlmClient:
    """Multi-vendor LLM client with model fallback.

    Usage::

        client = LlmClient.discover()
        if client is None:
            # No vendor available — fall back to structural-only
            ...
        result = client.structured_call(system="...", user="...")
        data = json.loads(result.content)
    """

    def __init__(self, vendors: list[_VendorEntry]) -> None:
        self._vendors = vendors

    @classmethod
    def discover(cls) -> LlmClient | None:
        """Auto-discover available vendors from environment variables.

        Checks ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY in
        priority order.  Returns ``None`` if no vendor is available,
        which signals callers to fall back to structural-only mode.
        """
        vendors: list[_VendorEntry] = []
        for vendor_name, cfg in _VENDOR_DEFAULTS.items():
            for env_var in cfg["env"]:
                key = os.environ.get(env_var)
                if key:
                    vendors.append(
                        _VendorEntry(
                            name=vendor_name,
                            api_key=key,
                            models=list(cfg["models"]),
                        )
                    )
                    break  # one key per vendor
        return cls(vendors) if vendors else None

    def structured_call(
        self,
        system: str,
        user: str,
        max_tokens: int = 8192,
        timeout: int = 120,
    ) -> LlmResult:
        """Make a structured LLM call, trying vendors and models in order.

        Expects JSON output from the LLM.  Parses with fallback
        extraction (finds outermost ``{...}`` if direct parse fails).

        Raises ``LlmExhaustedError`` if all vendors/models fail.
        """
        last_error = ""
        for vendor in self._vendors:
            for model in vendor.models:
                try:
                    content = self._call_vendor(
                        vendor.name, vendor.api_key, model,
                        system, user, max_tokens, timeout,
                    )
                    return LlmResult(
                        content=content,
                        model_used=model,
                        vendor=vendor.name,
                    )
                except LlmCapacityError:
                    logger.info(
                        "%s/%s capacity exhausted, trying fallback",
                        vendor.name, model,
                    )
                    continue
                except LlmAuthError as exc:
                    logger.warning("%s auth error: %s", vendor.name, exc)
                    break  # skip remaining models for this vendor
                except LlmTransientError as exc:
                    last_error = str(exc)
                    logger.warning(
                        "%s/%s transient error: %s",
                        vendor.name, model, str(exc)[:200],
                    )
                    break

        raise LlmExhaustedError(
            f"All vendors/models exhausted. Last error: {last_error}"
        )

    def _call_vendor(
        self,
        vendor: str,
        api_key: str,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        timeout: int,
    ) -> str:
        """Dispatch to vendor-specific SDK call."""
        if vendor == "anthropic":
            return self._call_anthropic(api_key, model, system, user, max_tokens, timeout)
        elif vendor == "openai":
            return self._call_openai(api_key, model, system, user, max_tokens, timeout)
        elif vendor == "google":
            return self._call_google(api_key, model, system, user, max_tokens, timeout)
        raise ValueError(f"Unknown vendor: {vendor}")

    def _call_anthropic(
        self, api_key: str, model: str, system: str, user: str,
        max_tokens: int, timeout: int,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text if response.content else ""
        except anthropic.RateLimitError:
            raise LlmCapacityError()
        except anthropic.AuthenticationError as exc:
            raise LlmAuthError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise LlmTransientError(str(exc))

    def _call_openai(
        self, api_key: str, model: str, system: str, user: str,
        max_tokens: int, timeout: int,
    ) -> str:
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=timeout)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content or ""
        except openai.RateLimitError:
            raise LlmCapacityError()
        except openai.AuthenticationError as exc:
            raise LlmAuthError(str(exc))
        except Exception as exc:  # noqa: BLE001
            raise LlmTransientError(str(exc))

    def _call_google(
        self, api_key: str, model: str, system: str, user: str,
        max_tokens: int, timeout: int,
    ) -> str:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        try:
            response = gen_model.generate_content(
                f"{system}\n\n{user}",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text if response.text else ""
        except Exception as exc:  # noqa: BLE001
            err_lower = str(exc).lower()
            if "429" in err_lower or "resource_exhausted" in err_lower:
                raise LlmCapacityError()
            if "401" in err_lower or "api_key" in err_lower:
                raise LlmAuthError(str(exc))
            raise LlmTransientError(str(exc))


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict | list | None:
    """Extract JSON from LLM response with fallback strategies.

    1. Try direct JSON parse
    2. Try finding outermost { ... } or [ ... ]
    3. Strip markdown code fences and retry
    """
    if not text:
        return None

    # Strategy 1: direct parse
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences (```json ... ```)
    stripped = re.sub(r"^```\w*\n", "", text.strip())
    stripped = re.sub(r"\n```\s*$", "", stripped)
    if stripped != text:
        try:
            return json.loads(stripped)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # Strategy 3: find outermost { ... } or [ ... ]
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = text.find(open_char)
        end = text.rfind(close_char)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                continue

    return None
