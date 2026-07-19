# Migrating the Coordinator from Railway to a Local Box

This runbook moves the coordinator off Railway and onto a machine you control,
while keeping it reachable to cloud agents (Claude Code Web, Codex/Gemini cloud)
at the **same URL** (`coord.<yourdomain>`). Because the hostname does not change,
**no cloud agent needs reconfiguration** — the cutover is a data copy plus a DNS
origin swap.

Pairs with:
- [`cloudflare-setup.md`](cloudflare-setup.md) — the tunnel + DNS mechanics.
- [`cloudflare-access-setup.md`](cloudflare-access-setup.md) — the security layer (service tokens + origin verification) to enable during this move.
- [`cloud-deployment.md`](cloud-deployment.md) — the overall architecture and env-var reference.

## Roles: Tailscale vs Cloudflare (read first)

- **Cloudflare Tunnel = the public path for cloud agents.** Claude Code Web and
  other cloud agents run in ephemeral containers that **cannot join your
  tailnet**, so the API must stay publicly reachable. The tunnel is
  outbound-only (no inbound ports on your router) and Cloudflare Access gates it.
- **Tailscale = the private path for you.** Admin access, the OpenBao/vault UI,
  the MCP HTTP transport, Postgres, and Prometheus should be reached over
  Tailscale, **not** published on the tunnel.

## Prerequisites on the local box

- Docker + Docker Compose (for the ParadeDB Postgres + optional stack).
- `uv` (or Docker) to run the coordinator.
- PostgreSQL client tools **16+** (`psql`, `pg_dump`, `pg_restore`) — the
  migration script uses them. Match or exceed Railway's server major version.
- `cloudflared`, a Cloudflare account with your domain, and (recommended)
  Tailscale installed and joined.

---

## Phase 1 — Stand up local Postgres

```bash
cd agent-coordinator
docker compose up -d postgres          # ParadeDB on localhost:54322
docker compose ps                      # wait for (healthy)
```

Local DSN (default): `postgresql://postgres:postgres@localhost:54322/postgres`
(set a strong password for a real deployment; keep Postgres bound to the Docker
network / localhost — never publish it on the tunnel).

> The stack applies schema two ways — `./database/migrations` is mounted into
> `docker-entrypoint-initdb.d`, and the app re-runs `schema_migrations` at
> startup. The migration script restores with `pg_restore --clean --if-exists`,
> so it safely **replaces** any pre-seeded schema with an exact copy of Railway.

## Phase 2 — Copy the database (trial run first)

Grab the Railway Postgres DSN (Railway dashboard → the Postgres service →
*Connect* → the public/proxy connection string).

```bash
export SOURCE_DSN='postgresql://<user>:<pass>@<railway-host>:<port>/railway'
export TARGET_DSN='postgresql://postgres:postgres@localhost:54322/postgres'

# 1) Dry run — preflight + show source row counts, make NO changes:
make migrate-to-local SOURCE_DSN="$SOURCE_DSN" TARGET_DSN="$TARGET_DSN" MIGRATE_FLAGS=--dry-run

# 2) Real copy — dump, restore (--clean), and verify per-table row counts:
make migrate-to-local SOURCE_DSN="$SOURCE_DSN" TARGET_DSN="$TARGET_DSN"
```

The script (`agent-coordinator/scripts/migrate_railway_to_local.sh`):
- refuses a non-local `TARGET_DSN` unless `--force` (prevents restoring *onto*
  Railway by mistake),
- performs a full logical copy including the `schema_migrations` tracker, and
- **verifies** by comparing exact per-table row counts source-vs-target,
  exiting non-zero on any mismatch.

Do this trial copy days ahead to shake out version/extension issues. You will
run it **once more** at cutover for the final, up-to-date data.

## Phase 3 — Recreate env and secrets locally

Reproduce the vars that lived in the Railway dashboard (see
[`agent-coordinator/CLAUDE.md`](../agent-coordinator/CLAUDE.md) for the full
list). At minimum:

```bash
export DB_BACKEND=postgres
export POSTGRES_DSN="$TARGET_DSN"
export COORDINATOR_PROFILE=cloudflare
export COORDINATION_API_KEYS=...                 # ROTATE during the move
export COORDINATION_API_KEY_IDENTITIES='{...}'
export COORDINATOR_SSE_SIGNING_KEY=...           # required for SSE (fail-closed)
export COORDINATION_ALLOWED_HOSTS='coord.<yourdomain>'
# GITHUB_PAT, LANGFUSE_*, notification vars as applicable
```

