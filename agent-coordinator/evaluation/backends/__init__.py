"""Agent backend adapters for evaluation.

Provides a protocol for submitting tasks to different agent
implementations and collecting standardized results.
"""

from .base import AgentBackend, BackendResult
from .claude_code import ClaudeCodeBackend
from .codex import CodexBackend
from .gemini_jules import GeminiJulesBackend

__all__ = [
    "AgentBackend",
    "BackendResult",
    "ClaudeCodeBackend",
    "CodexBackend",
    "GeminiJulesBackend",
]
