# Tasks: cloudflare-domain-setup

## Phase 1: Tunnel Configuration & Profile

- [ ] 1.1 Write tests for Cloudflare Tunnel config template validation
  **Spec scenarios**: agent-coordinator (Cloudflare Tunnel Configuration: multi-service ingress, catch-all safety)
  **Dependencies**: None

- [ ] 1.2 Create `agent-coordinator/cloudflared/config.yaml` — tunnel config template with multi-service ingress rules
  **Files**: `agent-coordinator/cloudflared/config.yaml`
  **Description**:
  - Template with `${TUNNEL_UUID}` and `${CREDENTIALS_FILE}` placeholders
  - Ingress rules for coord (→:8081), mcp (→:8082), vault (→:8200)
  - Catch-all `http_status:404` rule
  - Comments explaining each section and how to customize
  **Dependencies**: 1.1

- [ ] 1.3 Create `agent-coordinator/cloudflared/.gitignore` — exclude credentials and tunnel-specific files
  **Files**: `agent-coordinator/cloudflared/.gitignore`
  **Description**:
  - Ignore `*.json` (credentials files)
  - Ignore `*.pem` (certificate files)
  - Keep `config.yaml` tracked
  **Dependencies**: None

- [ ] 1.4 Write tests for cloudflare-tunnel profile loading and inheritance
  **Spec scenarios**: agent-coordinator (Cloudflare Tunnel Deployment Profile: profile loads, inheritance)
  **Dependencies**: None

- [ ] 1.5 Create `agent-coordinator/profiles/cloudflare-tunnel.yaml` — deployment profile
  **Files**: `agent-coordinator/profiles/cloudflare-tunnel.yaml`
  **Description**:
  - Extends `base` profile
  - Sets `coordination_allowed_hosts` from `${CUSTOM_DOMAIN}` env var
  - Sets transport to `http`
  - Documents required environment variables
  **Dependencies**: 1.4

## Phase 2: Docker Compose Integration

- [ ] 2.1 Write tests for docker-compose cloudflared service configuration
  **Spec scenarios**: agent-coordinator (Docker Compose Cloudflared Service: start with profile, default excludes)
  **Dependencies**: None

- [ ] 2.2 Add `cloudflared` service to `agent-coordinator/docker-compose.yml` under optional profile
  **Files**: `agent-coordinator/docker-compose.yml`
  **Description**:
  - Add `cloudflared` service using `cloudflare/cloudflared:latest` image
  - Place under `profiles: [cloudflared]` so it's opt-in
  - Mount `./cloudflared/config.yaml` and credentials volume
  - Command: `tunnel --config /etc/cloudflared/config.yaml run`
  - Depends on postgres (start order)
  **Dependencies**: 1.2, 2.1

## Phase 3: SSRF Allowlist & Bridge Updates

- [ ] 3.1 Write tests for custom domain SSRF allowlist validation
  **Spec scenarios**: agent-coordinator (SSRF Allowlist Custom Domain Support: custom domain, wildcard pattern)
  **Dependencies**: None

- [ ] 3.2 Update SSRF allowlist documentation and examples in `coordination_bridge.py`
  **Files**: `skills/coordination-bridge/scripts/coordination_bridge.py`
  **Description**:
  - Add Cloudflare custom domain examples alongside Railway examples in comments
  - Document wildcard subdomain pattern if supported
  - No code changes needed — just documentation in code comments
  **Dependencies**: 3.1

- [ ] 3.3 Test wildcard subdomain support in `_validate_url()` — verify `*.domain.com` matching works or document limitation
  **Spec scenarios**: agent-coordinator (SSRF Allowlist Custom Domain Support: wildcard pattern)
  **Dependencies**: None

## Phase 4: Documentation

- [ ] 4.1 Create `docs/cloudflare-tunnel-setup.md` — operator runbook
  **Files**: `docs/cloudflare-tunnel-setup.md`
  **Spec scenarios**: agent-coordinator (Standalone Tunnel Service Documentation: systemd, launchd), (Tunnel Health Verification: health check, MCP SSE)
  **Description**:
  - Prerequisites (Cloudflare account, domain, cloudflared CLI)
  - Step-by-step: create tunnel, configure DNS, set up config
  - Docker Compose usage (`--profile cloudflared`)
  - Standalone systemd service setup (Linux)
  - Standalone launchd agent setup (macOS)
  - Health verification checklist (API, MCP SSE, OpenBao)
  - Troubleshooting common issues
  - Railway fallback for always-on scenarios
  **Dependencies**: 1.2, 1.5, 2.2

- [ ] 4.2 Update `docs/cloud-deployment.md` — add Cloudflare Tunnel section
  **Files**: `docs/cloud-deployment.md`
  **Description**:
  - Add "Cloudflare Tunnel" section alongside existing Railway section
  - Cross-reference `docs/cloudflare-tunnel-setup.md` for full instructions
  - Update SSRF allowlist examples to include custom domain
  **Dependencies**: 4.1

- [ ] 4.3 Add cloud agent connection examples using custom domain
  **Files**: `docs/cloudflare-tunnel-setup.md`
  **Description**:
  - Example `COORDINATION_API_URL=https://coord.yourdomain.com`
  - Example coordination bridge detect command with custom domain
  - Example agent config snippets for Claude Web, Codex Cloud, Gemini Cloud
  **Dependencies**: 4.1

## Phase 5: Verification

- [ ] 5.1 Run SSRF allowlist tests to confirm custom domain acceptance
  **Dependencies**: 3.1, 3.2, 3.3

- [ ] 5.2 Validate profile loading with cloudflare-tunnel profile
  **Dependencies**: 1.4, 1.5

- [ ] 5.3 Validate docker-compose config with `docker compose --profile cloudflared config`
  **Dependencies**: 2.2

- [ ] 5.4 Manual verification: end-to-end tunnel test (if cloudflared available)
  **Spec scenarios**: agent-coordinator (Tunnel Health Verification: health check, MCP SSE)
  **Description**:
  - Start coordinator + tunnel
  - Verify `curl https://coord.<domain>/health` returns 200
  - Verify CF-Ray header present
  - Test MCP SSE connectivity through tunnel
  **Dependencies**: All previous phases
