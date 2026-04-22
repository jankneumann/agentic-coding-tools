---

## Phase: Plan (2026-04-04)

**Agent**: claude_code | **Session**: session_01PSp4stBb1JxAznAHHm1DiH

### Decisions
1. **Named Tunnel approach over DNS Proxy** `architectural: configuration` — Provides full service mesh (API + MCP SSE + OpenBao), eliminates Railway hosting cost, and creates provider-portable stable URLs
2. **Full service mesh DNS** `architectural: configuration` — Subdomains for all services (coord/mcp/vault) rather than just the API, enabling cloud agents to use all transport options
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
Planned Cloudflare Tunnel setup for coordinator service mesh. User has a domain on Cloudflare already. The SSRF allowlist and profile system already support custom domains, so this change is primarily infrastructure config, Docker Compose integration, and documentation.

---

## Phase: Implementation (2026-04-04)

**Agent**: claude_code | **Session**: current

### Decisions
1. **Added wildcard subdomain support to SSRF allowlist** — The existing _validate_url() did exact hostname matching only. Spec required wildcard support. Added ~10 lines to parse wildcard entries and match subdomains.
2. **Cloudflare profile extends Railway (not base)** `architectural: configuration` — Inherits Railway's Postgres DSN, API host/port, workers. Only overrides coordination_allowed_hosts with wildcard domain.
3. **No nested profile interpolation** `architectural: configuration` — The profile loader regex does not support nested variable references. Used simple wildcard pattern instead, with COORDINATION_ALLOWED_HOSTS env var overriding at runtime.
4. **Comprehensive runbook** — Combined all documentation tasks (zone setup, Railway custom domain, tunnel, agent config, secrets) into a single docs/cloudflare-setup.md with clear sections for each path.

### Alternatives Considered
- Separate profile for tunnel vs proxy: rejected — single `cloudflare.yaml` profile works for both since the SSRF allowlist is the only code-level difference, and DNS routing determines which backend is used
- Modifying `_validate_url()` for nested interpolation: rejected — profile loader regex fix is out of scope; simple `*.${CUSTOM_DOMAIN}` achieves the same result

### Trade-offs
- Accepted a small code change (wildcard matching) over documentation-only — the spec required wildcard support, and the change is trivial and well-tested

### Open Questions
- [x] Wildcard subdomain matching — implemented and tested (3 new tests)
- [ ] Railway custom domain plan tier — needs manual verification during setup
- [ ] MCP SSE through Cloudflare proxy — documented keepalive recommendation, needs live testing

### Context
Implemented all 19 tasks across 4 phases. Key code change: wildcard subdomain support in SSRF allowlist (5 lines + 3 tests). Rest is configuration (profile, tunnel template, docker-compose) and documentation (operator runbook, cloud deployment guide).
