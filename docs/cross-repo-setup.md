# Cross-Repo Setup Guide

How to set up a new repository to use the skills, scripts, and MCP servers
from `agentic-coding-tools`.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- `agentic-coding-tools` cloned locally (skills source)

## Quick Start

```bash
# From the agentic-coding-tools directory:
cd ~/Coding/agentic-coding-tools

# Install skills into the target repo
bash skills/install.sh \
  --target ~/Coding/<your-repo> \
  --mode rsync --force \
  --deps none --python-tools none
```

This copies all skills (SKILL.md + scripts/) into `<your-repo>/.claude/skills/`
and `<your-repo>/.agents/skills/`.

## Step-by-Step Setup

### 1. Install Skills

```bash
cd ~/Coding/agentic-coding-tools

bash skills/install.sh \
  --target ~/Coding/<your-repo> \
  --mode rsync --force \
  --deps none --python-tools none
```

**Flags explained:**

| Flag | Purpose |
|------|---------|
| `--target <path>` | Base directory of the target repo |
| `--mode rsync` | Copy files (not symlinks — works across git repos) |
| `--force` | Replace existing files at destination |
| `--deps none` | Skip per-skill dependency hooks (target repo manages its own deps) |
| `--python-tools none` | Skip pytest/mypy/ruff bootstrap (target repo has its own venv) |

**Re-syncing after skill updates:**

Run the same command again. `--mode rsync --force` is idempotent.

### 2. Create Python Environment

If the target repo has a `pyproject.toml`:

```bash
cd ~/Coding/<your-repo>
uv sync --all-extras
```

If not, create a minimal one:

```bash
cd ~/Coding/<your-repo>
uv init
uv sync
```

### 3. Create `.claude/settings.json`

Minimal template for a repo using cloud coordination (no local Docker):

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "WebFetch(domain:localhost)",
      "WebFetch(domain:*.railway.app)",
      "WebFetch(domain:*.rotkohl.ai)",
      "WebFetch(domain:api.github.com)",
      "WebFetch(domain:raw.githubusercontent.com)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(git reset --hard *)",
      "Bash(git clean *)",
      "Read(~/.aws/**)",
      "Read(**/.env.*)"
    ]
  },
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/bootstrap-cloud.sh",
        "timeout": 300
      }]
    }]
  }
}
```

Add coordinator lifecycle hooks if you want session registration/handoff
(copy from `session-bootstrap/SKILL.md` § Hooks).

### 4. Create Bootstrap Script (Optional)

For cloud sessions that need environment verification on start/resume,
create `scripts/bootstrap-cloud.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log() { echo "[bootstrap] $*" >&2; }

# Verify venv
if [[ ! -f "$PROJECT_DIR/.venv/bin/activate" ]]; then
    log "Creating venv..."
    cd "$PROJECT_DIR" && uv sync --all-extras
fi

# Verify skills
if [[ ! -d "$PROJECT_DIR/.claude/skills" ]]; then
    log "Skills missing — run install.sh from agentic-coding-tools"
fi

log "Bootstrap complete"
```

### 5. Commit the Installed Skills

```bash
cd ~/Coding/<your-repo>
git add .claude/skills/ .agents/skills/ .claude/settings.json
git commit -m "chore: install agentic-coding-tools skills"
```

Skills are committed as copies (not symlinks) so the repo is self-contained
and cloud environments work without access to `agentic-coding-tools`.

## MCP Server Access

### How MCP Scoping Works

Claude Code resolves MCP servers from three sources (in priority order):

| Scope | Config file | Visibility |
|-------|-------------|------------|
| **User** | `~/.claude.json` → `mcpServers` | Every repo you open |
| **Project (shared)** | `<repo>/.mcp.json` | This repo (committed, shared with team) |
| **Project (local)** | `<repo>/.claude/settings.json` → `mcpServers` | This repo (local only) |

### Choosing the Right Scope

| Scenario | Recommended scope | Why |
|----------|-------------------|-----|
| Server used from multiple repos | **User** (`~/.claude.json`) | Available everywhere |
| Server specific to one repo | **Project** (`.claude/settings.json`) | Stays with the project |
| Server shared with team/CI | **Project shared** (`.mcp.json`) | Committed to git |

For cross-repo access, register servers at **user scope** with absolute paths.

### Available MCP Servers

| Server | What it provides | Local transport | Cloud transport |
|--------|-----------------|-----------------|-----------------|
| **coordination** | Agent coordination: locks, work queue, handoffs, discovery | stdio → direct Postgres | stdio → HTTP proxy via `COORDINATION_API_URL` |
| **newsletter-aggregator** | Content tools: ingest, summarize, digest, search | stdio via `.venv/bin/aca-mcp` | SSE via Railway endpoint |

### Switching Between Local and Cloud

Use the profile switcher to toggle all MCP servers between local and cloud:

```bash
# Check current profile
scripts/mcp-profile.sh status

