# Tasks: cloudflare-domain-setup

## Phase 1: Cloudflare Zone & DNS Proxy to Railway (Production Path)

- [ ] 1.1 Create `docs/cloudflare-setup.md` — Cloudflare zone setup section
  **Files**: `docs/cloudflare-setup.md`
  **Spec scenarios**: Cloudflare Zone and DNS Configuration (DNS proxy to Railway, SSL/TLS mode)
  **Description**:
  - Prerequisites (Cloudflare account, registered domain)
  - Step-by-step: add domain to Cloudflare, update nameservers
  - Configure SSL/TLS mode to "Full (Strict)"
  - Create CNAME record: `coord.<domain>` → Railway domain (proxy enabled)
  - Verify CF-Ray header in response
  - DNS propagation troubleshooting
  **Dependencies**: None

- [ ] 1.2 Document Railway custom domain configuration in `docs/cloudflare-setup.md`
  **Files**: `docs/cloudflare-setup.md`
  **Spec scenarios**: Railway Custom Domain Configuration (Railway accepts custom domain traffic)
  **Description**:
  - Railway service settings for custom domain
  - DNS verification steps required by Railway
  - TLS certificate handling (Cloudflare manages edge TLS, Railway manages origin TLS)
  - Verify Railway serves responses at custom domain
  - Document fallback: Railway-assigned domain continues working
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for Cloudflare deployment profile loading and inheritance
  **Spec scenarios**: Cloudflare Deployment Profile (profile loads, inheritance from Railway)
  **Dependencies**: None

