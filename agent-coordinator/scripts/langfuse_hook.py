#!/usr/bin/env python3
"""Langfuse tracing hook for Claude Code sessions.

This script runs as a Claude Code Stop hook. After each assistant response,
it reads the session transcript and sends new conversation turns to Langfuse
as traces with nested spans for tool invocations.

The hook processes incrementally -- only new messages since the last run are
sent, using a state file to track progress.

Usage (in ~/.claude/settings.json or .claude/settings.local.json):
    {
        "env": {
            "LANGFUSE_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
            "LANGFUSE_SECRET_KEY": "sk-lf-...",
            "LANGFUSE_HOST": "http://localhost:3050"
        },
        "hooks": {
            "Stop": [{
                "hooks": [{
                    "type": "command",
                    "command": "uv run --with 'langfuse>=3.0,<4.0' ..."
                }]
            }]
        }
    }

Alternatively, if the agent-coordinator venv is available:
    "command": "/path/to/agent-coordinator/.venv/bin/python /path/to/langfuse_hook.py"

Environment variables:
    LANGFUSE_ENABLED: Must be "true" to enable (default: false)
    LANGFUSE_PUBLIC_KEY: Langfuse project public key
    LANGFUSE_SECRET_KEY: Langfuse project secret key
    LANGFUSE_HOST: Langfuse server URL (default: http://localhost:3050)
    LANGFUSE_DEBUG: Enable debug logging (default: false)
    CLAUDE_SESSION_ID: Override session ID (auto-detected from transcript path)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
STATE_DIR = Path.home() / ".claude" / "state"
LOG_FILE = STATE_DIR / "langfuse_hook.log"


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    debug = os.environ.get("LANGFUSE_DEBUG", "").lower() == "true"
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transcript discovery
# ---------------------------------------------------------------------------


def find_transcript() -> Path | None:
    """Find the most recently modified transcript.jsonl for the current session."""
    # Claude Code stores transcripts under ~/.claude/projects/<hash>/<session>.jsonl
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    # Find the most recently modified .jsonl file
    transcripts = sorted(
        projects_dir.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return transcripts[0] if transcripts else None


def extract_session_id(transcript_path: Path) -> str:
    """Extract a session ID from the transcript path or environment."""
    env_session = os.environ.get("CLAUDE_SESSION_ID")
    if env_session:
        return env_session

    # Use the filename (without extension) as session ID
    return transcript_path.stem


def extract_project_name(transcript_path: Path) -> str:
    """Extract the project name from the transcript path."""
    # Path is typically: ~/.claude/projects/<project-hash>/session.jsonl
    # The project hash directory name is the project identifier
    project_dir = transcript_path.parent.name
    # Try to get a human-readable name from the CWD
    cwd = os.environ.get("PWD", os.getcwd())
    return Path(cwd).name or project_dir


# ---------------------------------------------------------------------------
# State management (incremental processing)
# ---------------------------------------------------------------------------


def get_state_path(session_id: str) -> Path:
    """Get the state file path for a session."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    return STATE_DIR / f"langfuse_state_{safe_id}.json"


def load_state(session_id: str) -> dict[str, Any]:
    """Load processing state for a session."""
    path = get_state_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_line": 0, "trace_count": 0}


def save_state(session_id: str, state: dict[str, Any]) -> None:
    """Save processing state for a session."""
    path = get_state_path(session_id)
    try:
        path.write_text(json.dumps(state, indent=2) + "\n")
    except OSError as exc:
        logger.warning("Failed to save state: %s", exc)


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------


def parse_transcript_lines(
    transcript_path: Path, start_line: int
) -> tuple[list[dict[str, Any]], int]:
    """Read new lines from a transcript file starting at a given offset.

    Returns (messages, lines_consumed) where lines_consumed counts all lines
    read (including blank/invalid ones) so the cursor advances correctly.
    """
    messages: list[dict[str, Any]] = []
    lines_consumed = 0
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < start_line:
                    continue
                lines_consumed += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.error("Failed to read transcript: %s", exc)
    return messages, lines_consumed


def group_into_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group sequential messages into conversation turns.

    A turn starts with a user or system message and includes all subsequent
    assistant messages and tool calls until the next user message.
    """
    turns: list[dict[str, Any]] = []
    current_turn: dict[str, Any] | None = None

    for msg in messages:
        role = msg.get("role", "")

        if role == "user":
            if current_turn is not None:
                turns.append(current_turn)
            current_turn = {
                "user_message": _extract_text(msg),
                "assistant_messages": [],
                "tool_calls": [],
                "model": "",
                "timestamp": msg.get("timestamp"),
            }
        elif role == "assistant" and current_turn is not None:
            text = _extract_text(msg)
            if text:
                current_turn["assistant_messages"].append(text)
            # Extract model info
            if msg.get("model"):
                current_turn["model"] = msg["model"]
            # Extract tool use blocks
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        current_turn["tool_calls"].append({
                            "name": block.get("name", "unknown"),
                            "input": block.get("input", {}),
                        })
        elif role == "tool" and current_turn is not None:
            # Tool results -- attach to the most recent tool call
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            # Find matching tool call and attach result
            for tc in current_turn["tool_calls"]:
                if not tc.get("output"):
                    tc["output"] = _truncate(str(content), 2000)
                    break

    if current_turn is not None:
        turns.append(current_turn)

    return turns


def _extract_text(msg: dict[str, Any]) -> str:
    """Extract text content from a message."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


