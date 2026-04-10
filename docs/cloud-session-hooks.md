# Cloud Session Hooks & Network Configuration

How Claude Code lifecycle hooks, coordinator connectivity, and network
allowlists work in cloud/remote sessions (Claude Code web, `--remote`, and
container-based environments).

## How Hooks Apply to Cloud Sessions

`.claude/hooks.json` is a **project-level** file checked into the repository.
When Claude Code starts a cloud/remote session it clones the repo first, then
loads project settings — including hooks — from the working tree. No extra
setup is needed; hooks are active in every environment that checks out this
repo.

The same applies to `.claude/settings.json` (permissions, deny lists, output
style) and `.claude/skills/` (installed skill copies).

### Hook Script Behavior

All hook scripts use Python's stdlib `urllib.request` for HTTP calls — no
third-party packages required. This ensures they work in any Python
environment, including cloud containers where only the system Python is
available.

| Hook Event | Script | What It Does | Requires Auth |
|------------|--------|-------------|---------------|
| `SessionStart` | `register_agent.py` | Reports session start, loads previous handoff | Yes (`X-API-Key`) |
| `Stop` / `SubagentStop` | `report_status.py` | Reports phase transitions, heartbeat | No |
| `SessionEnd` | `deregister_agent.py` | Writes final handoff, reports session end | Yes (`X-API-Key`) |

All scripts communicate with the coordinator via its HTTP API. They resolve
the coordinator URL from environment variables (checked in order):
`COORDINATION_API_URL` → `COORDINATOR_URL` → `COORDINATOR_HTTP_URL`.

If no coordinator URL is configured, scripts skip silently without blocking
Claude Code.

### Lock Cleanup

The `deregister_agent.py` script does **not** release locks on session end.
The HTTP API has no endpoint to list locks by agent (only per-file lookup).
Instead, locks expire automatically via their TTL (default 120 minutes).

If immediate lock release is needed, skills should release locks explicitly
before session end using the coordination bridge.

### Agent Identity

The `AGENT_ID` environment variable controls which agent identity is used for
handoff read/write operations. If the API key maps to a specific agent via
`COORDINATION_API_KEY_IDENTITIES` on the server, the `agent_id` in requests
must match the key's mapped identity (or the server resolves it from the key
automatically).

For cloud sessions, set `AGENT_ID` to match the key's identity mapping (e.g.,
`claude-remote`). Without it, handoff endpoints may return 403.

## Tool-Call Tracking (Langfuse)

There are **no** `PreToolUse` / `PostToolUse` hooks configured. Tool-call
tracking is available via `langfuse_hook.py`, which does **post-hoc transcript
analysis** on `Stop` events.

### How It Works

1. Claude Code writes session transcripts to `~/.claude/projects/<hash>/<session>.jsonl`
2. On each `Stop` event, `langfuse_hook.py` reads new transcript lines
3. It extracts conversation turns and tool invocations into Langfuse traces
4. State is tracked incrementally (only new messages since last run)

### Cloud Compatibility

| Requirement | Status |
|-------------|--------|
| Transcript files exist | Yes (`~/.claude/projects/` is populated in cloud) |
| `langfuse` package available | No (not in system Python) |
| `uv` available for dynamic install | Yes |
| Currently in hooks.json | **No** (optional addition) |

### Enabling Langfuse in Cloud

To enable, add the Langfuse hook to `.claude/hooks.json` using `uv run` for
dependency resolution:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 agent-coordinator/scripts/report_status.py"
      },
      {
        "type": "command",
        "command": "uv run --with 'langfuse>=3.0,<4.0' agent-coordinator/scripts/langfuse_hook.py"
      }
    ]
  }
}
```

Required environment variables:
- `LANGFUSE_ENABLED=true`
- `LANGFUSE_PUBLIC_KEY=pk-lf-...`
- `LANGFUSE_SECRET_KEY=sk-lf-...`
- `LANGFUSE_HOST=https://cloud.langfuse.com` (or self-hosted URL)

The Langfuse host must also be in the platform egress allowlist.

## Network Configuration

Cloud sessions run inside containers with egress restrictions. Two separate
allowlists must be configured for coordinator access to work.

### 1. Platform Egress Allowlist (Container Level)

Claude Code cloud sessions use an egress proxy that only allows traffic to
pre-approved hosts. The coordinator domain must be in this list or HTTP
requests will be blocked at the network level.

**How to configure**: Set `COORDINATION_ALLOWED_HOSTS` in the container
environment (or the platform-specific egress configuration). The proxy JWT
token's `allowed_hosts` field must include the coordinator domain.

**Current allowlist** (coordinator-relevant entries):

| Host Pattern | Purpose |
|-------------|---------|
| `*.rotkohl.ai` | Coordinator API (`coord.rotkohl.ai`) |
| `*.railway.app` | Railway services (if coordinator is on Railway directly) |
| `api.github.com` | GitHub API (for MCP tools, PR operations) |
| `github.com` | Git operations |

To add a new host, update the egress allowlist in the Claude Code cloud
configuration for your organization.

### 2. SSRF Allowlist (Application Level)

