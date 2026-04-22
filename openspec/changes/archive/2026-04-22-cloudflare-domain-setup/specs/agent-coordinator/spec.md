# agent-coordinator — Delta Spec for cloudflare-domain-setup

## ADDED Requirements

### Requirement: Cloudflare Zone and DNS Configuration

The operator runbook SHALL document how to add a domain to Cloudflare, configure the DNS zone, and create subdomain records pointing to the Railway backend through Cloudflare's proxy.

#### Scenario: DNS proxy to Railway
- **WHEN** the operator creates a CNAME record for `coord.<domain>` pointing to the Railway domain
- **AND** Cloudflare proxy is enabled (orange cloud)
- **THEN** traffic to `coord.<domain>` SHALL be proxied through Cloudflare to Railway
- **AND** the response SHALL include a `CF-Ray` header confirming Cloudflare edge routing

#### Scenario: SSL/TLS mode
- **WHEN** the Cloudflare zone is configured with SSL mode "Full (Strict)"
- **THEN** traffic between Cloudflare and Railway SHALL be encrypted end-to-end
- **AND** Cloudflare SHALL terminate TLS at the edge and re-encrypt to the origin

---

### Requirement: Cloudflare Deployment Profile

The coordinator SHALL provide a deployment profile (`profiles/cloudflare.yaml`) that extends the Railway profile and configures environment variables for Cloudflare-proxied access.

#### Scenario: Profile loads with custom domain
- **WHEN** the profile is loaded with `CUSTOM_DOMAIN` set
- **THEN** `coordination_allowed_hosts` SHALL include the coordinator subdomain (e.g., `coord.<domain>`)
- **AND** the transport SHALL be set to `http`

#### Scenario: Profile inheritance from Railway
- **WHEN** the cloudflare profile is loaded
- **THEN** it SHALL inherit Railway settings (Postgres DSN, API host/port, workers)
- **AND** it SHALL override only Cloudflare-specific fields (allowed hosts)

---

### Requirement: Railway Custom Domain Configuration

The operator runbook SHALL document how to configure Railway to accept traffic on the custom domain, including any required DNS verification and TLS certificate setup.

#### Scenario: Railway accepts custom domain traffic
- **WHEN** the custom domain is configured in Railway's service settings
- **AND** DNS verification is complete
- **THEN** Railway SHALL serve coordinator API responses for requests to `coord.<domain>`
- **AND** the existing Railway-assigned domain SHALL continue to work as a fallback

---

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

### Requirement: Docker Compose Cloudflared Service

The docker-compose configuration SHALL include a `cloudflared` service under an optional Docker Compose profile, so operators can start the tunnel alongside other services for local testing.

#### Scenario: Start tunnel with Docker Compose profile
- **WHEN** `docker compose --profile cloudflared up` is executed
- **THEN** the `cloudflared` container SHALL start alongside postgres
- **AND** the tunnel SHALL use the mounted config and credentials files

#### Scenario: Default startup excludes tunnel
- **WHEN** `docker compose up` is executed without the `cloudflared` profile
- **THEN** the cloudflared service SHALL NOT start
- **AND** postgres and other default services SHALL start normally

---

### Requirement: SSRF Allowlist Custom Domain Support

The coordination bridge's SSRF allowlist SHALL accept Cloudflare custom domains when configured via `COORDINATION_ALLOWED_HOSTS`, with documentation examples alongside the existing Railway examples.

#### Scenario: Custom domain in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes `coord.customdomain.com`
- **THEN** the coordination bridge SHALL allow HTTP requests to `https://coord.customdomain.com`
- **AND** requests to unlisted hosts SHALL still be blocked

#### Scenario: Wildcard subdomain pattern
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes `*.customdomain.com`
- **THEN** the coordination bridge SHALL allow requests to any subdomain of `customdomain.com`

---

### Requirement: Tunnel Health Verification

The operator runbook SHALL include verification steps to confirm connectivity works correctly through both the DNS proxy path and the tunnel path.

#### Scenario: Health check through Cloudflare proxy
- **WHEN** the operator runs `curl https://coord.<domain>/health`
- **THEN** the response SHALL be HTTP 200 with a valid health payload
- **AND** the response SHALL include a `CF-Ray` header

#### Scenario: Health check through tunnel
- **WHEN** the tunnel is running and the operator runs `curl https://coord.<domain>/health`
- **THEN** the response SHALL be HTTP 200 served from the local coordinator
- **AND** the response SHALL include a `CF-Ray` header

#### Scenario: MCP SSE through tunnel
- **WHEN** a cloud agent connects to `https://mcp.<domain>/sse` through the tunnel
- **THEN** the SSE connection SHALL be established successfully
- **AND** the agent SHALL be able to send and receive MCP messages

---

## MODIFIED Requirements

### Requirement: SSRF Allowlist Documentation

The coordination bridge MUST document how to configure `COORDINATION_ALLOWED_HOSTS` for cloud deployment URLs, covering Railway domains, Cloudflare custom domains, and wildcard patterns.

#### Scenario: Cloud URL in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes the deployment hostname (Railway or custom domain)
- **THEN** the coordination bridge SHALL allow HTTP requests to that host
- **AND** requests to unlisted hosts SHALL still be blocked

#### Scenario: Cloudflare custom domain in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes a Cloudflare custom domain
- **THEN** the coordination bridge SHALL allow HTTP requests to that domain
- **AND** the existing Railway hostname support SHALL remain unchanged