def sanitize(text: str) -> str:
    """Redact common secret patterns from text.

    Patterns are ordered from most specific to most general to prevent
    the generic key=value rule from masking more descriptive replacements.
    """
    # Langfuse keys (pk-lf-*, sk-lf-*) — before generic sk- pattern
    text = re.sub(r"[ps]k-lf-[a-zA-Z0-9_-]{10,}", "LF-KEY-REDACTED", text)
    # Anthropic / OpenAI style API keys
    text = re.sub(r"sk-[a-zA-Z0-9_-]{20,}", "SK-REDACTED", text)
    # Supabase service keys (sbp_*)
    text = re.sub(r"sbp_[a-zA-Z0-9]{20,}", "SBP-REDACTED", text)
    # JWT tokens (eyJ* base64url segments separated by dots)
    text = re.sub(r"eyJ[a-zA-Z0-9_.-]{50,}", "JWT-REDACTED", text)
    # Bearer tokens
    text = re.sub(r"Bearer [a-zA-Z0-9._-]+", "Bearer REDACTED", text)
    # Generic key=value secret patterns (last — catches remaining secrets)
    text = re.sub(r"(?i)(password|secret|token|api_key|apikey)\s*[:=]\s*\S+", r"\1=REDACTED", text)
    return text


# ---------------------------------------------------------------------------
# Langfuse trace creation
# ---------------------------------------------------------------------------


def send_turns_to_langfuse(
    turns: list[dict[str, Any]],
    session_id: str,
    project_name: str,
) -> int:
    """Send conversation turns to Langfuse as traces. Returns count of traces created."""
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.error("langfuse package not available")
        return 0

    try:
        lf = Langfuse(
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3050"),
            debug=os.environ.get("LANGFUSE_DEBUG", "").lower() == "true",
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Failed to create Langfuse client: %s", exc)
        return 0

    agent_id = os.environ.get("AGENT_ID", os.environ.get("USER", "unknown"))
    count = 0

    for i, turn in enumerate(turns):
        user_text = sanitize(turn["user_message"])
        assistant_text = sanitize("\n".join(turn["assistant_messages"]))

        trace = lf.trace(
            name=f"turn-{i}",
            session_id=session_id,
            user_id=agent_id,
            input=user_text,
            output=assistant_text,
            metadata={
                "project": project_name,
                "model": turn.get("model", ""),
                "tool_count": len(turn["tool_calls"]),
                "source": "claude-code-hook",
                "hostname": os.uname().nodename,
            },
            tags=["claude-code", "coding-session", project_name],
        )

        # Create child spans for each tool call
        for tc in turn["tool_calls"]:
            tool_input = tc.get("input", {})
            tool_output = tc.get("output", "")

            # Sanitize tool inputs/outputs
            if isinstance(tool_input, dict):
                tool_input = {
                    k: sanitize(str(v)) if isinstance(v, str) else v
                    for k, v in tool_input.items()
                }
            if isinstance(tool_output, str):
                tool_output = sanitize(tool_output)

            span = trace.span(
                name=f"tool:{tc['name']}",
                input=tool_input,
                metadata={"tool_name": tc["name"]},
            )
            span.end(output=tool_output)

        count += 1

    # Flush all events
    try:
        lf.flush()
    except Exception as exc:
        logger.warning("Langfuse flush failed: %s", exc)

    try:
        lf.shutdown()
    except Exception:
        pass

    return count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    setup_logging()

    if os.environ.get("LANGFUSE_ENABLED", "").lower() != "true":
        return

    if not os.environ.get("LANGFUSE_PUBLIC_KEY") or not os.environ.get("LANGFUSE_SECRET_KEY"):
        logger.warning("LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set, skipping")
        return

    transcript = find_transcript()
    if transcript is None:
        logger.debug("No transcript found")
        return

    session_id = extract_session_id(transcript)
    project_name = extract_project_name(transcript)
    state = load_state(session_id)

    logger.debug(
        "Processing session=%s project=%s from_line=%d",
        session_id, project_name, state["last_line"],
    )

    messages, lines_consumed = parse_transcript_lines(transcript, state["last_line"])
    if not messages:
        # Still advance past any blank/invalid lines we consumed
        if lines_consumed > 0:
            state["last_line"] = state["last_line"] + lines_consumed
            save_state(session_id, state)
        logger.debug("No new messages to process")
        return

    turns = group_into_turns(messages)
    if not turns:
        # Still advance cursor past consumed lines to avoid re-reading
        state["last_line"] = state["last_line"] + lines_consumed
        save_state(session_id, state)
        logger.debug("No complete turns found")
        return

    count = send_turns_to_langfuse(turns, session_id, project_name)

    # Update state — advance by lines consumed (not messages parsed)
    state["last_line"] = state["last_line"] + lines_consumed
    state["trace_count"] = state.get("trace_count", 0) + count
    state["last_run"] = time.time()
    save_state(session_id, state)

    logger.info(
        "Sent %d turn(s) to Langfuse (session=%s, total_traces=%d)",
        count, session_id, state["trace_count"],
    )


if __name__ == "__main__":
    main()