The `coordination_bridge.py` script has its own SSRF protection that validates
coordinator URLs before making requests. This prevents scripts from being
tricked into hitting internal endpoints.

**Environment variable**: `COORDINATION_ALLOWED_HOSTS`

**Format**: Comma-separated hostnames (no scheme, no port)

```bash
# Exact match
COORDINATION_ALLOWED_HOSTS=coord.rotkohl.ai

# Wildcard (matches subdomains, not bare domain)
COORDINATION_ALLOWED_HOSTS=*.rotkohl.ai

# Multiple hosts
COORDINATION_ALLOWED_HOSTS=coord.rotkohl.ai,your-app.railway.app
```

**Built-in allowlist** (always permitted): `localhost`, `127.0.0.1`, `::1`

### 3. Settings Deny List (Claude Code Level)

`.claude/settings.json` can deny specific tool patterns. The current deny
list includes `Bash(curl *)`, which prevents direct `curl` commands but does
**not** affect Python's `urllib` (used by all coordinator hook scripts).

```json
{
  "permissions": {
    "deny": [
      "Bash(curl *)"
    ]
  }
}
```

If you need `curl` for debugging, move the pattern to `ask` instead of `deny`:

```json
"ask": ["Bash(curl *coord.rotkohl.ai*)"]
```

## Required Environment Variables

These must be set in the cloud session environment for coordinator access:

| Variable | Required | Example | Used By |
|----------|----------|---------|---------|
| `COORDINATION_API_URL` | Yes | `https://coord.rotkohl.ai` | All hook scripts, `check_coordinator.py`, `coordination_bridge.py` |
| `COORDINATION_API_KEY` | Yes | `91a8925e...` | HTTP `X-API-Key` header (register, deregister, handoffs) |
| `COORDINATION_ALLOWED_HOSTS` | Yes | `coord.rotkohl.ai` | SSRF allowlist in bridge |
| `AGENT_ID` | Recommended | `claude-remote` | Agent identity — must match API key identity mapping |
| `AGENT_TYPE` | Optional | `claude_code` | Agent type label (default: `claude_code`) |

**Note**: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are **not needed** for
cloud sessions. All hook scripts communicate via the coordinator HTTP API.

## Maintenance: Updating Allowlists

When the coordinator infrastructure changes (new domain, new services), update
these locations:

### Checklist

1. **Platform egress** — Update the organization's cloud egress configuration
   to include new host patterns. This is external to the repo.

2. **`.claude/settings.json`** — Update `WebFetch` domain allows if the new
   host needs to be fetched by Claude directly:
   ```json
   "allow": [
     "WebFetch(domain:*.rotkohl.ai)",
     "WebFetch(domain:*.newdomain.com)"
   ]
   ```

3. **Cloud deployment docs** — Update `docs/cloud-deployment.md` section 8
   with any new environment variable requirements.

4. **`.env.cloud` template** — If using `setup_cloud.py`, the `--domain` flag
   auto-populates `COORDINATION_ALLOWED_HOSTS`. Update for new domains:
   ```bash
   python3 agent-coordinator/scripts/setup_cloud.py --domain new.domain.com
   ```

5. **CI/CD secrets** — Update GitHub Actions secrets or Railway service
   variables if API keys or URLs change.

### Adding a New Coordinator Domain

```bash
# 1. Verify connectivity
COORDINATION_API_URL=https://new.domain.com \
  python3 skills/coordination-bridge/scripts/check_coordinator.py --json

# 2. Update SSRF allowlist in agent environment
export COORDINATION_ALLOWED_HOSTS="new.domain.com"

# 3. Update .claude/settings.json WebFetch allows
#    (edit the allow array to include the new domain)

# 4. Regenerate cloud config if using setup_cloud.py
python3 agent-coordinator/scripts/setup_cloud.py --domain new.domain.com
```

## Verification

Run from any session (local or cloud) to verify full coordinator access:

```bash
# Full capability detection (JSON output)
python3 skills/coordination-bridge/scripts/check_coordinator.py --json

# Expected output when working:
# {
#   "COORDINATOR_AVAILABLE": true,
#   "COORDINATION_TRANSPORT": "http",
#   "health": {"status": "ok", "db": "connected", "version": "0.2.0"},
#   "CAN_LOCK": true,
#   "CAN_QUEUE_WORK": true,
#   ...all capabilities true...
# }

# Test hook scripts directly
AGENT_ID=claude-remote python3 agent-coordinator/scripts/register_agent.py
AGENT_ID=claude-remote python3 agent-coordinator/scripts/deregister_agent.py
```

If `COORDINATOR_AVAILABLE` is `false`, check:
1. Platform egress allows the coordinator domain
2. `COORDINATION_API_URL` is set and correct
3. `COORDINATION_ALLOWED_HOSTS` includes the coordinator hostname
4. The coordinator service is healthy (`/health` returns 200)

## Related Documentation

- [Cloud Deployment Guide](cloud-deployment.md) — Full Railway + ParadeDB setup
- [Cloudflare Domain Setup](cloudflare-setup.md) — Custom domain routing
- [Agent Coordinator](agent-coordinator.md) — Architecture overview
- [Setup Coordinator Skill](../skills/setup-coordinator/SKILL.md) — Interactive setup
