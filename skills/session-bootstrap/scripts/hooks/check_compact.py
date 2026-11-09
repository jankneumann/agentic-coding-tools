#!/usr/bin/env python3
"""Stop hook: request state capture + /compact at sync points or a hard limit.

Fires after every assistant turn (Stop lifecycle). The context measured is
the live window: only transcript rows after the last ``compact_boundary``
count, because the transcript file keeps every pre-compaction message. Two
trigger paths, both relative to CLAUDE_CONTEXT_LIMIT (default 1_000_000):

  1. **Sync point, near the limit** — context >= CLAUDE_COMPACT_SYNC_PCT
     (default 15%, ~150k) AND this turn reached a natural sync point, where
     the work is already persisted so compaction loses least:
       * a PhaseRecord handoff written under openspec/changes/<id>/handoffs/
         in the last PHASE_BOUNDARY_WINDOW_SEC seconds, applied by the
         orchestrator, and owned by THIS session (see session_scope.py); or
       * the turn pushed (``git push``), merged or opened a pull request.
  2. **Hard limit, anywhere** — context >= CLAUDE_COMPACT_THRESHOLD_PCT
     (default 20%, ~200k), a backstop that keeps every turn below the
     long-context price step even when no sync point comes.

When either trips, the hook emits ``{"decision": "block", "reason": "..."}``
to stdout. Claude Code interprets this as "do not yield to the user; re-prompt
the model with this reason", so the agent captures state on its next turn.
A hook cannot start the compaction itself: Claude Code compacts at the
``autoCompactWindow`` set in .claude/settings.json (200k), or on a typed
/compact. The sync threshold sits below that window so state is captured at
a natural point before the automatic compaction lands mid-task.

Token estimation strategy (see phase_token_meter.py for prior art, decision D9):

  * **SDK path** — when ANTHROPIC_API_KEY is set AND the ``anthropic`` package
    imports cleanly, call ``client.messages.count_tokens(...)`` for an
    authoritative count. Adds ~200ms latency per Stop event.
  * **Proxy fallback** — sum char-lengths of transcript message content,
    divide by 4. Tolerable ±20% drift per D9.

A per-session flag file (``~/.claude/compact-pending-<session-key>.flag``)
prevents re-blocking on the next Stop after a /compact request has been issued.
The PreCompact hook (precompact_handoff.py) derives the same key from its own
payload and clears the flag.

Hook input (stdin JSON, per Claude Code spec):
    {"session_id": "...", "transcript_path": "...", "cwd": "...",
     "hook_event_name": "Stop"}
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_scope  # noqa: E402

PREFIX = "[check_compact]"
DEFAULT_THRESHOLD_PCT = 20
DEFAULT_SYNC_PCT = 15
DEFAULT_CONTEXT_LIMIT = 1_000_000
PHASE_BOUNDARY_WINDOW_SEC = 300
CHAR_PER_TOKEN = 4
SDK_CACHE_TTL_SEC = 30


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
    shape (role + content); we just collect them in order.

    The transcript keeps every message from before a compaction; a
    ``compact_boundary`` system row marks where the live window restarts, so
    collection restarts there too."""
    messages: list[dict[str, Any]] = []
    if not transcript_path or not transcript_path.exists():
        return messages
    with transcript_path.open() as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("subtype") == "compact_boundary":
                messages = []
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


def _boundary_count(transcript_path: Path) -> int:
    """How many compactions the transcript records (``compact_boundary`` rows)."""
    try:
        with transcript_path.open() as f:
            return sum(1 for line in f if '"compact_boundary"' in line)
    except OSError:
        return 0


def _sdk_cache_lookup(transcript_path: Path) -> int | None:
    """Return cached token count when:
      - the transcript hasn't changed since last measurement (exact hit), OR
      - the cache is fresh within SDK_CACHE_TTL_SEC (rate-limit hit).
    Otherwise return None and force a fresh SDK call. A compaction since the
    count was taken always invalidates it: the live window it measured is gone."""
    cache_path = _sdk_cache_path(transcript_path)
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    cached_tokens = cache.get("tokens")
    if not isinstance(cached_tokens, int):
        return None
    if cache.get("boundaries") != _boundary_count(transcript_path):
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
            "boundaries": _boundary_count(transcript_path),
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


def _all_worktree_roots() -> list[Path]:
    return session_scope.all_worktree_roots()


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


