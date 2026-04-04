# Cloudflare Domain Setup

Expose coordinator services through stable custom subdomains via Cloudflare. Two deployment paths are supported:

1. **DNS Proxy to Railway** (production) — Cloudflare proxies traffic to Railway's backend
2. **Named Tunnel to local machine** (development/testing) — Cloudflare Tunnel exposes local services

Both paths use the same subdomains. Switching between them is a DNS record change — no agent configuration changes needed.

## Prerequisites

- Cloudflare account ([dash.cloudflare.com](https://dash.cloudflare.com))
- A registered domain (any registrar)
- Railway deployment already working (see [cloud-deployment.md](cloud-deployment.md))

## 1. Add Domain to Cloudflare

1. Log into [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Click **Add a site** and enter your domain
3. Select the **Free** plan (sufficient for DNS proxy + tunnel)
4. Cloudflare will scan existing DNS records — review and confirm
5. Update your domain's nameservers at your registrar to the Cloudflare-assigned nameservers
6. Wait for nameserver propagation (usually 5-30 minutes, can take up to 24 hours)
7. Verify domain is active in the Cloudflare dashboard (status: "Active")

### SSL/TLS Configuration

1. Go to **SSL/TLS** > **Overview** in the Cloudflare dashboard
2. Set encryption mode to **Full (Strict)**
   - This encrypts traffic both from client to Cloudflare edge AND from Cloudflare to Railway
   - Railway provides valid TLS certificates, so "Full (Strict)" works without extra configuration

## 2. DNS Proxy to Railway (Production Path)

This path routes traffic through Cloudflare to your existing Railway deployment.

### 2a. Configure Railway Custom Domain

1. In Railway dashboard, go to your Coordination API service
2. Click **Settings** > **Networking** > **Custom Domain**
3. Add your subdomain: `coord.yourdomain.com`
4. Railway will provide a CNAME target (e.g., `your-service.up.railway.app`)
5. Complete any DNS verification Railway requires

### 2b. Create Cloudflare DNS Records

In Cloudflare dashboard > **DNS** > **Records**, create:

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `coord` | `your-service.up.railway.app` | Proxied (orange cloud) |

**Important**: Keep the orange cloud (Proxy) enabled. This routes traffic through Cloudflare's edge network, providing:
- Automatic TLS certificate management
- DDoS protection
- Future WAF/rate limiting capabilities

### 2c. Verify

```bash
# Should return 200 with CF-Ray header
curl -I https://coord.yourdomain.com/health

# Check for Cloudflare headers
curl -sI https://coord.yourdomain.com/health | grep -i "cf-ray"
```

### 2d. Update Agent Configuration

Cloud agents should use the custom domain instead of the Railway-assigned URL:

```bash
# Before (Railway URL)
COORDINATION_API_URL=https://your-app.up.railway.app

# After (custom domain)
COORDINATION_API_URL=https://coord.yourdomain.com
```

The `COORDINATION_ALLOWED_HOSTS` environment variable accepts wildcard patterns:

```bash
# Allow all subdomains of your domain
COORDINATION_ALLOWED_HOSTS="*.yourdomain.com"

# Or specific subdomains
COORDINATION_ALLOWED_HOSTS="coord.yourdomain.com,mcp.yourdomain.com"
```

### Agent Config Examples

**Claude Web / Claude Code (cloud):**
```bash
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=your-api-key
```

**Codex Cloud:**
```bash
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=your-api-key
```

**Gemini Cloud:**
```bash
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=your-api-key
```

These configurations are identical regardless of whether the backend is Railway (DNS proxy) or a local machine (tunnel). Only the DNS record determines where traffic goes.

## 3. Named Tunnel to Local Machine (Testing Path)

This path routes traffic through a Cloudflare Tunnel to services running on your laptop or development machine.

### 3a. Install cloudflared

```bash
# macOS
brew install cloudflared

# Linux (Debian/Ubuntu)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

### 3b. Create a Named Tunnel

```bash
# Authenticate with Cloudflare
cloudflared tunnel login

# Create a named tunnel
cloudflared tunnel create coordinator

# Note the tunnel UUID from the output (e.g., a1b2c3d4-e5f6-7890-abcd-ef1234567890)
```

### 3c. Configure DNS for Tunnel

Create CNAME records pointing to the tunnel:

```bash
cloudflared tunnel route dns coordinator coord.yourdomain.com
cloudflared tunnel route dns coordinator mcp.yourdomain.com
cloudflared tunnel route dns coordinator vault.yourdomain.com
```

Or manually in Cloudflare dashboard — create CNAME records pointing to `<tunnel-uuid>.cfargotunnel.com`.

**Note**: When switching from Railway DNS proxy to tunnel, update the existing CNAME record targets. The subdomain names stay the same.

### 3d. Configure Tunnel Routing

Edit `agent-coordinator/cloudflared/config.yaml`:

```yaml
tunnel: <your-tunnel-uuid>
credentials-file: /path/to/credentials/<tunnel-uuid>.json

ingress:
  - hostname: coord.yourdomain.com
    service: http://localhost:8081
  - hostname: mcp.yourdomain.com
    service: http://localhost:8082
  - hostname: vault.yourdomain.com
    service: http://localhost:8200
  - service: http_status:404
```

Replace `<your-tunnel-uuid>` and update the credentials file path. The credentials file was created during `cloudflared tunnel create` (typically at `~/.cloudflared/<tunnel-uuid>.json`).

### 3e. Run the Tunnel

**Option A: Docker Compose (recommended for development)**

```bash
cd agent-coordinator
docker compose --profile cloudflared up -d
```

This starts the tunnel alongside PostgreSQL. The cloudflared service mounts the config and credentials files automatically.

**Option B: Standalone daemon**

```bash
cloudflared tunnel --config agent-coordinator/cloudflared/config.yaml run
```

**Option C: System service (for always-on server)**

Linux (systemd):
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

macOS (launchd):
```bash
sudo cloudflared service install
# Starts automatically on login
```

Both methods use the config file at the default location (`/etc/cloudflared/config.yml` or `~/.cloudflared/config.yml`).

### 3f. Verify Tunnel

```bash
# Health check through tunnel
curl -I https://coord.yourdomain.com/health
# Should return 200 with CF-Ray header

# MCP SSE connectivity (should establish SSE stream)
curl -N https://mcp.yourdomain.com/sse
# Should receive SSE events (Ctrl+C to stop)

# OpenBao status
curl https://vault.yourdomain.com/v1/sys/health
```

## 4. Switching Between Paths

To switch from Railway (DNS proxy) to tunnel (or vice versa):

1. Update the CNAME target for `coord.yourdomain.com`:
   - **Railway**: point to `your-service.up.railway.app`
   - **Tunnel**: point to `<tunnel-uuid>.cfargotunnel.com`
2. Wait for DNS propagation (usually seconds with Cloudflare proxy enabled)
3. No agent configuration changes needed — the URL stays the same

## 5. Secret Management

### Current Strategy (Railway + Local Dev)

| Environment | Secret Storage | Notes |
|-------------|---------------|-------|
| Production (Railway) | Railway dashboard env vars | Per-service, encrypted at rest |
| Local development | `.env` files + OpenBao (docker-compose) | `.env` is gitignored |
| Tunnel credentials | `~/.cloudflared/` or volume mount | Never committed to git |

### Tunnel Credentials Security

- The `agent-coordinator/cloudflared/.gitignore` excludes `*.json` and `*.pem` files
- Store credentials at `~/.cloudflared/` (the default location)
- For Docker Compose, mount credentials as a volume (not copied into the image)

## Troubleshooting

### DNS not resolving
- Verify nameservers were updated at your registrar
- Check Cloudflare dashboard shows domain as "Active"
- DNS propagation can take up to 24 hours (usually much faster)

### 502 Bad Gateway through Cloudflare
- Railway service is down or restarting — check Railway dashboard
- For tunnel: local coordinator is not running on expected port

### SSL/TLS errors
- Ensure SSL mode is "Full (Strict)" in Cloudflare dashboard
- Railway custom domain TLS certificate may take a few minutes to provision

### MCP SSE timeout through proxy
- Cloudflare has a 100-second idle timeout for HTTP connections
- The MCP SSE endpoint should send keepalive events periodically
- If connections drop, check the coordinator's SSE keepalive configuration

### Tunnel not starting
- Verify credentials file exists and is readable
- Check tunnel UUID matches the one in config.yaml
- Run `cloudflared tunnel info coordinator` to check tunnel status
