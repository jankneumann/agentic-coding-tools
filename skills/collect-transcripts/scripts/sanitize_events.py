"""Sanitize normalized event streams for transcript mining.

Applies the session-log sanitizer to NormalizedEvent streams, with
extended coverage for tool-call argument blobs and tool-result outputs
which are common accidental-leak sites.

Sanitization MUST happen before any LLM sees the content.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Import the session-log sanitizer
_SESSION_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "session-log" / "scripts"
if str(_SESSION_LOG_DIR) not in sys.path:
    sys.path.insert(0, str(_SESSION_LOG_DIR))

from sanitize_session_log import sanitize as sanitize_text  # noqa: E402

# Also need our normalize module
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from normalize import ContentBlock, ContentType, NormalizedEvent  # noqa: E402


def sanitize_content_block(block: ContentBlock) -> tuple[ContentBlock, list[dict[str, str]]]:
    """Sanitize a single content block, returning the sanitized block and redactions."""
    all_redactions: list[dict[str, str]] = []

    # Sanitize text content
    sanitized_text = block.text
    if block.text:
        sanitized_text, redactions = sanitize_text(block.text)
        all_redactions.extend(redactions)

    # Sanitize tool_input (tool_use blocks) — serialize, sanitize, deserialize
    sanitized_input = block.tool_input
    if block.type == ContentType.TOOL_USE and block.tool_input:
        input_str = json.dumps(block.tool_input, default=str)
        sanitized_input_str, redactions = sanitize_text(input_str)
        all_redactions.extend(redactions)
        try:
            sanitized_input = json.loads(sanitized_input_str)
        except json.JSONDecodeError:
            sanitized_input = {"_sanitized": sanitized_input_str}

    return ContentBlock(
        type=block.type,
        text=sanitized_text,
        tool_name=block.tool_name,
        tool_input=sanitized_input,
        tool_use_id=block.tool_use_id,
        is_error=block.is_error,
    ), all_redactions


def sanitize_event(event: NormalizedEvent) -> tuple[NormalizedEvent, list[dict[str, str]]]:
    """Sanitize a single NormalizedEvent, returning the sanitized event and redactions."""
    all_redactions: list[dict[str, str]] = []
    sanitized_content: list[ContentBlock] = []

    for block in event.content:
        sanitized_block, redactions = sanitize_content_block(block)
        sanitized_content.append(sanitized_block)
        all_redactions.extend(redactions)

    # Sanitize metadata values
    sanitized_metadata = {}
    if event.metadata:
        meta_str = json.dumps(event.metadata, default=str)
        sanitized_meta_str, redactions = sanitize_text(meta_str)
        all_redactions.extend(redactions)
        try:
            sanitized_metadata = json.loads(sanitized_meta_str)
        except json.JSONDecodeError:
            sanitized_metadata = {"_sanitized": sanitized_meta_str}

    return NormalizedEvent(
        event_id=event.event_id,
        session_id=event.session_id,
        timestamp=event.timestamp,
        sequence_number=event.sequence_number,
        role=event.role,
        content=sanitized_content,
        usage=event.usage,
        harness=event.harness,
        model=event.model,
        version=event.version,
        metadata=sanitized_metadata,
    ), all_redactions


def sanitize_event_stream(
    events: list[NormalizedEvent],
) -> tuple[list[NormalizedEvent], list[dict[str, str]]]:
    """Sanitize a full stream of NormalizedEvents.

    Returns the sanitized events and a flat list of all redactions applied.
    """
    all_redactions: list[dict[str, str]] = []
    sanitized_events: list[NormalizedEvent] = []

    for event in events:
        sanitized_event, redactions = sanitize_event(event)
        sanitized_events.append(sanitized_event)
        all_redactions.extend(redactions)

    return sanitized_events, all_redactions
