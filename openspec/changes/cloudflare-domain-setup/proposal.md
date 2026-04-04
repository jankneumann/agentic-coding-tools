# Proposal: Cloudflare Domain Setup for Coordinator Services

**Change ID**: `cloudflare-domain-setup`
**Status**: Draft
**Author**: Claude Code
**Date**: 2026-04-04

## Summary

Set up Cloudflare Tunnel and custom domain DNS to expose the full coordinator service mesh (HTTP API, MCP SSE, OpenBao, future services) through stable, provider-portable subdomains. The primary mode replaces Railway as the public endpoint by tunneling from the local machine through Cloudflare's network. A secondary documentation path covers proxying Railway as a backend for always-on scenarios.

## Motivation

### Current Pain Points

1. **Provider lock-in**: The coordinator API's public URL is a Railway-assigned domain (`your-app.railway.app`). Changing deployment targets requires updating `COORDINATION_API_URL`, `COORDINATION_ALLOWED_HOSTS`, agent configs, and documentation everywhere.

2. **Cost**: Railway hosts the coordinator API container ($$$) even though it's just proxying to a database. For development workflows where the operator's machine is available, this is unnecessary overhead.

3. **URL fragility**: Services are accessed via port numbers (`localhost:8081`, `localhost:8082`, `localhost:8200`). There's no human-readable, stable naming layer. Cloud agents must be configured with provider-specific URLs that change on redeployment.

4. **Single transport exposure**: Only the HTTP API (`:8081`) is exposed publicly via Railway. MCP SSE (`:8082`) and OpenBao (`:8200`) are local-only, limiting cloud agent transport options.

5. **No edge security layer**: The coordinator API is protected only by `X-API-Key` headers. There's no WAF, rate limiting, or DDoS protection — Railway provides basic TLS but no application-layer protection.

### Why Cloudflare Tunnel

Cloudflare Tunnel (`cloudflared`) creates an outbound-only connection from your machine to Cloudflare's edge network. This means:
- **No inbound ports** — your machine doesn't need to be directly reachable
- **Automatic TLS** — Cloudflare terminates TLS at the edge
- **Stable URLs** — subdomains like `coord.yourdomain.com` survive infrastructure changes
- **Edge features** — rate limiting, WAF, access policies are available at the Cloudflare dashboard level (future work)

### Strategic Value

A custom domain layer decouples service identity from deployment location. Today it's a tunnel to localhost; tomorrow it could point to Railway, Fly.io, or a VPS — without changing a single agent configuration.

## Goals

### Primary Goals

1. **Cloudflare Tunnel configuration** — `cloudflared` config for multi-service routing (API, MCP SSE, OpenBao) through a single tunnel with per-subdomain ingress rules
2. **Full service mesh DNS** — Subdomains for all coordinator services (`coord.`, `mcp.`, `vault.`, extensible for future services)
3. **Deployment profile** — New `profiles/cloudflare-tunnel.yaml` integrated into the existing profile inheritance system
4. **Dual hosting docs** — Both Docker Compose service and standalone system service (`systemd`/`launchd`) documented
5. **SSRF allowlist integration** — Custom domain automatically added to `COORDINATION_ALLOWED_HOSTS`
6. **Operator runbook** — Step-by-step guide for Cloudflare Tunnel setup, DNS configuration, and verification

### Secondary Goals

