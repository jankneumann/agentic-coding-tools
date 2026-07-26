"""Eval-backend registry and factory.

The single place that maps a supported roster name to its ``AgentBackend``
adapter. This is the pluggable-adapter seam the roster migration rides on:
adding, retiring, or reflagging a harness is a one-line change here plus an
adapter module, and everything else routes through :func:`build_backend`.

Requesting a retired harness (the removed Gemini/Jules backend) raises a
structured :class:`UnknownBackendError` naming the supported roster, satisfying
the evaluation-framework requirement "requesting one SHALL raise a structured
error naming the supported roster".
"""

from __future__ import annotations

from ..config import AgentBackendConfig
from .antigravity import AntigravityBackend
from .base import AgentBackend
from .claude_code import ClaudeCodeBackend
from .codex import CodexBackend
from .grok import GrokBackend
from .pi import PiBackend

# Supported roster: name (matches each backend's ``.name``) → adapter class.
SUPPORTED_BACKENDS: dict[str, type[AgentBackend]] = {
    "claude_code": ClaudeCodeBackend,
    "codex": CodexBackend,
    "antigravity": AntigravityBackend,
    "grok": GrokBackend,
    "pi": PiBackend,
}


class UnknownBackendError(ValueError):
    """Raised when a backend name is not part of the supported roster.

    Names the supported roster so a caller migrating off a retired harness
    (such as the removed Gemini/Jules backend) can see what to target instead.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        supported = ", ".join(sorted(SUPPORTED_BACKENDS))
        super().__init__(
            f"Unknown agent backend {name!r}. "
            f"Supported roster: {supported}."
        )


def get_backend_class(name: str) -> type[AgentBackend]:
    """Return the adapter class for a supported roster *name*.

    Raises:
        UnknownBackendError: if *name* is not in the supported roster.
    """
    try:
        return SUPPORTED_BACKENDS[name]
    except KeyError:
        raise UnknownBackendError(name) from None


def build_backend(config: AgentBackendConfig) -> AgentBackend:
    """Construct a backend adapter from *config* via its ``from_config``.

    Raises:
        UnknownBackendError: if ``config.name`` is not in the supported roster.
    """
    return get_backend_class(config.name).from_config(config)
