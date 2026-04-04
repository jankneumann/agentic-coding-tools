# agent-coordinator — Delta Spec for cloudflare-domain-setup

## ADDED Requirements

### Requirement: Cloudflare Tunnel Configuration

The coordinator project SHALL include a templateable Cloudflare Tunnel configuration file that routes multiple subdomains to local coordinator services through a single named tunnel.

#### Scenario: Multi-service ingress routing
- **WHEN** the cloudflared daemon starts with the provided config template
- **THEN** it SHALL route `coord.<domain>` to `http://localhost:8081` (HTTP API)
- **AND** it SHALL route `mcp.<domain>` to `http://localhost:8082` (MCP SSE)
- **AND** it SHALL route `vault.<domain>` to `http://localhost:8200` (OpenBao)
- **AND** unmatched hostnames SHALL receive HTTP 404

#### Scenario: Catch-all rule safety
- **WHEN** a request arrives for an unrecognized hostname
- **THEN** the tunnel SHALL return HTTP 404
- **AND** it SHALL NOT forward the request to any local service

---

### Requirement: Cloudflare Tunnel Deployment Profile

The coordinator SHALL provide a deployment profile (`profiles/cloudflare-tunnel.yaml`) that extends the base profile and configures environment variables for tunnel-based access.

#### Scenario: Profile loads with custom domain
- **WHEN** the profile is loaded with `CUSTOM_DOMAIN` set
- **THEN** `coordination_allowed_hosts` SHALL include the coordinator subdomain
- **AND** the transport SHALL be set to `http`

#### Scenario: Profile inheritance
- **WHEN** the cloudflare-tunnel profile is loaded
- **THEN** it SHALL inherit all settings from the base profile
- **AND** it SHALL override only tunnel-specific fields (allowed hosts, transport)

---

### Requirement: Docker Compose Cloudflared Service

The docker-compose configuration SHALL include a `cloudflared` service under an optional Docker Compose profile, so operators can start the tunnel alongside other services.

#### Scenario: Start tunnel with Docker Compose profile
- **WHEN** `docker compose --profile cloudflared up` is executed
- **THEN** the `cloudflared` container SHALL start alongside postgres
- **AND** the tunnel SHALL use the mounted config and credentials files

#### Scenario: Default startup excludes tunnel
- **WHEN** `docker compose up` is executed without the `cloudflared` profile
- **THEN** the cloudflared service SHALL NOT start
- **AND** postgres and other default services SHALL start normally

---

### Requirement: Standalone Tunnel Service Documentation

The operator runbook SHALL document how to install cloudflared as a standalone system service on Linux (systemd) and macOS (launchd).

#### Scenario: Systemd service installation
- **WHEN** the operator follows the systemd installation steps
- **THEN** cloudflared SHALL be registered as a system service
- **AND** it SHALL start automatically on boot
- **AND** it SHALL use the project's tunnel config file

#### Scenario: Launchd service installation
- **WHEN** the operator follows the launchd installation steps
- **THEN** cloudflared SHALL be registered as a launch agent
- **AND** it SHALL start automatically on login

---

### Requirement: SSRF Allowlist Custom Domain Support

The coordination bridge's SSRF allowlist documentation SHALL include examples for Cloudflare custom domains alongside the existing Railway examples.

#### Scenario: Custom domain in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes `coord.customdomain.com`
- **THEN** the coordination bridge SHALL allow HTTP requests to `https://coord.customdomain.com`
- **AND** requests to unlisted hosts SHALL still be blocked

#### Scenario: Wildcard subdomain pattern
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes `*.customdomain.com`
- **THEN** the coordination bridge SHALL allow requests to any subdomain of `customdomain.com`

---

### Requirement: Tunnel Health Verification

The operator runbook SHALL include verification steps to confirm the tunnel is working correctly for all exposed services.

#### Scenario: Health check through tunnel
- **WHEN** the operator runs `curl https://coord.<domain>/health`
- **THEN** the response SHALL be HTTP 200 with a valid health payload
- **AND** the response SHALL be served through Cloudflare (CF-Ray header present)

#### Scenario: MCP SSE through tunnel
- **WHEN** a cloud agent connects to `https://mcp.<domain>/sse`
- **THEN** the SSE connection SHALL be established successfully
- **AND** the agent SHALL be able to send and receive MCP messages

---

## MODIFIED Requirements

### Requirement: SSRF Allowlist Documentation

The coordination bridge MUST document how to configure `COORDINATION_ALLOWED_HOSTS` for cloud deployment URLs beyond the default localhost allowlist.

#### Scenario: Cloud URL in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes the deployment hostname (Railway or custom domain)
- **THEN** the coordination bridge SHALL allow HTTP requests to that host
- **AND** requests to unlisted hosts SHALL still be blocked

#### Scenario: Cloudflare Tunnel domain in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes a Cloudflare Tunnel custom domain
- **THEN** the coordination bridge SHALL allow HTTP requests to that domain
- **AND** the existing Railway hostname support SHALL remain unchanged