7. **Health check validation** — Verify the `/health` endpoint works through the tunnel with correct TLS termination
8. **Agent config examples** — Updated cloud agent connection examples using the custom domain
9. **CI awareness** — Document how CI (which can't use the tunnel) falls back to `localhost` URLs

### Non-Goals

- Cloudflare Access / Zero Trust integration (follow-up feature)
- Cloudflare Workers API gateway (follow-up feature)
- Multi-environment DNS (`coord-dev.` / `coord-prod.`) (follow-up feature)
- R2 storage integration (separate feature)
- Migrating the database away from Railway (out of scope — only the API hosting is replaced)

## What Changes

### New Files

| File | Purpose |
|------|---------|
| `agent-coordinator/cloudflared/config.yaml` | Cloudflare Tunnel configuration with multi-service ingress |
| `agent-coordinator/profiles/cloudflare-tunnel.yaml` | Deployment profile extending `base` |
| `docs/cloudflare-tunnel-setup.md` | Operator runbook for tunnel setup and DNS |

### Modified Files

| File | Change |
|------|--------|
| `agent-coordinator/docker-compose.yml` | Add `cloudflared` service (optional profile) |
| `docs/cloud-deployment.md` | Add Cloudflare Tunnel section alongside Railway |
| `skills/coordination-bridge/scripts/coordination_bridge.py` | No code changes needed — document domain in allowlist examples |

### Configuration Artifacts

| Artifact | Description |
|----------|-------------|
| `cloudflared/config.yaml` | Tunnel ID, ingress rules mapping subdomains to local ports |
| `profiles/cloudflare-tunnel.yaml` | Environment variables, SSRF allowlist, transport config |

## Approaches Considered

### Approach 1: Named Tunnel with Config File (Recommended)

Use `cloudflared tunnel` with a persistent named tunnel and YAML config file defining ingress rules per subdomain.

```yaml
tunnel: <tunnel-uuid>
credentials-file: /path/to/credentials.json

ingress:
  - hostname: coord.yourdomain.com
    service: http://localhost:8081
  - hostname: mcp.yourdomain.com
    service: http://localhost:8082
  - hostname: vault.yourdomain.com
    service: http://localhost:8200
  - service: http_status:404
```

DNS records are CNAME entries pointing to `<tunnel-uuid>.cfargotunnel.com`.

**Pros:**
- Persistent tunnel identity survives restarts
- Multi-service routing in a single tunnel (one process, one connection)
- Config file is version-controllable (minus credentials)
- Docker Compose integration is straightforward (mount config + credentials)
- Well-documented by Cloudflare, stable API

**Cons:**
- Requires one-time `cloudflared tunnel create` and DNS record setup (manual steps)
- Credentials file must be managed outside git (secret)
- Tunnel UUID is environment-specific (can't share exact config across machines)

**Effort:** S

### Approach 2: Quick Tunnel (Ephemeral)

Use `cloudflared tunnel --url http://localhost:8081` for instant, zero-config tunnels with auto-generated `*.trycloudflare.com` URLs.

**Pros:**
- Zero setup — single command, works immediately
- No Cloudflare account needed for basic usage
- Good for quick demos or one-off testing

**Cons:**
- URLs are random and change every restart — not stable
- Only supports one origin service per tunnel invocation (no multi-service mesh)
- No custom domain — defeats the primary goal
- No persistent identity or config management

**Effort:** S (but doesn't achieve goals)

### Approach 3: Cloudflare DNS Proxy to Railway

Keep Railway as the backend. Point custom domain DNS to Cloudflare, proxy traffic to Railway's domain. Cloudflare acts as CDN/WAF layer in front of Railway.

**Pros:**
- Always-on — doesn't depend on local machine uptime
- Railway handles compute, Cloudflare handles edge
- Adds CDN caching, WAF, DDoS protection to existing deployment
- No `cloudflared` daemon to run

**Cons:**
- Still paying for Railway API hosting
- Adds latency (Cloudflare edge → Railway → database)
- Only works for the HTTP API — MCP SSE and OpenBao still not exposed
- Requires Railway custom domain configuration (additional setup)

**Effort:** S

### Selected Approach (Approved at Gate 1)

**Approach 1: Named Tunnel with Config File** was selected because it:
- Achieves all primary goals (stable URLs, full service mesh, no Railway cost)
- Uses Cloudflare's production-grade tunnel infrastructure
- Produces a version-controllable config that can be templated for different operators
- Naturally supports Docker Compose and standalone hosting models

Approach 3 (DNS proxy to Railway) will be documented as a secondary option in the runbook for users who need always-on availability.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Local machine downtime = coordinator unavailable | Cloud agents lose coordination | Document Railway fallback; agents already handle coordinator unavailability gracefully |
| Credentials file leakage | Unauthorized tunnel access | `.gitignore` the credentials file; document OpenBao storage path |
| Tunnel UUID environment-specific | Config not portable across machines | Template the config with `${TUNNEL_UUID}` placeholder; document per-machine setup |
| MCP SSE through tunnel may have WebSocket issues | Cloud agents can't use MCP SSE transport | Test WebSocket/SSE passthrough; Cloudflare tunnels support WebSockets natively |

## Success Criteria

1. Cloud agent can reach coordinator API at `coord.yourdomain.com` through the tunnel
2. MCP SSE transport works at `mcp.yourdomain.com` through the tunnel
3. OpenBao vault accessible at `vault.yourdomain.com` through the tunnel
4. Health check passes: `curl https://coord.yourdomain.com/health` returns 200
5. SSRF allowlist accepts the custom domain without code changes
6. Docker Compose `docker compose --profile cloudflared up` starts tunnel alongside services
7. Standalone `cloudflared service install` documented and tested