# Switch all servers to cloud
scripts/mcp-profile.sh switch cloud

# Switch all servers to local
scripts/mcp-profile.sh switch local

# Switch a single server
scripts/mcp-profile.sh switch cloud coord
scripts/mcp-profile.sh switch local aca

# See available profiles and servers
scripts/mcp-profile.sh list
```

Restart Claude Code after switching for changes to take effect.

### Profile Details

#### Coordination Server

The coordination MCP server always uses stdio transport — the switching
happens *inside* the server, which auto-detects whether to use direct
Postgres or HTTP proxy:

| Profile | Env vars set | Internal behavior |
|---------|-------------|-------------------|
| **local** | `POSTGRES_DSN` | Direct DB queries via asyncpg |
| **cloud** | `COORDINATION_API_URL`, `COORDINATION_API_KEY` | HTTP proxy to Railway API |

#### Newsletter-Aggregator Server

The newsletter-aggregator uses FastMCP, which supports multiple transports.
The profile switcher changes the registration type:

| Profile | Transport | Config |
|---------|-----------|--------|
| **local** | stdio | Runs `.venv/bin/aca-mcp` from the local clone |
| **cloud** | SSE | Connects to Railway endpoint with `X-Admin-Key` auth |

### Environment Variables for Cloud Profiles

Set these before switching to cloud (in your shell profile or `.env`):

```bash
# Coordination (required for cloud)
export COORDINATION_API_URL=https://coord.rotkohl.ai
export COORDINATION_API_KEY=<your-key>

# Newsletter-aggregator (required for cloud)
export ACA_MCP_URL=https://<your-railway-domain>/mcp/sse
export ACA_MCP_ADMIN_KEY=<your-admin-key>
```

### Manual Registration (Without the Switcher)

If you prefer manual control:

```bash
# Coordination — local
claude mcp add-json --scope user coordination '{
  "type": "stdio",
  "command": "<agentic-coding-tools>/agent-coordinator/.venv/bin/python",
  "args": ["<agentic-coding-tools>/agent-coordinator/run_mcp.py"],
  "env": {
    "DB_BACKEND": "postgres",
    "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:54322/postgres"
  }
}'

# Coordination — cloud
claude mcp add-json --scope user coordination '{
  "type": "stdio",
  "command": "<agentic-coding-tools>/agent-coordinator/.venv/bin/python",
  "args": ["<agentic-coding-tools>/agent-coordinator/run_mcp.py"],
  "env": {
    "COORDINATION_API_URL": "https://coord.rotkohl.ai",
    "COORDINATION_API_KEY": "<your-key>"
  }
}'

# Newsletter-aggregator — local
claude mcp add-json --scope user newsletter-aggregator '{
  "type": "stdio",
  "command": "<agentic-newsletter-aggregator>/.venv/bin/aca-mcp",
  "args": []
}'

