#!/usr/bin/env python3
"""Print current coordinator configuration on session start.

Surfaces the environment variables that control coordinator access so
you can immediately see which coordinator a new session is pointing at
(local vs. Railway vs. Cloudflare, which API key, which allowed hosts).

Wired up as a SessionStart hook for Claude Code and Codex via
``.claude/hooks.json`` and ``.codex/hooks.json``. Must be fast and
non-blocking: swallows all errors so session startup is never delayed.

Usage:
    python3 agent-coordinator/scripts/print_coordinator_env.py
"""

from __future__ import annotations

import os
import sys


def _get(name: str, default: str = "(unset)") -> str:
    value = os.environ.get(name, "").strip()
    return value if value else default


def _mask(value: str | None, keep: int = 4) -> str:
    """Mask secrets: show the first ``keep`` chars and the length."""
    if not value:
        return "(unset)"
    if len(value) <= keep:
        return "***"
    return f"{value[:keep]}… (masked, len={len(value)})"


def _apply_profile_best_effort() -> None:
    """Load the active deployment profile so env vars reflect what the
    coordinator code will see. Silently skipped if the coordinator package
    or pyyaml is unavailable (e.g. running outside the repo venv).
    """
    try:
        sys.path.insert(
            0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        from src.profile_loader import apply_profile  # type: ignore

        apply_profile()
    except Exception:
        # Profile loading is a nice-to-have; never block session start.
        pass


def main() -> int:
    _apply_profile_best_effort()

    lines = [
        "[coord-env] === Coordinator Configuration ===",
        f"[coord-env] Profile:        {_get('COORDINATOR_PROFILE', 'local')}",
        f"[coord-env] Transport:      {_get('COORDINATION_TRANSPORT', 'none')}",
        f"[coord-env] API URL:        {_get('COORDINATION_API_URL')}",
        f"[coord-env] Allowed hosts:  {_get('COORDINATION_ALLOWED_HOSTS', '(localhost only)')}",
        f"[coord-env] API key:        {_mask(os.environ.get('COORDINATION_API_KEY'))}",
        f"[coord-env] Agent ID:       {_get('AGENT_ID')}",
        f"[coord-env] Agent type:     {_get('AGENT_TYPE', 'claude_code')}",
        f"[coord-env] DB backend:     {_get('DB_BACKEND', 'postgres')}",
    ]
    for line in lines:
        print(line)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # SessionStart hooks must never block the session.
        sys.exit(0)
