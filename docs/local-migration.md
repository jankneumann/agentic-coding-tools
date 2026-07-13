# Coordinator Migration: Railway → Local (Cloudflare Tunnel)

Runbook for moving the Coordination API and its Postgres state from Railway to a
local always-on box, while keeping the coordinator reachable from the general
internet for cloud agents (Claude Code Web, Codex Cloud, Gemini Cloud).

Companion docs:

- [Cloudflare Domain Setup](cloudflare-setup.md) — tunnel creation, DNS, WAF options (referenced throughout)
- [Cloud Deployment Guide](cloud-deployment.md) — the Railway architecture being replaced
- [OpenBao Secret Management](openbao-secret-management.md) — local secret storage

## Target Architecture

```
Cloud agents (Claude Web, Codex Cloud)            You (laptop / phone)
        │  HTTPS + X-API-Key                             │
        ▼                                                ▼
Cloudflare edge (WAF, rate limit)                    Tailscale
        │ tunnel (outbound-only from local box)          │
        ▼                                                ▼
┌──────────────────────── local box ─────────────────────────┐
│  cloudflared ──▶ coordinator-api :8081                      │
│                        │                                    │
│                  postgres :54322   (localhost only)         │
│                  langfuse :3050    (Tailscale only)         │
│                  openbao  :8200    (Tailscale only)         │
└─────────────────────────────────────────────────────────────┘
```

Two networks, two audiences:

- **Cloudflare Tunnel** serves *cloud agents*. It is an outbound-only
  connection from the local box to Cloudflare's edge — no inbound firewall
  ports are opened. Only the coordinator HTTP API is published.
- **Tailscale** serves *you*: SSH, `psql`, the Langfuse UI, OpenBao. Nothing
  admin-facing goes through the tunnel.

## Security Checklist

Work through this before cutover. Items marked **(built-in)** already exist in
the codebase and only need verification.

### Application layer (built-in)

- [ ] **API-key auth** — every write endpoint requires a key
      (`verify_api_key` in `agent-coordinator/src/coordination_api.py`;
      accepts `X-API-Key`, `Authorization: Bearer`, or
      `X-Coordinator-API-Key`). Verify `COORDINATION_API_KEYS` and
      `COORDINATION_API_KEY_IDENTITIES` are set — an empty key list means
      all authenticated endpoints reject requests, but double-check you
      have not fallen back to the compose default `dev-key-001`.
- [ ] **Per-key identities** feed agent profiles, trust levels, the Cedar
      policy engine, guardrails, and the audit log. Map one key per agent so
      the audit trail stays attributable.
- [ ] **SSE auth is fail-closed** — set `COORDINATOR_SSE_SIGNING_KEY`
      (e.g. `openssl rand -hex 32`) to enable live SSE for kanban-viz;
      leaving it unset returns 503 from `/events/auth` and clients fall
      back to polling.

### Keys and secrets

- [ ] **Rotate API keys at cutover.** The current keys have lived in the
      Railway dashboard; treat them as burned once the migration is done.
      Generate fresh keys with `openssl rand -hex 32` per agent, or run
      `make cloud-setup DOMAIN=coord.yourdomain.com` (without `RAILWAY=1`)
      to generate keys and write `.env.cloud`.
- [ ] **Tunnel credentials** — `~/.cloudflared/<tunnel-uuid>.json` is the key
      to your hostname. Keep it out of git
      (`agent-coordinator/cloudflared/.gitignore` already excludes `*.json`)
      and `chmod 600` it.
- [ ] **Change compose defaults** on a long-lived box: the Postgres
      `postgres/postgres` password, and Langfuse's `NEXTAUTH_SECRET`, `SALT`,
      and admin password (all have `-change-me` defaults in
      `agent-coordinator/docker-compose.yml`).
- [ ] **OpenBao dev mode is not for production.** The compose service runs
      `server -dev` with a static root token. Fine on localhost/Tailscale;
      never publish it through the tunnel (see next section). If you rely on
      OpenBao for real secrets, switch to a persistent server with proper
      unseal — see [openbao-secret-management.md](openbao-secret-management.md).

### Cloudflare edge

