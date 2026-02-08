#!/usr/bin/env python3
"""Register agent session on Claude Code session start.

This script is called by Claude Code's SessionStart lifecycle hook.
It registers the agent with the coordination system and loads
the most recent handoff document for context continuity.

Usage:
    python agent-coordinator/scripts/register_agent.py

Environment variables:
    SUPABASE_URL: Supabase project URL
    SUPABASE_SERVICE_KEY: Service role key
    AGENT_ID: Agent identifier (auto-generated if not set)
    AGENT_TYPE: Agent type (default: claude_code)
    SESSION_ID: Session identifier
    AGENT_CAPABILITIES: Comma-separated capabilities (optional)
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main() -> None:
    try:
        from src.config import get_config
        from src.discovery import get_discovery_service
        from src.handoffs import get_handoff_service
    except ImportError as e:
        print(f"[register_agent] Import error (coordination not installed): {e}", file=sys.stderr)
        return

    try:
        config = get_config()
    except ValueError:
        # Missing SUPABASE_URL or SUPABASE_SERVICE_KEY — coordination not configured
        print("[register_agent] Coordination not configured (missing env vars)", file=sys.stderr)
        return

    # Parse capabilities from environment
    capabilities_str = os.environ.get("AGENT_CAPABILITIES", "")
    capabilities = [c.strip() for c in capabilities_str.split(",") if c.strip()]

    # Register the agent session
    discovery = get_discovery_service()
    result = await discovery.register(capabilities=capabilities)

    if result.success:
        print(f"[register_agent] Registered session: {result.session_id}")
    else:
        print("[register_agent] Registration failed", file=sys.stderr)
        return

    # Load most recent handoff for context continuity
    handoff_service = get_handoff_service()
    handoff_result = await handoff_service.read(
        agent_name=config.agent.agent_id,
        limit=1,
    )

    if handoff_result.handoffs:
        h = handoff_result.handoffs[0]
        print(f"[register_agent] Previous handoff loaded: {h.summary[:80]}")
        if h.next_steps:
            print("[register_agent] Next steps from previous session:")
            for step in h.next_steps:
                print(f"  - {step}")
    else:
        print("[register_agent] No previous handoff found (first session)")


if __name__ == "__main__":
    asyncio.run(main())
