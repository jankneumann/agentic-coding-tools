#!/usr/bin/env python3
"""Deregister agent session on Claude Code session end.

This script is called by Claude Code's SessionEnd lifecycle hook.
It releases all held file locks and writes a final handoff document
for the next session to pick up.

Usage:
    python agent-coordinator/scripts/deregister_agent.py

Environment variables:
    SUPABASE_URL: Supabase project URL
    SUPABASE_SERVICE_KEY: Service role key
    AGENT_ID: Agent identifier
    SESSION_ID: Session identifier
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main() -> None:
    try:
        from src.locks import get_lock_service
        from src.handoffs import get_handoff_service
        from src.config import get_config
    except ImportError as e:
        print(f"[deregister_agent] Import error (coordination not installed): {e}", file=sys.stderr)
        return

    try:
        config = get_config()
    except ValueError:
        print("[deregister_agent] Coordination not configured (missing env vars)", file=sys.stderr)
        return

    agent_id = config.agent.agent_id

    # Release all locks held by this agent
    lock_service = get_lock_service()
    locks = await lock_service.check()
    released_count = 0
    for lock in locks:
        if lock.locked_by == agent_id:
            result = await lock_service.release(lock.file_path)
            if result.success:
                released_count += 1
                print(f"[deregister_agent] Released lock: {lock.file_path}")

    if released_count > 0:
        print(f"[deregister_agent] Released {released_count} lock(s)")
    else:
        print("[deregister_agent] No locks to release")

    # Write a final handoff document
    handoff_service = get_handoff_service()
    result = await handoff_service.write(
        summary=f"Session ended. Released {released_count} lock(s).",
    )

    if result.success:
        print(f"[deregister_agent] Final handoff written: {result.handoff_id}")
    else:
        print(f"[deregister_agent] Handoff write failed: {result.error}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