- [ ] **WAF skip rule for Bot Fight Mode — mandatory with a tunnel.**
      [cloudflare-setup.md §6](cloudflare-setup.md#6-proxy-mode-for-api-hostnames)
      lists "DNS only (grey cloud)" as Option A, but tunnel CNAMEs
      (`<uuid>.cfargotunnel.com`) only resolve through Cloudflare's proxy
      (orange cloud), so that option is unavailable here. Without a skip
      rule, Python HTTP clients get 403 `error code: 1010`. Create the
      Option B or C rule *before* cutover and place it above any managed
      rulesets:

      | Field | Value |
      |-------|-------|
      | Rule name | `Skip Bot Fight for Coordinator API` |
      | Expression | `(http.host eq "coord.yourdomain.com")` |
      | Action | Skip → Bot Fight Mode, Super Bot Fight Mode |

- [ ] **Rate limiting.** The app has no built-in rate limiting, and Railway's
      Fastly shield goes away. Add a Cloudflare rate-limiting rule on
      `coord.yourdomain.com` — agents are few and known, so a generous
      per-IP limit (e.g. 300 requests/minute) catches abuse without
      touching legitimate traffic.
- [ ] **SSL/TLS mode "Full (strict)"** stays as-is; the tunnel encrypts
      edge → origin itself.

### Tunnel ingress (publish the minimum)

- [ ] **Only expose the coordinator API.** The tunnel config template
      (`agent-coordinator/cloudflared/config.yaml`) publishes only
      `coord.<domain>` → `http://localhost:8081`. Do not add ingress rules
      for OpenBao (dev-mode root token = handing out your secret store),
      Postgres, or Langfuse. The MCP SSE hostname (`mcp.<domain>` → `:8082`)
      is included commented-out — enable it only if cloud agents actually
      use MCP-over-SSE, and note the coordinator MCP server has no
      API-key gate of its own.
- [ ] **Postgres stays private — bind it to loopback explicitly.** Cloud
      agents go through the HTTP API only; this is an *improvement* over
      Railway, where MCP + direct-DB mode required a public TCP proxy.
      But note the compose default `ports: "54322:5432"` publishes Postgres
      on **all host interfaces** (Docker inserts its own iptables rules,
      which bypass simple ufw setups). Set
      `AGENT_COORDINATOR_DB_PORT=127.0.0.1:54322` in `agent-coordinator/.env`
      so the mapping becomes `127.0.0.1:54322:5432` (loopback only), and
      verify with `ss -tlnp | grep 54322`. Reach it remotely over Tailscale
      via SSH port-forward if needed.

### Host

- [ ] **Firewall**: allow the Tailscale interface, deny unsolicited inbound
      on the WAN interface (e.g. `ufw allow in on tailscale0`,
      `ufw default deny incoming`). The tunnel needs no inbound rules.
- [ ] **Auto-start + restart**: run the compose stack and tunnel under
      supervision so a reboot or crash self-heals (see Phase 3 Option C
      and Phase 5).
- [ ] **Keep `cloudflared` updated** — it is your internet-facing surface.

### Availability (now your problem, not Railway's)

- [ ] External uptime monitor on `https://coord.yourdomain.com/health`.
- [ ] Optionally wire the coordinator's webhook notification channel
      (`NOTIFICATION_CHANNELS=webhook`, `WEBHOOK_URL=https://ntfy.sh/<topic>`)
      so the watchdog can alert your phone.
- [ ] A box that sleeps is a coordinator that is down — use an always-on
      machine or disable suspend.

## Migration Steps

### Phase 1 — Stand up the local stack (Railway still serving)

```bash
cd agent-coordinator

# Postgres with ParadeDB; migrations auto-apply on first init of the volume
docker compose up -d postgres

# Generate fresh API keys + .env.cloud (manual mode — no Railway push)
make cloud-setup DOMAIN=coord.yourdomain.com
source .env.cloud
```

**`.env.cloud` contains only the client-side variables** (agent URL, keys,
aliases). The *server-side* values — `COORDINATION_API_KEYS` and
`COORDINATION_API_KEY_IDENTITIES` — are printed to stdout by
`make cloud-setup` under "Railway env vars (set in dashboard...)". Persist
them into `agent-coordinator/.env` (gitignored; docker compose reads it for
variable interpolation), mapped to the compose operator variables:

```bash
# agent-coordinator/.env — values copied from the cloud-setup output
COORDINATOR_API_KEYS=<printed COORDINATION_API_KEYS value>
COORDINATOR_API_KEY_IDENTITIES=<printed COORDINATION_API_KEY_IDENTITIES JSON>
# In-container client key for the HTTP loopback (e.g. /gen-eval/run spawns the
# gen_eval CLI, which calls the coordinator's own API as a client). Must be ONE
# of the keys in COORDINATOR_API_KEYS above — otherwise it defaults to
# dev-key-001, which the rotated server now rejects, and loopback calls get 401.
COORDINATOR_CLIENT_API_KEY=<one key from COORDINATOR_API_KEYS>
# Bind Postgres to loopback only (see security checklist)
AGENT_COORDINATOR_DB_PORT=127.0.0.1:54322
```

Skipping this step is the dev-key trap: without `COORDINATOR_API_KEYS` set,
compose falls back to `dev-key-001` and the public API will accept that
well-known key while rejecting the rotated keys you distribute to agents.
The mirror trap is setting `COORDINATOR_API_KEYS` but *not*
`COORDINATOR_CLIENT_API_KEY`: the server stops accepting `dev-key-001`, yet the
in-container loopback client still sends it, so `/gen-eval/run` and other
self-calls fail with 401 until the client key is pinned to a rotated key.

```bash
docker compose --profile api up -d --build coordinator-api

curl -s localhost:8081/health
# Expected: {"status":"ok","db":"connected",...}

# Confirm the rotated keys are live and the dev fallback is NOT:
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-API-Key: $COORDINATION_API_KEY" localhost:8081/profiles/me   # 200
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-API-Key: dev-key-001" localhost:8081/profiles/me             # 401
```

### Phase 2 — Copy state from Railway

The local volume already has the schema (migrations ran on first init), so use
a **data-only** dump to avoid DDL conflicts:

```bash
# From Railway (public connection string: Settings > Networking > Public URL)
pg_dump "postgresql://postgres:<pw>@<railway-public-host>:<port>/coordinator" \
  --data-only --disable-triggers -Fc -f coordinator-data.dump

pg_restore \
  -d "postgresql://postgres:postgres@localhost:54322/postgres" \
  --data-only --disable-triggers coordinator-data.dump
```

Caveats:

- `--disable-triggers` requires superuser on the target — the local
  `postgres` user qualifies.
- If the Railway schema is *behind* local `main` (migrations added since the
  last deploy), restore may hit missing-column errors on new tables; restore
  table-by-table (`pg_restore -t <table>`) for the state you care about.
- Skipping this phase entirely is legitimate: file locks and work-queue
  entries are ephemeral. Episodic/procedural memory and the audit log are
  the tables worth carrying over.

### Phase 3 — Create the tunnel

Follow [cloudflare-setup.md §3](cloudflare-setup.md#3-named-tunnel-to-local-machine-testing-path); summary:

```bash
cloudflared tunnel login
cloudflared tunnel create coordinator
# note the tunnel UUID; credentials land at ~/.cloudflared/<uuid>.json
```

**DNS:** `cloudflared tunnel route dns coordinator coord.yourdomain.com`
only works for hostnames with **no existing record** — it creates a new
CNAME and errors out (or leaves the old record winning) when
`coord.yourdomain.com` already has the Railway CNAME from
[cloudflare-setup.md](cloudflare-setup.md). Since this is a migration,
that record exists — so *don't* route DNS here. Leave the hostname
pointing at Railway for now; repointing it **is** the cutover (Phase 4).

Fill `TUNNEL_UUID`, `CREDENTIALS_FILE`, and `CUSTOM_DOMAIN` into
`agent-coordinator/cloudflared/config.yaml`, then run the tunnel:

```bash
# Option A: alongside the stack (development)
docker compose --profile cloudflared up -d

# Option B: standalone
cloudflared tunnel --config agent-coordinator/cloudflared/config.yaml run

# Option C: systemd service (recommended for an always-on box).
# Pass --config explicitly: `sudo` changes $HOME, so without it the
# installed unit looks for ~/.cloudflared/config.yml as root and can start
# without your edited ingress/credentials — the tunnel runs but never
# serves coord.*. Use an absolute path (also for credentials-file inside
# the config).
sudo cloudflared --config /absolute/path/to/agent-coordinator/cloudflared/config.yaml service install
sudo systemctl enable --now cloudflared
systemctl status cloudflared   # verify it loaded the right config
```

### Phase 4 — Cutover

If agents already point at `coord.yourdomain.com` (the recommended setup from
[cloudflare-setup.md](cloudflare-setup.md)), cutover is one DNS edit, done
manually: in **Cloudflare Dashboard → DNS → Records**, change the existing
`coord` CNAME's target from `your-service.up.railway.app` to
`<tunnel-uuid>.cfargotunnel.com` and set it to **Proxied** (orange cloud —
tunnel CNAMEs only resolve through the proxy). Do not use
`cloudflared tunnel route dns` for this — it cannot repoint an existing
record (see Phase 3). Agents need **zero configuration changes** — same URL,
same header.

If any agent still points at the raw `*.up.railway.app` URL, update it now to
the custom domain (last time you will ever touch it):

```bash
export COORDINATION_API_URL="https://coord.yourdomain.com"
export COORDINATION_API_KEY="<new-agent-key>"
export COORDINATION_ALLOWED_HOSTS="coord.yourdomain.com"
```

Distribute the rotated keys generated in Phase 1 to each agent environment
(Claude Code Web environment variables, Codex Cloud env, `.env.cloud` +
aliases for local CLIs).

Verify end to end:

```bash
curl -I https://coord.yourdomain.com/health
# 200 + a CF-Ray header (traffic is via Cloudflare proxy)

make cloud-verify DOMAIN=coord.yourdomain.com

python3 skills/coordination-bridge/scripts/coordination_bridge.py detect \
  --http-url "https://coord.yourdomain.com" --api-key "<new-key>"
```

Then confirm a real cloud-agent session can acquire/release a lock and that
the audit log attributes it to the right identity.

### Phase 5 — Harden and supervise

- Move the tunnel to the systemd service (Phase 3 Option C) if you started
  with compose.
- Ensure the compose services restart on boot: `restart: unless-stopped` is
  set on `cloudflared`; add a systemd unit (or `restart: unless-stopped`
  overrides) for `postgres` and `coordinator-api`, or start the stack from
  a boot-time unit running `docker compose --profile api --profile cloudflared up -d`.
- Point an uptime monitor at `/health`.

### Phase 6 — Decommission Railway

1. Keep Railway alive for a day or two as the rollback target. Rollback is a
   single CNAME flip back to `your-service.up.railway.app` (see
   [cloudflare-setup.md §4](cloudflare-setup.md#4-switching-between-paths)) —
   but note DB writes made locally after cutover will not exist on Railway.
2. Take one final full dump of the Railway database before deleting anything:
   `pg_dump ... -Fc -f railway-final-backup.dump`.
3. Delete the Railway services and volume; remove the now-unused Railway keys
   from any agent environment that still has them.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 403 `error code: 1010` from agents | Bot Fight Mode blocking non-browser clients; DNS-only mode is unavailable with a tunnel | WAF skip rule ([checklist](#cloudflare-edge)) |
| 502 through `coord.yourdomain.com` | Tunnel up but coordinator not listening on `:8081` | `docker compose ps`, `curl localhost:8081/health` on the box |
| 530 / `error 1033` | Tunnel itself down | `cloudflared tunnel info coordinator`; check systemd/compose logs |
| SSE streams drop ~100s | Cloudflare proxy idle timeout (always applies via tunnel) | Coordinator SSE keepalives; polling fallback covers the gap |
| `pg_restore` errors on duplicate keys | Restoring into a non-empty table | Truncate the target tables first, or restore table-by-table |
| Agents work locally but not from cloud | `COORDINATION_ALLOWED_HOSTS` missing the new hostname | Set to `coord.yourdomain.com` (SSRF allowlist, no scheme) |
