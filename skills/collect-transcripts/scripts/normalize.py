"""Normalized event schema for session transcript mining.

All vendor-specific adapters normalize their raw events into this common
schema so that downstream consumers (sanitizer, triage, deep-analysis)
operate on a single data shape.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventRole(str, Enum):
    """Who produced this event."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ContentType(str, Enum):
    """Content block type within an event."""
    TEXT = "text"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class ContentBlock:
    """A single content block within a normalized event."""
    type: ContentType
    text: str = ""
    # For tool_use blocks
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""
    # For tool_result blocks
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type.value, "text": self.text}
        if self.type == ContentType.TOOL_USE:
            d["tool_name"] = self.tool_name
            d["tool_input"] = self.tool_input
            d["tool_use_id"] = self.tool_use_id
        if self.type == ContentType.TOOL_RESULT:
            d["tool_use_id"] = self.tool_use_id
            d["is_error"] = self.is_error
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ContentBlock:
        return cls(
            type=ContentType(d.get("type", "unknown")),
            text=d.get("text", ""),
            tool_name=d.get("tool_name", ""),
            tool_input=d.get("tool_input", {}),
            tool_use_id=d.get("tool_use_id", ""),
            is_error=d.get("is_error", False),
        )


@dataclass
class TokenUsage:
    """Token usage counts for a single event."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TokenUsage:
        return cls(
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            cache_creation_input_tokens=d.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=d.get("cache_read_input_tokens", 0),
        )


@dataclass
class NormalizedEvent:
    """A single normalized event from a session transcript.

    This is the common schema that all vendor-specific adapters produce.
    Downstream consumers (sanitizer, triage, deep-analysis) operate on
    sequences of NormalizedEvent instances.
    """
    # Identity
    event_id: str = ""
    session_id: str = ""
    timestamp: str = ""  # ISO 8601
    sequence_number: int = 0

    # Content
    role: EventRole = EventRole.ASSISTANT
    content: list[ContentBlock] = field(default_factory=list)

    # Usage (optional, assistant events only)
    usage: TokenUsage | None = None

    # Provenance
    harness: str = ""  # e.g. "claude_code_cli", "codex_cli", "gemini_cli"
    model: str = ""
    version: str = ""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "sequence_number": self.sequence_number,
            "role": self.role.value,
            "content": [c.to_dict() for c in self.content],
            "harness": self.harness,
            "model": self.model,
            "version": self.version,
            "metadata": self.metadata,
        }
        if self.usage is not None:
            d["usage"] = self.usage.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizedEvent:
        usage = None
        if "usage" in d and d["usage"]:
            usage = TokenUsage.from_dict(d["usage"])
        return cls(
            event_id=d.get("event_id", ""),
            session_id=d.get("session_id", ""),
            timestamp=d.get("timestamp", ""),
            sequence_number=d.get("sequence_number", 0),
            role=EventRole(d.get("role", "assistant")),
            content=[ContentBlock.from_dict(c) for c in d.get("content", [])],
            usage=usage,
            harness=d.get("harness", ""),
            model=d.get("model", ""),
            version=d.get("version", ""),
            metadata=d.get("metadata", {}),
        )

    def to_jsonl_line(self) -> str:
        """Serialize to a single JSONL line."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_jsonl_line(cls, line: str) -> NormalizedEvent:
        """Deserialize from a single JSONL line."""
        return cls.from_dict(json.loads(line))


@dataclass
class SessionSummary:
    """Summary metadata for a discovered session."""
    session_id: str
    harness: str
    source_path: str = ""
    start_time: str = ""
    event_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