- **Rotate the API keys** now — they have been sitting in the Railway dashboard.
  `python scripts/setup_cloud.py --domain coord.<yourdomain>` regenerates them
  and writes `.env.cloud`.
- Prefer the **OpenBao** backend (`BAO_ADDR=...`) or a gitignored `.env` for
  secrets; never commit them.
- **Enable Cloudflare Access** origin verification (`CF_ACCESS_TEAM_DOMAIN`,
  `CF_ACCESS_AUD`) — see [`cloudflare-access-setup.md`](cloudflare-access-setup.md).

Smoke-test locally **before** touching DNS:

```bash
# start the API (or: docker compose --profile api up -d --build coordinator-api)
curl -s localhost:8081/live && echo
curl -s localhost:8081/ready && echo     # 503 if DB down — good signal
curl -s localhost:8081/health && echo
```

## Phase 4 — Cloudflare Tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create coordinator            # note the tunnel UUID
# place the generated <uuid>.json where cloudflared/config.yaml expects it
# (agent-coordinator/cloudflared/config.yaml already routes coord.* -> :8081)
cloudflared tunnel route dns coordinator coord.<yourdomain>
docker compose --profile cloudflared up -d cloudflared
```

The bundled `cloudflared/config.yaml` publishes **only** `coord.<yourdomain>`.
MCP and vault are intentionally left off the public tunnel (reach them over
Tailscale).

## Phase 5 — Cutover checklist (the DNS swap)

Downtime is the window between the final data sync and DNS propagation. Keep it
small by syncing immediately before the flip.

1. [ ] Announce a short maintenance window (writes will briefly fail).
2. [ ] (Optional) Pause Railway writers, or accept that in-flight writes during
       the window may be lost — the coordinator's operations are idempotent/retry-tolerant.
3. [ ] **Final data sync:** re-run `make migrate-to-local ...` (Phase 2, step 2)
       so the local DB has the latest rows. Confirm the verify step is all `[ok]`.
4. [ ] Confirm the local API is healthy behind the tunnel:
       `curl -s https://coord.<yourdomain>/health` (health is Access-exempt).
5. [ ] **Repoint DNS:** `coord.<yourdomain>` currently CNAMEs to Railway.
       `cloudflared tunnel route dns` (Phase 4) repoints it to
       `<uuid>.cfargotunnel.com`. Verify in the Cloudflare DNS dashboard that the
       `coord` record now targets the tunnel and is **Proxied**.
6. [ ] Verify from a cloud session with a service token:
       ```bash
       curl -si https://coord.<yourdomain>/locks/status/x \
         -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
         -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" | head -1
       ```
7. [ ] Run the bundled probe: `python skills/coordination-bridge/scripts/check_coordinator.py --url https://coord.<yourdomain>`
8. [ ] Add the Cloudflare **rate-limiting** rule (the app has none) — see the Access doc §4.
9. [ ] Watch logs / audit trail for a clean first hour.

`COORDINATION_API_URL` stays `https://coord.<yourdomain>`, so no agent config
changes.

## Phase 6 — Decommission Railway

Only after the local instance is confirmed healthy for a day or two:

1. [ ] Take a final `pg_dump` of the Railway DB and archive it offline.
2. [ ] Delete the Railway API + Postgres services (or pause billing).
3. [ ] Revoke the **old** coordinator API keys (you rotated in Phase 3).
4. [ ] Remove `*.railway.app` from allowlists if no longer needed
       (`.claude/settings.json`, `docs/cross-repo-setup.md`).

## Rollback

If the local instance misbehaves during or shortly after cutover:

1. Repoint `coord.<yourdomain>` DNS back to the Railway CNAME target.
2. If Railway kept serving during the window, its data is authoritative — no
   restore needed. If you paused Railway writers, replay/accept the small gap.
3. Because the local copy was additive (Railway untouched by the script — it
   only *reads* the source), rolling back is a DNS change, not a data restore.

## Notes

- **Extensions.** Both sides run ParadeDB (`paradedb/paradedb`), so `pg_search`
  / `pgvector` match. If you ever restore into stock Postgres, install the
  extensions first or the restore will error on `CREATE EXTENSION`.
- **Version skew.** Use a `pg_dump` whose major version ≥ the Railway server;
  an older client dumping a newer server can fail.
- **Langfuse / ClickHouse** (if used) are separate stores — migrate them on
  their own tracks; this runbook covers the coordinator Postgres only.