def _recent_phase_boundary(payload: dict) -> str | None:
    """Return the phase name (e.g. 'implementation') if a handoff JSON was
    written in the last PHASE_BOUNDARY_WINDOW_SEC seconds, has been recorded
    as its change's most-recently-applied phase outcome, AND belongs to the
    session described by ``payload``. PhaseRecord write_both() persists to
    openspec/changes/<id>/handoffs/<phase>-<N>.json in the local-fallback
    path.

    A recent mtime alone is NOT a phase boundary: sub-agent writes, mtime
    touches (git checkout, IDE indexing), and sibling-worktree handoffs all
    produce fresh mtimes without a real phase transition. We gate on the
    change's ``loop-state.json.last_handoff_id`` so only handoffs the
    orchestrator has actually consumed count as boundaries.

    An applied handoff is still not OUR boundary when another session wrote
    it: every concurrent session shares the repository's worktree list. The
    session-ownership check (session_scope.SessionScope.owns_handoff) runs
    last, so the transcript is only read when an applied candidate exists."""
    cutoff = time.time() - PHASE_BOUNDARY_WINDOW_SEC
    newest_phase: str | None = None
    newest_mtime = 0.0
    seen: set[Path] = set()
    roots = _all_worktree_roots()
    scope: session_scope.SessionScope | None = None
    for root in roots:
        for p in root.glob(session_scope.HANDOFF_GLOB):
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
            if scope is None:
                scope = session_scope.load_session_scope(payload)
            if not scope.owns_handoff(p, roots):
                continue  # another session's applied handoff
            newest_mtime = mtime
            newest_phase = p.stem.rsplit("-", 1)[0]
    return newest_phase


def _is_prompt(msg: dict[str, Any]) -> bool:
    """A user message that starts a turn (not a tool result)."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _turn_sync_action(messages: list[dict[str, Any]]) -> str | None:
    """The sync action the current turn performed, or None: the work left
    this session (pushed, merged, or a PR opened), so a compaction after it
    loses the least."""
    start = max((i for i, m in enumerate(messages) if _is_prompt(m)), default=-1)
    found: str | None = None
    for msg in messages[start + 1:]:
        if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name", ""))
            command = (block.get("input") or {}).get("command", "")
            if name == "Bash" and isinstance(command, str) and "git push" in command:
                found = "git push"
            elif name.endswith("merge_pull_request"):
                found = "pull request merge"
            elif name.endswith("create_pull_request"):
                found = "pull request opened"
    return found


# Neither the model nor a hook can start a compaction: Claude Code compacts on
# its own at the configured auto-compact window (``autoCompactWindow`` in
# .claude/settings.json), or when a person types /compact. What this hook can
# do is make sure the state is captured at a sync point before that happens.
_CAPTURE = (
    "Capture state now: commit and push anything a fresh context needs "
    "(checkpoint/loop state, roadmap learnings, open decisions and next steps). "
    "Auto-compaction at the configured window follows; if a person is present, "
    "say they can run /compact now."
)


def _block(reason: str) -> None:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


def main() -> int:
    payload = _read_hook_input()
    flag = session_scope.flag_path(payload)
    if flag.exists():
        return 0  # /compact already requested; PreCompact will clear the flag

    transcript = Path(payload.get("transcript_path", ""))

    tokens = _measure_tokens(transcript)
    limit = _env_int("CLAUDE_CONTEXT_LIMIT", DEFAULT_CONTEXT_LIMIT)
    threshold = _env_int("CLAUDE_COMPACT_THRESHOLD_PCT", DEFAULT_THRESHOLD_PCT)
    sync_pct = _env_int("CLAUDE_COMPACT_SYNC_PCT", DEFAULT_SYNC_PCT)
    pct = (tokens * 100) // max(limit, 1)
    where = f"~{pct}% of {limit:,} tokens since the last compaction"

    if pct >= threshold:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Context window at {where} (hard limit {threshold}%, "
            f"session={session_scope.session_key(payload)}). {_CAPTURE} Phase "
            f"handoffs are persisted, so SessionStart rehydrates context."
        )

    if pct < sync_pct:
        return 0
    sync = _recent_phase_boundary(payload)
    sync = f"{sync} handoff applied" if sync else _turn_sync_action(
        _transcript_messages(transcript)
    )
    if sync:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        _block(
            f"Natural sync point reached ({sync}) with the context window at "
            f"{where} (sync threshold {sync_pct}%). {_CAPTURE}"
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Hooks must never crash Claude Code; degrade silently.
        print(f"{PREFIX} unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)
