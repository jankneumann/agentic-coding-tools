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

### Hook Script Behavior by Environment

The three hook scripts have different transport dependencies:

| Hook Event | Script | Transport | Local (MCP/Supabase) | Cloud (HTTP only) |
|------------|--------|-----------|---------------------|-------------------|
| `SessionStart` | `register_agent.py` | Supabase SDK | Works | **Silently skipped** |
| `Stop` / `SubagentStop` | `report_status.py` | HTTP API (`httpx`) | Works | Works |
| `SessionEnd` | `deregister_agent.py` | Supabase SDK | Works | **Silently skipped** |

**Why the gap exists**: `register_agent.py` and `deregister_agent.py` were
written when the only backend was Supabase. They import `src.config.get_config()`
which requires `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Cloud sessions
typically only have `COORDINATION_API_URL` and `COORDINATION_API_KEY` (HTTP
transport). The scripts catch the `ValueError` and exit silently — no crash,
but no registration or lock cleanup either.

`report_status.py` was written later and uses `httpx` to POST directly to the
coordinator HTTP API, so it works everywhere.

### Impact of Skipped Hooks

| Feature | Impact When Hook Is Skipped | Mitigation |
|---------|----------------------------|------------|
| Agent registration | Coordinator doesn't know agent started | Skills call `/profiles/me` on first use |
| Handoff loading | No automatic context from previous session | Manual `/recall` via coordination bridge |
| Lock release on exit | Stale locks may persist | Lock TTL (default 120 min) auto-expires them |
| Final handoff write | No session summary for next agent | Write handoff manually before session end |

### Future Fix

To make all hooks work in cloud sessions, `register_agent.py` and
`deregister_agent.py` should be updated to use the HTTP API (like
`report_status.py` does) when Supabase env vars are absent. The HTTP API
already has equivalent endpoints:

- Registration: `POST /status/report` (with `event_type: "session.started"`)
- Lock release: `POST /locks/release` (per held lock, or add a bulk endpoint)
- Handoff write: `POST /handoffs/write`
- Handoff read: `POST /handoffs/read`

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
**not** affect Python's `urllib` or `httpx` (used by all coordinator scripts).

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
| `COORDINATION_API_URL` | Yes | `https://coord.rotkohl.ai` | `check_coordinator.py`, `coordination_bridge.py` |
| `COORDINATION_API_KEY` | Yes | `91a8925e...` | HTTP `X-API-Key` header |
| `COORDINATION_ALLOWED_HOSTS` | Yes | `coord.rotkohl.ai` | SSRF allowlist in bridge |
| `COORDINATOR_URL` | Optional | `https://coord.rotkohl.ai` | `report_status.py` (fallback for `COORDINATION_API_URL`) |
| `AGENT_ID` | Optional | `claude-web-1` | Agent identity in status reports |

**Note**: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are only needed for local
MCP mode (direct DB access). Cloud sessions should **not** set these — the
HTTP API handles all DB access server-side.

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
