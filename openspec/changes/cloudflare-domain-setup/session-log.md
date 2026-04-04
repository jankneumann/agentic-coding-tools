---

## Phase: Plan (2026-04-04)

**Agent**: claude_code | **Session**: session_01PSp4stBb1JxAznAHHm1DiH

### Decisions
1. **Named Tunnel approach over DNS Proxy** — Provides full service mesh (API + MCP SSE + OpenBao), eliminates Railway hosting cost, and creates provider-portable stable URLs
2. **Full service mesh DNS** — Subdomains for all services (coord/mcp/vault) rather than just the API, enabling cloud agents to use all transport options
3. **Both Docker Compose and standalone service hosting** — Docker for development workflow, systemd/launchd for always-on production
4. **Sequential tier** — Feature is focused on single architectural boundary (networking/deployment infrastructure)

### Alternatives Considered
- Quick Tunnel (ephemeral): rejected because URLs are random and change on restart, defeating the stable URL goal
- DNS Proxy to Railway: rejected as primary approach because it still requires Railway hosting costs and only exposes HTTP API; documented as secondary fallback in the runbook

### Trade-offs
- Accepted local machine uptime dependency over always-on Railway hosting because the cost savings and direct coordinator access outweigh uptime concerns (agents already handle coordinator unavailability gracefully)
- Accepted manual tunnel creation step over full automation because tunnel UUID is inherently per-machine

### Open Questions
- [ ] Should we add Cloudflare Access (Zero Trust) in a follow-up change?
- [ ] Should wildcard subdomain matching be added to SSRF allowlist code (currently may need explicit entries per subdomain)?

### Context
Planned Cloudflare Tunnel setup for coordinator service mesh. User has a domain on Cloudflare already. The codebase's SSRF allowlist and profile system already support custom domains, so this change is primarily infrastructure config, Docker Compose integration, and documentation.
