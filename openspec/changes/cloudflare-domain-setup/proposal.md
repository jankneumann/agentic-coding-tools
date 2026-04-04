# Proposal: Cloudflare Domain Setup for Coordinator Services

**Change ID**: `cloudflare-domain-setup`
**Status**: Draft (Revision 2)
**Author**: Claude Code
**Date**: 2026-04-04

## Summary

Set up a Cloudflare domain with custom DNS to provide stable, provider-portable subdomains for coordinator services. Two deployment paths are implemented in parallel:

1. **DNS Proxy to Railway** (production) — Cloudflare proxies traffic to the existing Railway deployment through custom subdomains. This is the primary path for the next 2-3 months while no always-on home server is available.
2. **Named Tunnel to local machine** (testing) — Cloudflare Tunnel exposes the coordinator running on a laptop for development and testing. Both paths can be validated side-by-side.

## Motivation

### Current Pain Points

1. **Provider lock-in**: The coordinator API's public URL is a Railway-assigned domain (`your-app.railway.app`). Changing deployment targets requires updating `COORDINATION_API_URL`, `COORDINATION_ALLOWED_HOSTS`, agent configs, and documentation everywhere.

2. **URL fragility**: Services are accessed via port numbers (`localhost:8081`, `localhost:8082`, `localhost:8200`). No human-readable, stable naming layer. Cloud agents must be configured with provider-specific URLs that change on redeployment.

3. **Single transport exposure**: Only the HTTP API (`:8081`) is exposed publicly via Railway. MCP SSE (`:8082`) and OpenBao (`:8200`) are local-only, limiting cloud agent transport options.

4. **No edge security layer**: The coordinator API is protected only by `X-API-Key` headers. No WAF, rate limiting, or DDoS protection — Railway provides basic TLS but no application-layer protection.

### Why Cloudflare

- **Stable URLs** — subdomains like `coord.yourdomain.com` survive infrastructure changes
- **Automatic TLS** — Cloudflare terminates TLS at the edge
- **Edge features** — rate limiting, WAF, access policies available at the Cloudflare dashboard (future work)
- **Provider portability** — the custom domain layer decouples service identity from deployment location. Today it points to Railway; in 2-3 months it can point to a home server tunnel — without changing agent configurations.

### Constraint: No Always-On Home Server (Next 2-3 Months)

The operator does not currently have a dedicated always-on server. Railway remains the production backend. Cloudflare sits in front as a reverse proxy, adding stable DNS, TLS management, and edge protection. The named tunnel path is implemented in parallel for laptop-based testing.

## Goals

### Primary Goals

1. **Cloudflare zone setup** — Add domain to Cloudflare, configure DNS zone
2. **DNS proxy to Railway** — CNAME records routing `coord.<domain>` through Cloudflare to Railway's backend
3. **Railway custom domain** — Configure Railway to accept traffic on the custom domain
4. **Deployment profile** — New `profiles/cloudflare.yaml` for the Cloudflare-proxied Railway setup
5. **SSRF allowlist integration** — Custom domain added to `COORDINATION_ALLOWED_HOSTS`
6. **Named tunnel configuration** — `cloudflared` config for multi-service routing from laptop (parallel testing path)
7. **Operator runbook** — Setup guide covering both DNS proxy and tunnel paths

### Secondary Goals

8. **Health check validation** — Verify `/health` through the custom domain
9. **Agent config examples** — Updated cloud agent connection examples using the custom domain
10. **Secret management recommendation** — Document Railway env vars vs shared OpenBao trade-offs

### Non-Goals

- Cloudflare Access / Zero Trust integration (follow-up feature)
- Cloudflare Workers API gateway (follow-up feature)
- Multi-environment DNS (`coord-dev.` / `coord-prod.`) (follow-up feature)
- R2 storage integration (separate feature)
- Migrating the database away from Railway (out of scope)
- Running OpenBao on Railway behind Cloudflare (deferred — Railway env vars sufficient for now)

## What Changes

### New Files

| File | Purpose |
|------|---------|
| `agent-coordinator/profiles/cloudflare.yaml` | Deployment profile for Cloudflare-proxied Railway |
| `agent-coordinator/cloudflared/config.yaml` | Tunnel config template for local testing path |
| `agent-coordinator/cloudflared/.gitignore` | Exclude credentials and tunnel-specific files |
| `docs/cloudflare-setup.md` | Operator runbook covering zone setup, DNS proxy, and tunnel paths |

### Modified Files

| File | Change |
|------|--------|
| `agent-coordinator/docker-compose.yml` | Add `cloudflared` service under optional profile |
| `agent-coordinator/.env.example` | Add `CUSTOM_DOMAIN`, `TUNNEL_UUID`, `CREDENTIALS_FILE` vars |
| `docs/cloud-deployment.md` | Add Cloudflare section alongside Railway |
| `skills/coordination-bridge/scripts/coordination_bridge.py` | Document custom domain in allowlist examples |

