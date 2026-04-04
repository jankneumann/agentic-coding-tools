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

---

## Phase: Plan Revision 2 (2026-04-04)

**Agent**: claude_code | **Session**: current

### Decisions
1. **Flipped approach priority** — DNS Proxy to Railway is now the primary production path (not a fallback). Operator has no always-on home server for the next 2-3 months, so Railway must remain the backend.
2. **Both paths in parallel** — DNS proxy to Railway (production) + Named Tunnel to laptop (testing). Both implemented simultaneously so they can be validated side-by-side.
3. **Cloudflare profile extends Railway** — New `profiles/cloudflare.yaml` inherits from `railway.yaml` (not base), adding only the custom domain SSRF allowlist override. Railway settings (DSN, host, port, workers) are inherited.
4. **Railway env vars for secrets** — Not running shared OpenBao behind Cloudflare. Railway dashboard for production secrets, local `.env` + OpenBao for dev. Revisit when home server is available.
5. **Cloudflare zone setup needed** — Domain exists but is not yet added to Cloudflare. Runbook includes zone setup steps.
6. **Tailscale Funnel evaluated and rejected** — Cannot proxy to Railway (Funnel only exposes local services), single hostname with path-based routing, no edge security. Tailscale is complementary for private mesh, not suitable as public edge.
7. **Local-only users unaffected** — Cloudflare setup is purely additive. `profiles/local.yaml` and `check_coordinator.py` defaults continue working unchanged.
8. **Coordinated tier** — Coordinator available, but feature is mostly config/docs with two parallel work packages (DNS proxy + tunnel).

### Alternatives Considered
- Named Tunnel as primary (original plan): deferred because no always-on server for 2-3 months
- Tailscale Funnel: rejected — cannot proxy to Railway, port restrictions (443/8443/10000 only), no edge security
- Railway-only custom domain (no Cloudflare proxy): rejected — no edge security, no tunnel testing path

### Trade-offs
- Accepted continued Railway hosting cost (2-3 months) over coordinator downtime when laptop is off
- Accepted two deployment configs (proxy + tunnel) over a single path — enables parallel validation
- Accepted Railway env vars over shared OpenBao — simpler, sufficient for single-service deployment

### Open Questions
- [ ] Does Railway plan support custom domains? Need to verify before implementation
- [ ] MCP SSE through Cloudflare proxy — needs testing for buffering/timeout behavior
- [ ] Wildcard subdomain matching in SSRF allowlist code (`*.domain.com`)

### Context
Revised the plan from PR #67 based on operator constraint: no always-on home server for 2-3 months. Flipped DNS proxy to Railway as primary production path, kept named tunnel as parallel testing path. Added Cloudflare zone setup (domain not yet added to CF), Tailscale comparison, and secret management strategy. The future migration to own server is a DNS record swap — no agent config changes needed.