- [ ] 1.4 Create `agent-coordinator/profiles/cloudflare.yaml` — deployment profile
  **Files**: `agent-coordinator/profiles/cloudflare.yaml`
  **Spec scenarios**: Cloudflare Deployment Profile (profile loads, inheritance from Railway)
  **Description**:
  - Extends `railway` profile (not base — inherits Railway's Postgres DSN, host, port, workers)
  - Sets `coordination_allowed_hosts` from `${CUSTOM_DOMAIN}` env var
  - Keeps transport as `http`
  - Documents required environment variables (`CUSTOM_DOMAIN`)
  **Dependencies**: 1.3

- [ ] 1.5 Write tests for custom domain SSRF allowlist validation
  **Spec scenarios**: SSRF Allowlist Custom Domain Support (custom domain, wildcard pattern)
  **Dependencies**: None

- [ ] 1.6 Update SSRF allowlist documentation and examples
  **Files**: `skills/coordination-bridge/scripts/coordination_bridge.py`, `agent-coordinator/.env.example`
  **Spec scenarios**: SSRF Allowlist Custom Domain Support (custom domain, wildcard pattern)
  **Description**:
  - Add Cloudflare custom domain examples alongside Railway examples in coordination_bridge.py comments
  - Add `CUSTOM_DOMAIN` to `.env.example`
  - Test wildcard subdomain pattern (`*.domain.com`) in `_validate_url()`
  **Dependencies**: 1.5

- [ ] 1.7 Update `docs/cloud-deployment.md` — add Cloudflare section
  **Files**: `docs/cloud-deployment.md`
  **Description**:
  - Add "Cloudflare Domain" section alongside existing Railway section
  - Cross-reference `docs/cloudflare-setup.md` for full instructions
  - Update SSRF allowlist examples to include custom domain
  **Dependencies**: 1.1

## Phase 2: Named Tunnel Configuration (Testing Path)

- [ ] 2.1 Write tests for Cloudflare Tunnel config template validation
  **Spec scenarios**: Cloudflare Tunnel Configuration (multi-service ingress, catch-all safety)
  **Dependencies**: None

- [ ] 2.2 Create `agent-coordinator/cloudflared/config.yaml` — tunnel config template
  **Files**: `agent-coordinator/cloudflared/config.yaml`
  **Spec scenarios**: Cloudflare Tunnel Configuration (multi-service ingress, catch-all safety)
  **Description**:
  - Template with `${TUNNEL_UUID}` and `${CREDENTIALS_FILE}` placeholders
  - Ingress rules for coord (→:8081), mcp (→:8082), vault (→:8200)
  - Catch-all `http_status:404` rule
  - Comments explaining each section and how to customize
  **Dependencies**: 2.1

- [ ] 2.3 Create `agent-coordinator/cloudflared/.gitignore` — exclude credentials
  **Files**: `agent-coordinator/cloudflared/.gitignore`
  **Description**:
  - Ignore `*.json` (credentials files)
  - Ignore `*.pem` (certificate files)
  - Keep `config.yaml` tracked
  **Dependencies**: None

- [ ] 2.4 Write tests for docker-compose cloudflared service configuration
  **Spec scenarios**: Docker Compose Cloudflared Service (start with profile, default excludes)
  **Dependencies**: None

- [ ] 2.5 Add `cloudflared` service to `agent-coordinator/docker-compose.yml`
  **Files**: `agent-coordinator/docker-compose.yml`
  **Spec scenarios**: Docker Compose Cloudflared Service (start with profile, default excludes)
  **Description**:
  - Add `cloudflared` service using `cloudflare/cloudflared:latest` image
  - Place under `profiles: [cloudflared]` so it's opt-in
  - Mount `./cloudflared/config.yaml` and credentials volume
  - Command: `tunnel --config /etc/cloudflared/config.yaml run`
  - Depends on postgres (start order)
  **Dependencies**: 2.2, 2.4

- [ ] 2.6 Add tunnel setup section to `docs/cloudflare-setup.md`
  **Files**: `docs/cloudflare-setup.md`
  **Spec scenarios**: Cloudflare Tunnel Configuration (multi-service ingress), Tunnel Health Verification (health check, MCP SSE)
  **Description**:
  - Prerequisites: `cloudflared` CLI installed
  - Create named tunnel: `cloudflared tunnel create <name>`
  - Configure DNS CNAMEs pointing to `<tunnel-uuid>.cfargotunnel.com`
  - Docker Compose usage: `--profile cloudflared`
  - Standalone daemon: systemd (Linux) and launchd (macOS) setup
  - Health verification checklist (API, MCP SSE, OpenBao)
  - How to switch DNS from Railway proxy to tunnel (and back)
  **Dependencies**: 1.1, 2.2, 2.5

## Phase 3: Agent Configuration & Secret Management

- [ ] 3.1 Add cloud agent connection examples to `docs/cloudflare-setup.md`
  **Files**: `docs/cloudflare-setup.md`
  **Description**:
  - Example: `COORDINATION_API_URL=https://coord.<domain>`
  - Example: coordination bridge detect command with custom domain
  - Agent config snippets for Claude Web, Codex Cloud, Gemini Cloud
  - Document that agent configs are the same regardless of whether backend is Railway or tunnel
  **Dependencies**: 1.1

- [ ] 3.2 Document secret management strategy in `docs/cloudflare-setup.md`
  **Files**: `docs/cloudflare-setup.md`
  **Description**:
  - Recommended path: Railway env vars for production secrets
  - Local dev: `.env` files (gitignored) + OpenBao in docker-compose
  - Tunnel credentials: document secure storage outside git
  - Future: shared OpenBao behind Cloudflare when home server is available
  **Dependencies**: 1.1

## Phase 4: Verification

- [ ] 4.1 Run SSRF allowlist tests to confirm custom domain acceptance
  **Dependencies**: 1.5, 1.6

- [ ] 4.2 Validate profile loading with cloudflare profile
  **Dependencies**: 1.3, 1.4

- [ ] 4.3 Validate docker-compose config with `docker compose --profile cloudflared config`
  **Dependencies**: 2.5

- [ ] 4.4 Validate openspec specs: `openspec validate cloudflare-domain-setup --strict`
  **Dependencies**: All previous phases