## Approaches Considered

### Approach 1: DNS Proxy to Railway + Parallel Tunnel (Selected)

Cloudflare proxies traffic to Railway via CNAME records. Custom subdomains route through Cloudflare's edge network to Railway's backend. In parallel, a named tunnel configuration enables the same subdomains to route to the local laptop for testing.

**Pros:**
- Always-on production via Railway (no home server needed)
- Edge security (TLS, DDoS, future WAF) from Cloudflare
- Stable custom domain from day one
- Tunnel path validates the future migration to own server
- Both paths share the same subdomains — agent configs don't change

**Cons:**
- Railway hosting cost continues during the 2-3 month interim
- Two deployment configs to maintain (proxy + tunnel)
- Railway custom domain setup requires paid plan or domain verification

**Effort:** S-M

### Approach 2: Named Tunnel Only (Original Plan — Deferred as Primary)

Use `cloudflared tunnel` with a persistent named tunnel and YAML config. All traffic routes from Cloudflare edge through the tunnel to the local machine.

**Pros:**
- Eliminates Railway hosting cost
- Full service mesh (API, MCP SSE, OpenBao)
- Single infrastructure path

**Cons:**
- Requires always-on machine — not available for 2-3 months
- Local machine downtime = coordinator unavailable

**Effort:** S — implemented as the parallel testing path within Approach 1.

### Approach 3: Railway Only with Custom Domain (No Tunnel)

Point custom domain DNS to Railway without Cloudflare proxying. Railway handles custom domain TLS directly.

**Pros:**
- Simplest setup — just DNS records and Railway config
- No Cloudflare dependency for traffic flow

**Cons:**
- No edge security layer (WAF, rate limiting, DDoS)
- No tunnel testing path — can't validate future migration
- Still provider-coupled at the TLS/edge layer

**Effort:** S

### Approach 4: Tailscale Funnel (Evaluated and Rejected)

Use Tailscale Funnel to expose local services publicly via `*.ts.net` hostnames.

**Why rejected:**
- **Cannot proxy to Railway** — Funnel only exposes services running on the local Tailscale node. Since Railway is the production backend for 2-3 months, this requires a completely separate routing solution, defeating the purpose of a unified edge layer.
- **No custom subdomains** — services get path-based routing on a single `*.ts.net` hostname, not separate subdomains.
- **No edge security** — no WAF, rate limiting, or DDoS protection.
- **Port restrictions** — only ports 443, 8443, 10000 can be funneled.

Tailscale is excellent for private mesh networking (device-to-device). It could complement Cloudflare later for private connectivity between home server and laptop, but it's not suitable as the public-facing edge for cloud agents.

### Selected Approach

**Approach 1: DNS Proxy to Railway + Parallel Tunnel** — provides the stable custom domain needed now (via Railway), the edge security layer from Cloudflare, and validates the tunnel migration path in parallel. When the home server is available in 2-3 months, switching is a DNS record change.

## Secret Management Strategy

**Recommendation for the next 2-3 months: Railway environment variables.**

- Secrets (API keys, DB credentials) live in Railway's dashboard per-service
- Local development uses `.env` files (gitignored)
- The existing OpenBao instance in docker-compose continues for local development

**Why not shared OpenBao behind Cloudflare:**
- Adds hosting cost and infrastructure complexity
- Vault must be always-on (same constraint as the coordinator)
- Railway env vars are sufficient for the current single-service deployment
- Can be revisited when the home server is available

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Railway doesn't support custom domains on current plan | Can't complete DNS proxy path | Verify Railway plan supports custom domains before implementation; fallback to Cloudflare Workers proxy |
| Cloudflare proxy adds latency to Railway | Slower API responses | Cloudflare edge is typically faster than direct; monitor with health checks |
| Tunnel credentials leakage | Unauthorized tunnel access | `.gitignore` credentials; document secure storage |
| DNS propagation delay | Temporary downtime during setup | Keep Railway URL as fallback; agents handle coordinator unavailability |
| MCP SSE through Cloudflare proxy may buffer | SSE streaming broken | Test SSE passthrough; Cloudflare supports WebSocket/SSE natively |

## Success Criteria

1. `curl https://coord.<domain>/health` returns HTTP 200 through Cloudflare (CF-Ray header present)
2. Cloud agents can connect to coordinator at `coord.<domain>` instead of Railway URL
3. SSRF allowlist accepts the custom domain without code changes (env var only)
4. Named tunnel routes `coord.<domain>` to `localhost:8081` when running locally
5. Docker Compose `--profile cloudflared` starts tunnel alongside services
6. Railway continues serving as backend through the custom domain
7. Switching from Railway to tunnel requires only a DNS record change (no agent config changes)
