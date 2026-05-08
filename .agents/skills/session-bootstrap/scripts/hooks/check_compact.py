#!/usr/bin/env python3
"""Stop hook: request /compact at context thresholds or phase boundaries.

Fires after every assistant turn (Stop lifecycle). Two trigger paths:

  1. **Threshold trip** — estimated context >= CLAUDE_COMPACT_THRESHOLD_PCT
     of CLAUDE_CONTEXT_LIMIT (default 70% of 200_000 tokens).
  2. **Phase boundary** — a PhaseRecord handoff JSON was just written under
     openspec/changes/<id>/handoffs/ in the last PHASE_BOUNDARY_WINDOW_SEC
     seconds. This is the "natural decomposition point" path.

When either trips, the hook emits ``{"decision": "block", "reason": "..."}``
to stdout. Claude Code interprets this as "do not yield to the user; re-prompt
the model with this reason" — which causes the agent to issue ``/compact`` on
its next turn.

Token estimation strategy (see phase_token_meter.py for prior art, decision D9):

  * **SDK path** — when ANTHROPIC_API_KEY is set AND the ``anthropic`` package
    imports cleanly, call ``client.messages.count_tokens(...)`` for an
    authoritative count. Adds ~200ms latency per Stop event.
  * **Proxy fallback** — sum char-lengths of transcript message content,
    divide by 4. Tolerable ±20% drift per D9.

A per-agent flag file (``~/.claude/compact-pending-<agent-id>.flag``) prevents
re-blocking on the next Stop after a /compact request has been issued. The
PreCompact hook (precompact_handoff.py) clears this flag.

Hook input (stdin JSON, per Claude Code spec):
    {"session_id": "...", "transcript_path": "...", "hook_event_name": "Stop"}
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PREFIX = "[check_compact]"
DEFAULT_THRESHOLD_PCT = 70
DEFAULT_CONTEXT_LIMIT = 200_000
PHASE_BOUNDARY_WINDOW_SEC = 60
CHAR_PER_TOKEN = 4


def _agent_id() -> str:
    return os.environ.get("AGENT_ID", "unknown")


def _flag_path() -> Path:
    return Path.home() / ".claude" / f"compact-pending-{_agent_id()}.flag"


def _read_hook_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw.isdigit() else default


def _transcript_messages(transcript_path: Path) -> list[dict[str, Any]]:
    """Reconstruct an Anthropic-API-shaped messages list from a Claude Code
    transcript JSONL. Each row's ``message`` field is already in the right
    shape (role + content); we just collect them in order."""
    messages: list[dict[str, Any]] = []
    if not transcript_path or not transcript_path.exists():
        return messages
    with transcript_path.open() as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = row.get("message")
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


def _proxy_estimate(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    for key in ("text", "content", "input"):
                        val = block.get(key)
                        if isinstance(val, str):
                            total += len(val)
    return total // CHAR_PER_TOKEN


def _sdk_estimate(messages: list[dict[str, Any]], model: str) -> int | None:
    """Authoritative count via Anthropic SDK. Returns None on any failure."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from env
        response = client.messages.count_tokens(model=model, messages=messages)
        tokens = getattr(response, "input_tokens", None)
        if isinstance(tokens, int) and tokens >= 0:
            return tokens
    except Exception as exc:  # noqa: BLE001
        print(f"{PREFIX} SDK count_tokens failed ({exc}); using proxy",
              file=sys.stderr)
    return None


def _measure_tokens(transcript_path: Path) -> int:
    """SDK path when ANTHROPIC_API_KEY is set and `anthropic` imports;
    otherwise proxy. Mirrors phase_token_meter.py priority order."""
    messages = _transcript_messages(transcript_path)
    if not messages:
        return 0
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        sdk_tokens = _sdk_estimate(messages, model)
        if sdk_tokens is not None:
            return sdk_tokens
    return _proxy_estimate(messages)


def _recent_phase_boundary() -> str | None:
    """Return the phase name (e.g. 'implementation') if a handoff JSON was
    written in the last PHASE_BOUNDARY_WINDOW_SEC seconds. PhaseRecord
    write_both() persists to openspec/changes/<id>/handoffs/<phase>-<N>.json
    in the local-fallback path."""
    cutoff = time.time() - PHASE_BOUNDARY_WINDOW_SEC
    newest_phase: str | None = None
    newest_mtime = 0.0
    for p in Path.cwd().glob("openspec/changes/*/handoffs/*.json"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff and mtime > newest_mtime:
            newest_mtime = mtime
            newest_phase = p.stem.rsplit("-", 1)[0]
    return newest_phase


def _block(reason: str) -> None:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


def main() -> int:
    flag = _flag_path()
    if flag.exists():
        return 0  # /compact already requested; PreCompact will clear the flag

    payload = _read_hook_input()
    transcript = Path(payload.get("transcript_path", ""))
    tokens = _measure_tokens(transcript)
    limit = _env_int("CLAUDE_CONTEXT_LIMIT", DEFAULT_CONTEXT_LIMIT)
    threshold = _env_int("CLAUDE_COMPACT_THRESHOLD_PCT", DEFAULT_THRESHOLD_PCT)
    pct = (tokens * 100) // max(limit, 1)
    boundary = _recent_phase_boundary()

    if pct >= threshold:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Context window at ~{pct}% of {limit:,} tokens "
            f"(threshold {threshold}%, agent={_agent_id()}). "
            f"Run /compact now. Phase handoffs are persisted, so context "
            f"will be rehydrated by SessionStart after compaction."
        )
    elif boundary:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Natural decomposition point reached: {boundary} handoff just "
            f"written. Run /compact now to consolidate context before the "
            f"next phase."
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Hooks must never crash Claude Code; degrade silently.
        print(f"{PREFIX} unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)
