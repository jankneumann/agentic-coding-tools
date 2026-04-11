# Session Bootstrap

Infrastructure skill that provides cloud environment bootstrap and coordinator lifecycle hooks.

## Purpose

Cloud coding environments (Claude Code web, Codex) are ephemeral — the repo is cloned fresh each session. This skill provides:

1. **`bootstrap-cloud.sh`** — Idempotent environment setup (Python, venvs, OpenSpec, git config)
2. **Coordinator hooks** — Session registration, status reporting, and deregistration via the coordinator HTTP API

## Shipped Scripts

| Script | Hook Event | Purpose |
|--------|-----------|---------|
| `scripts/bootstrap-cloud.sh` | SessionStart | Install Python, venvs, OpenSpec CLI, git config |
| `scripts/hooks/print_coordinator_env.py` | SessionStart | Print active coordinator configuration |
| `scripts/hooks/register_agent.py` | SessionStart | Register session; load previous handoff |
| `scripts/hooks/report_status.py` | Stop / SubagentStop | Report phase completion to coordinator |
| `scripts/hooks/deregister_agent.py` | SessionEnd | Deregister session; write final handoff |

## Hook Wiring

Target repos wire these scripts in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh", "timeout": 300 },
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/print_coordinator_env.py" },
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/register_agent.py" }
      ]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/report_status.py" }
      ]
    }],
    "SubagentStop": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/report_status.py --subagent" }
      ]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/hooks/deregister_agent.py" }
      ]
    }]
  }
}
```

## Environment Variables

The coordinator hook scripts read these from the environment:

| Variable | Required | Description |
|----------|----------|-------------|
| `COORDINATION_API_URL` | No | Coordinator HTTP API URL (hooks skip gracefully if unset) |
| `COORDINATION_API_KEY` | No | API key for `X-API-Key` header |
| `AGENT_ID` | No | Agent identifier (default: "unknown") |
| `AGENT_TYPE` | No | Agent type (default: "claude_code") |

All hook scripts are **stdlib-only** (no third-party dependencies) and **never block sessions** (all exceptions swallowed, always exit 0).

## Canonical Source

The hook scripts here are the canonical copies for distribution via `install.sh`. The `agent-coordinator/scripts/` directory contains equivalent scripts that reference the coordinator's own venv and paths — those are for local development and the Makefile's user-scope hook targets.