# Newsletter-aggregator — cloud
claude mcp add-json --scope user newsletter-aggregator '{
  "type": "sse",
  "url": "https://<railway-domain>/mcp/sse",
  "headers": { "X-Admin-Key": "<your-admin-key>" }
}'
```

### HTTP Transport for Cloud Sessions

In cloud coding sessions (Claude Code web, Codex), stdio MCP servers that
depend on another repo's venv won't work — the other repo isn't cloned.
Options:

1. **Run the MCP server as an HTTP service** (e.g., on Railway) and connect
   via SSE/streamable-http transport
2. **Bundle the MCP server** as a standalone package installable via pip/npm
3. **Use the coordination HTTP bridge** (`coordination-bridge` skill) which
   auto-detects MCP vs HTTP and falls back accordingly

## Cloud vs CLI Differences

| Concern | CLI (local) | Cloud (Claude Code web / Codex) |
|---------|-------------|----------------------------------|
| Skills source | `install.sh --target` from local clone | Committed copies in `.claude/skills/` |
| Python venv | `uv sync` once, persists | `setup-cloud.sh` recreates each session |
| MCP servers | User-scope stdio with absolute paths | HTTP transport or bundled in repo |
| Coordinator | User-scope MCP (stdio → local or Railway) | HTTP bridge (`COORDINATION_API_URL`) |
| Docker/DB | Optional (`--skip-docker`) | Not available; use Railway/cloud DB |

## Updating Skills

When skills are updated in `agentic-coding-tools`:

```bash
# Re-sync to target repo
cd ~/Coding/agentic-coding-tools
bash skills/install.sh \
  --target ~/Coding/<your-repo> \
  --mode rsync --force \
  --deps none --python-tools none

# Commit the updates in the target repo
cd ~/Coding/<your-repo>
git add .claude/skills/ .agents/skills/
git commit -m "chore: sync skills from agentic-coding-tools"
```

## Adopting Langfuse in another repo

Langfuse is the team's default LLM observability platform. The `langfuse` skill bundles three integration mechanisms behind one front door: skill knowledge, the CLI (`npx langfuse-cli`), and the MCP server (`mcp__langfuse__*` for prompt management).

### Two-command setup

```bash
# 1. Sync the skill from agentic-coding-tools (along with all other skills)
cd ~/Coding/agentic-coding-tools
bash skills/install.sh --target ~/Coding/<your-repo> --mode rsync --force \
  --deps none --python-tools none

# 2. Register the Langfuse MCP server in the target repo
cd ~/Coding/<your-repo>
LANGFUSE_PUBLIC_KEY=pk-lf-... \
LANGFUSE_SECRET_KEY=sk-lf-... \
  bash .claude/skills/langfuse/scripts/install-mcp.sh
```

Then export `LANGFUSE_BASIC_AUTH` from your shell profile so `.mcp.json` can interpolate it:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com  # or regional / self-hosted variant
export LANGFUSE_BASIC_AUTH=$(printf '%s:%s' \
  "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)
```

### Optional: lock to read-only

Pass `--lock-read-only` to add deny rules for the three write tools (`createTextPrompt`, `createChatPrompt`, `updatePromptLabels`) into `.claude/settings.json`. Useful for shared repos where prompt versioning goes through a release process.

### Optional: stream session transcripts to Langfuse

To make Claude Code session transcripts appear as Langfuse traces alongside server-side spans, wire `langfuse_hook.py` (or your project's equivalent) into the `Stop` matcher in `.claude/settings.json`. See `skills/langfuse/references/stop-hook.md` for both patterns (project venv vs `uv run`).

### Per-region URLs

| Region | MCP URL |
|---|---|
| EU cloud | `https://cloud.langfuse.com/api/public/mcp` |
| US cloud | `https://us.cloud.langfuse.com/api/public/mcp` |
| Japan | `https://jp.cloud.langfuse.com/api/public/mcp` |
| HIPAA | `https://hipaa.cloud.langfuse.com/api/public/mcp` |
| Self-hosted | `<your-langfuse-host>/api/public/mcp` |

Pass `--host us|jp|hipaa` (or `--host self-hosted --url <full-url>`) to `install-mcp.sh` for non-EU deployments.

## Reference

- [`skills/install.sh --help`](../skills/install.sh) — Full flag reference
- [`scripts/setup-cli.sh`](../scripts/setup-cli.sh) — One-time setup for agentic-coding-tools itself
- [`scripts/mcp-profile.sh`](../scripts/mcp-profile.sh) — MCP profile switcher (local ↔ cloud)
- [`session-bootstrap/SKILL.md`](../skills/session-bootstrap/SKILL.md) — Cloud hooks and wiring
- [Parallel Agentic Development](parallel-agentic-development.md) — Full parallel execution reference
