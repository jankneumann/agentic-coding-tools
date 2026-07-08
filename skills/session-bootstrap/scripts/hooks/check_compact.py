#!/usr/bin/env python3
"""Stop hook: request /compact at context thresholds or phase boundaries.

Fires after every assistant turn (Stop lifecycle). Two trigger paths:

  1. **Threshold trip** — estimated context >= CLAUDE_COMPACT_THRESHOLD_PCT
     of CLAUDE_CONTEXT_LIMIT (default 40% of 1_000_000 tokens, i.e. ~400k).
     Modern Claude models (Opus 4.7, Sonnet 4.6) support 1M-token contexts;
     prompting /compact at 400k still leaves substantial headroom for the
     rest of the session while keeping per-turn latency and cost in check.
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

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PREFIX = "[check_compact]"
DEFAULT_THRESHOLD_PCT = 40
DEFAULT_CONTEXT_LIMIT = 1_000_000
PHASE_BOUNDARY_WINDOW_SEC = 300
CHAR_PER_TOKEN = 4
SDK_CACHE_TTL_SEC = 30


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


def _extract_block_chars(block: dict[str, Any]) -> int:
    """Type-aware char extraction for one content block.

    Real transcripts contain four block types (text, thinking, tool_use,
    tool_result) with different content-bearing keys:
      * text       → block["text"]                 (str)
      * thinking   → block["thinking"]             (str)
      * tool_use   → block["input"]                (dict — JSON-serialize)
      * tool_result→ block["content"]              (str OR list of blocks)
    """
    btype = block.get("type", "")
    if btype == "text":
        text = block.get("text")
        return len(text) if isinstance(text, str) else 0
    if btype == "thinking":
        text = block.get("thinking")
        return len(text) if isinstance(text, str) else 0
    if btype == "tool_use":
        try:
            return len(json.dumps(block.get("input", {}), default=str))
        except (TypeError, ValueError):
            return 0
    if btype == "tool_result":
        content = block.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return sum(
                _extract_block_chars(sub)
                for sub in content
                if isinstance(sub, dict)
            )
        return 0
    # Unknown block type — best-effort fallback to any string-typed value.
    total = 0
    for value in block.values():
        if isinstance(value, str):
            total += len(value)
    return total


def _proxy_estimate(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += _extract_block_chars(block)
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


def _sdk_cache_path(transcript_path: Path) -> Path:
    """Per-transcript SDK cache path. Hashing isolates sessions cleanly
    without coupling to AGENT_ID, which may be unset."""
    key = hashlib.sha1(str(transcript_path).encode()).hexdigest()[:16]
    return Path.home() / ".claude" / f"compact-token-cache-{key}.json"


def _sdk_cache_lookup(transcript_path: Path) -> int | None:
    """Return cached token count when:
      - the transcript hasn't changed since last measurement (exact hit), OR
      - the cache is fresh within SDK_CACHE_TTL_SEC (rate-limit hit).
    Otherwise return None and force a fresh SDK call."""
    cache_path = _sdk_cache_path(transcript_path)
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    cached_tokens = cache.get("tokens")
    if not isinstance(cached_tokens, int):
        return None
    try:
        current_mtime = transcript_path.stat().st_mtime
    except OSError:
        current_mtime = 0.0
    if cache.get("transcript_mtime") == current_mtime:
        return cached_tokens
    if (time.time() - cache.get("computed_at", 0.0)) < SDK_CACHE_TTL_SEC:
        return cached_tokens
    return None


def _sdk_cache_store(transcript_path: Path, tokens: int) -> None:
    cache_path = _sdk_cache_path(transcript_path)
    try:
        mtime = transcript_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "tokens": tokens,
            "computed_at": time.time(),
            "transcript_mtime": mtime,
        }))
    except OSError as exc:
        print(f"{PREFIX} cache write failed: {exc}", file=sys.stderr)


def _measure_tokens(transcript_path: Path) -> int:
    """SDK path when ANTHROPIC_API_KEY is set and `anthropic` imports;
    otherwise proxy. Mirrors phase_token_meter.py priority order.

    SDK calls are rate-limited via a per-transcript file cache (TTL
    SDK_CACHE_TTL_SEC) to avoid ~200ms latency on every Stop event."""
    messages = _transcript_messages(transcript_path)
    if not messages:
        return 0
    if os.environ.get("ANTHROPIC_API_KEY"):
        cached = _sdk_cache_lookup(transcript_path)
        if cached is not None:
            return cached
        model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        sdk_tokens = _sdk_estimate(messages, model)
        if sdk_tokens is not None:
            _sdk_cache_store(transcript_path, sdk_tokens)
            return sdk_tokens
    return _proxy_estimate(messages)


def _all_worktree_roots(cwd: Path | None = None) -> list[Path]:
    """Return every checkout known to the current git repository (main +
    linked worktrees). Falls back to [cwd] when not in a git repo or git
    is missing.

    Why: a single Claude/Codex session may operate across multiple worktrees
    (e.g. parallel work-package agents in .git-worktrees/<change-id>/<pkg>/).
    Phase-boundary detection should be session-scoped, not cwd-scoped, so
    we glob handoffs from every checkout the repo knows about.
    """
    cwd = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=2, check=True,
            cwd=str(cwd),
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return [cwd]
    roots: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line.split(" ", 1)[1]))
    return roots or [cwd]


def _applied_handoff_id(change_dir: Path) -> str | None:
    """Return the ``last_handoff_id`` recorded in this change's
    ``loop-state.json``, or None when the state file is absent, malformed,
    or has no usable applied-handoff value.

    The orchestrator (e.g. autopilot's ``apply-outcome`` step) writes
    ``loop-state.json`` with ``last_handoff_id`` set to the repo-relative
    path of the handoff it just consumed. That is the authoritative "a phase
    just completed" signal. We read it defensively: any read/parse failure or
    a missing/null/empty value is treated as "no applied handoff" so the
    phase-boundary detector fails closed."""
    loop_state_path = change_dir / "loop-state.json"
    try:
        loop_state = json.loads(loop_state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None  # fail closed: no readable loop state = no boundary
    if not isinstance(loop_state, dict):
        return None
    last_handoff = loop_state.get("last_handoff_id")
    if not isinstance(last_handoff, str) or not last_handoff:
        return None  # missing / null / empty = no applied handoff
    return last_handoff


def _recent_phase_boundary() -> str | None:
    """Return the phase name (e.g. 'implementation') if a handoff JSON was
    written in the last PHASE_BOUNDARY_WINDOW_SEC seconds in ANY worktree
    of the current repo AND that handoff has been recorded as the change's
    most-recently-applied phase outcome. PhaseRecord write_both() persists to
    openspec/changes/<id>/handoffs/<phase>-<N>.json in the local-fallback
    path.

    A recent mtime alone is NOT a phase boundary: sub-agent writes, mtime
    touches (git checkout, IDE indexing), and sibling-worktree handoffs all
    produce fresh mtimes without a real phase transition. We gate on the
    change's ``loop-state.json.last_handoff_id`` so only handoffs the
    orchestrator has actually consumed count as boundaries."""
    cutoff = time.time() - PHASE_BOUNDARY_WINDOW_SEC
    newest_phase: str | None = None
    newest_mtime = 0.0
    seen: set[Path] = set()
    for root in _all_worktree_roots():
        for p in root.glob("openspec/changes/*/handoffs/*.json"):
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff or mtime <= newest_mtime:
                continue
            # Gate on last_handoff_id from the loop-state.json alongside this
            # handoff file. If the orchestrator has not yet consumed this
            # handoff (apply-outcome step), the recent mtime is from sub-agent
            # activity, an mtime touch, or a sibling worktree's write — not a
            # real boundary. Compare basename because last_handoff_id is stored
            # as a repo-relative path while p may resolve differently across
            # worktree roots; per-change handoff dirs namespace filenames.
            change_dir = p.parent.parent  # openspec/changes/<id>/
            last_handoff = _applied_handoff_id(change_dir)
            if last_handoff is None or not last_handoff.endswith(p.name):
                continue
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

    boundary = _recent_phase_boundary()
    if boundary:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Natural decomposition point reached: {boundary} handoff just "
            f"written. Run /compact now to consolidate context before the "
            f"next phase."
        )

    tokens = _measure_tokens(transcript)
    limit = _env_int("CLAUDE_CONTEXT_LIMIT", DEFAULT_CONTEXT_LIMIT)
    threshold = _env_int("CLAUDE_COMPACT_THRESHOLD_PCT", DEFAULT_THRESHOLD_PCT)
    pct = (tokens * 100) // max(limit, 1)

    if pct >= threshold:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Context window at ~{pct}% of {limit:,} tokens "
            f"(threshold {threshold}%, agent={_agent_id()}). "
            f"Run /compact now. Phase handoffs are persisted, so context "
            f"will be rehydrated by SessionStart after compaction."
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Hooks must never crash Claude Code; degrade silently.
        print(f"{PREFIX} unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)
