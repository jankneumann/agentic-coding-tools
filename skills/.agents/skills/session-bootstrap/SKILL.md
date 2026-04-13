---
name: session-bootstrap
description: "Cloud environment bootstrap (setup script + verify hook) and coordinator lifecycle hooks"
category: Infrastructure
tags: [bootstrap, cloud, setup, hooks, coordinator, session]
---

# Session Bootstrap

Infrastructure skill that provides cloud environment setup and coordinator lifecycle hooks.

## Architecture

Cloud environments are ephemeral. Two scripts handle setup at different lifecycle points:

| Script | When | Runs on resume? | What it does |
|--------|------|-----------------|-------------|
| `setup-cloud.sh` | Setup Script (cloud UI) | No (new sessions only) | Heavy installs: `uv sync`, `npm install`, skills, git config |
| `bootstrap-cloud.sh` | SessionStart hook | Yes (every start/resume) | Fast verify: file-existence checks, repair only if missing |

On a resumed session, `bootstrap-cloud.sh` takes <1 second — it only checks that venvs, openspec, and skills still exist. If something was deleted mid-session, it repairs it.

### Claude Code Web

- **Setup Script**: Paste `setup-cloud.sh` into Environment Settings > Setup Script
- **SessionStart hook**: Wired in `.claude/settings.json` (committed to repo)
- Pre-installed: Python 3.x, uv, pip, npm, pnpm, docker, git, PostgreSQL 16, Redis 7.0

### Codex

- **Setup Script**: Configure in environment settings (cached up to 12h)
- **Maintenance Script**: Use `bootstrap-cloud.sh` as the maintenance script for resume
- Pre-installed: Common languages and tools via `codex-universal` image

## Shipped Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup-cloud.sh` | Full install for cloud Setup Script field |
| `scripts/bootstrap-cloud.sh` | Fast verify + repair SessionStart hook |
| `scripts/bootstrap-cloud.sh --check` | Dry-run diagnostics |
| `scripts/hooks/print_coordinator_env.py` | Print coordinator config (SessionStart) |
| `scripts/hooks/register_agent.py` | Register session, load handoff (SessionStart) |
| `scripts/hooks/report_status.py` | Report phase completion (Stop/SubagentStop) |
| `scripts/hooks/deregister_agent.py` | Deregister session, write handoff (SessionEnd) |

## Wiring for Target Repos

### 1. Cloud Setup Script (Environment Settings UI)

The Setup Script field is a text area in the cloud UI (not committed to git).
Paste this one-liner — it calls the versioned script from the cloned repo:

```bash
bash "$(pwd)/.claude/skills/session-bootstrap/scripts/setup-cloud.sh"
```

Note: `$(pwd)` not `$CLAUDE_PROJECT_DIR` — the Setup Script runs before Claude Code
launches, so `CLAUDE_PROJECT_DIR` isn't set yet. The repo is already cloned at `$(pwd)`.

### 2. `.claude/settings.json` — Hooks

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [
        { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh", "timeout": 30 },
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

### 3. Environment Variables (cloud UI)

```
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=<your-api-key>
AGENT_ID=claude-web-1
AGENT_TYPE=claude_code
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COORDINATION_API_URL` | No | Coordinator HTTP API URL (hooks skip gracefully if unset) |
| `COORDINATION_API_KEY` | No | API key for `X-API-Key` header |
| `AGENT_ID` | No | Agent identifier (default: "unknown") |
| `AGENT_TYPE` | No | Agent type (default: "claude_code") |
| `CLAUDE_CODE_REMOTE` | Auto | Set to `true` by Claude Code web — can be used to skip local execution |
| `CLAUDE_ENV_FILE` | Auto | File path for persisting env vars across Bash calls |

All hook scripts are **stdlib-only** (no third-party dependencies) and **never block sessions** (all exceptions swallowed, always exit 0).

## Canonical Source

The hook scripts here are the canonical copies for distribution via `install.sh`. The `agent-coordinator/scripts/` directory contains equivalent scripts for local development and the Makefile's user-scope hook targets.
