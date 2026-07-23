"""Agent backend adapters for evaluation.

Provides a protocol for submitting tasks to different agent implementations and
collecting standardized results, plus a factory (:func:`build_backend`) that
maps a supported roster name to its adapter. The roster is Claude Code, Codex,
antigravity, grok, and pi; the retired Gemini/Jules backend is absent and
requesting it raises :class:`UnknownBackendError`.
"""

from .antigravity import AntigravityBackend
from .base import AgentBackend, BackendResult
from .claude_code import ClaudeCodeBackend
from .codex import CodexBackend
from .grok import GrokBackend
from .pi import PiBackend
from .registry import (
    SUPPORTED_BACKENDS,
    UnknownBackendError,
    build_backend,
    get_backend_class,
)

__all__ = [
    "SUPPORTED_BACKENDS",
    "AgentBackend",
    "AntigravityBackend",
    "BackendResult",
    "ClaudeCodeBackend",
    "CodexBackend",
    "GrokBackend",
    "PiBackend",
    "UnknownBackendError",
    "build_backend",
    "get_backend_class",
]
