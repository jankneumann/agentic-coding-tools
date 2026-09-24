"""Session identity and session-scoped handoff discovery for the compact hooks.

Shared by check_compact.py (Stop) and precompact_handoff.py (PreCompact).
Stdlib-only, like every other hook in this directory.

Two questions both hooks need answered the same way:

  1. **Who is this session?** The compact-pending flag must be keyed on a
     value both hooks can derive. Claude Code puts ``session_id`` in every
     hook payload and keeps it across ``/compact``, so it is the natural key.
     ``AGENT_ID`` is usually unset in local runs; keying on it alone collapsed
     every session onto one shared ``compact-pending-unknown.flag``.

  2. **Which handoffs belong to this session?** One repository hosts many
     concurrent sessions, each in its own worktree. Scanning every worktree
     let one session's applied handoff block a different session's Stop.
     A handoff counts only when it lives in a worktree this session has
     worked in (per the ``cwd`` recorded on each transcript row) AND its
     change id appears somewhere in this session's transcript.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

HANDOFF_GLOB = "openspec/changes/*/handoffs/*.json"

_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
# Matches a top-level-looking ``"cwd": "..."`` pair on a raw JSONL line. A cwd
# serialized inside a string field is escaped (``\"cwd\"``) and cannot match.
_CWD_FIELD = re.compile(r'"cwd"\s*:\s*("(?:[^"\\]|\\.)*")')


def session_key(payload: dict | None) -> str:
    """Filesystem-safe identity for this session.

    Precedence: hook-payload ``session_id`` → ``SESSION_ID`` env →
    ``AGENT_ID`` env → hash of ``transcript_path`` → ``"unknown"``."""
    payload = payload or {}
    for candidate in (
        payload.get("session_id"),
        os.environ.get("SESSION_ID"),
        os.environ.get("AGENT_ID"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return _UNSAFE_KEY_CHARS.sub("_", candidate.strip())[:128]
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str) and transcript:
        return "transcript-" + hashlib.sha1(transcript.encode()).hexdigest()[:16]
    return "unknown"


def flag_path(payload: dict | None) -> Path:
    return Path.home() / ".claude" / f"compact-pending-{session_key(payload)}.flag"


def all_worktree_roots(cwd: Path | None = None) -> list[Path]:
    """Every checkout known to the repository (main + linked worktrees).
    Falls back to [cwd] outside a git repo or when git is missing."""
    cwd = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=2, check=True,
            cwd=str(cwd),
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return [cwd]
    roots = [
        Path(line.split(" ", 1)[1])
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return roots or [cwd]


def owning_root(path: Path, roots: Iterable[Path]) -> Path | None:
    """The most specific root containing ``path``. Linked worktrees live
    inside the main checkout (``.git-worktrees/<id>``), so the longest
    matching root wins."""
    best: Path | None = None
    for root in roots:
        if (path == root or root in path.parents) and (
            best is None or len(root.parts) > len(best.parts)
        ):
            best = root
    return best


@dataclass
class SessionScope:
    """Where this session has worked and what it has mentioned."""

    cwds: set[Path] = field(default_factory=set)
    text: str = ""

    def roots(self, all_roots: Iterable[Path]) -> set[Path]:
        all_roots = list(all_roots)
        owned = (owning_root(cwd, all_roots) for cwd in self.cwds)
        return {root for root in owned if root is not None}

    def owns_handoff(self, handoff: Path, all_roots: Iterable[Path]) -> bool:
        """True when ``handoff`` (…/openspec/changes/<id>/handoffs/<f>.json)
        sits in one of this session's worktrees and its change id appears
        in this session's transcript."""
        all_roots = list(all_roots)
        root = owning_root(handoff, all_roots)
        if root is None or root not in self.roots(all_roots):
            return False
        change_id = handoff.parent.parent.name
        return bool(change_id) and change_id in self.text


def load_session_scope(payload: dict | None, fallback_cwd: Path | None = None) -> SessionScope:
    """Collect this session's working directories and transcript text.

    The payload ``cwd`` (or the hook process cwd) is always included, so a
    session with an unreadable transcript still scopes to its own checkout."""
    payload = payload or {}
    scope = SessionScope()
    payload_cwd = payload.get("cwd")
    scope.cwds.add(Path(payload_cwd) if isinstance(payload_cwd, str) and payload_cwd
                   else (fallback_cwd or Path.cwd()))

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return scope
    try:
        text = Path(transcript).read_text(errors="replace")
    except OSError:
        return scope
    scope.text = text
    for match in _CWD_FIELD.finditer(text):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, str) and value:
            scope.cwds.add(Path(value))
    return scope
