# Agent coordinator on GX-10

A separate compose project (`aca-gx10-coord`) that joins the analyzer's
networks and reuses its Langfuse, OpenBao and Squid. Three containers run here:
`coordinator-postgres`, `coordinator-api`, `cloudflared`.

Six services from `agent-coordinator/docker-compose.yml` are deliberately
**absent**: `openbao`, `langfuse-web`, `langfuse-worker`,
`langfuse-clickhouse`, `langfuse-redis`, `langfuse-minio`. The laptop compose
runs its own copies; here they belong to the analyzer.

Read these two in the analyzer repo before changing anything here:

- [`docs/GX10_HANDOFF.md`][ho] — host state, the install prerequisites that
  need credentials, and every open task. Start here.
- [`docs/CASE_STUDIES.md` → GX-10 Production Bring-Up][cs] — the specific ways
  this host punishes assumptions. Every file in this directory is shaped by it.

[ho]: https://github.com/jankneumann/agentic-content-analyzer/blob/main/docs/GX10_HANDOFF.md
[cs]: https://github.com/jankneumann/agentic-content-analyzer/blob/main/docs/CASE_STUDIES.md

## What the deployment assumes

| Assumption | Why |
|---|---|
| The analyzer runtime is up | It owns `aca-gx10_application` and `aca-gx10_egress`, renders the secrets, and hosts Langfuse. The unit declares `Requires=` and `PartOf=aca-gx10.service`. |
| Nothing is published to the host | The only inbound path is the Cloudflare tunnel, terminating at `coordinator-api` over the internal network. |
| Images are pinned `tag@sha256` | `GX10_COORD_IMAGE`, `GX10_COORD_POSTGRES_IMAGE`, `GX10_CLOUDFLARED_IMAGE` in `/etc/aca/gx10-images.env`. The compose fails closed on an unset one. `GX10_NODE_IMAGE` builds the kanban board and fails closed the same way. |
| The container uid is 10001 | Pinned in the Dockerfile so `make ownership` has a number to chown to. |

## One-time prerequisites

These need credentials or a UI and cannot be scripted from here.

1. **A Langfuse project for the coordinator.** The analyzer's headless init
   seeds exactly one project, so the second is created once via the Langfuse
   API or UI. Store its two keys at `secret/coordinator/gx10/runtime` as
   `langfuse_public_key` and `langfuse_secret_key`.
2. **An OpenBao AppRole** scoped to read `secret/coordinator/gx10/*` only —
   not the analyzer's path. Write its role id and secret id to
   `/etc/aca/gx10/coordinator-role-id` and `.../coordinator-secret-id`, mode
   0600 root. The secrets unit loads them as systemd credentials so they never
   enter the environment.
3. **The remaining secrets** at the same path: `postgres_password`,
   `coordination_api_keys`, `coordination_api_key_identities`,
   `coordination_api_key`, `sse_signing_key`, and the Access application's
   `cf_access_team_domain` / `cf_access_aud` (step 5). The compose forces
   Access verification on, so without the last two the API refuses to start.
4. **A Cloudflare tunnel** — `cloudflared tunnel create gx10-coordinator` —
   with its credentials JSON at `/run/aca/gx10/cloudflared/credentials.json`
   (0600) and a config whose only ingress rule is the coordinator API.
   `GX10_COORD_TUNNEL_CONFIG` points the renderer at the reviewed config.
5. **A Cloudflare Access application** on `coord.<domain>` with a service
   token per client (see [Cutover](#cutover-from-railway)). Without it the tunnel publishes the API with only
   `X-API-Key` in front of it, which is the weak version of this design and
   looks identical from outside until you test an unauthenticated request.
6. **A firewall rule** for the tunnel's egress. `cloudflared` holds an
   outbound connection that does not pass through Squid — a deliberate,
   documented exception to the egress policy, which is why it sits alone on
   the egress network with no route to `stateful`.

## Bring-up

```bash
sudo git -C /opt/agentic-coding-tools pull
sudo make -C /opt/agentic-coding-tools/deploy/gx10 image
sudo nano /etc/aca/gx10-images.env         # paste GX10_COORD_IMAGE
sudo make -C /opt/agentic-coding-tools/deploy/gx10 ownership
sudo make -C /opt/agentic-coding-tools/deploy/gx10 start
sudo make -C /opt/agentic-coding-tools/deploy/gx10 status
```

A code change costs a rebuild, a push, a digest pin and a restart. The
container is `read_only` with no source mount, so a `git pull` alone **cannot**
change what runs. If a fix appears to do nothing, confirm the image was
rebuilt before debugging the code.

## Things that will bite

- **`NO_PROXY` must list every host called over HTTP.** Every container here
  inherits `HTTP_PROXY=squid:3128`, and `httpx` honours it. A host missing from
  `NO_PROXY` has its request handed to Squid, which denies internal
  destinations — so a purely local call fails on our own SSRF rule.
- **The SSE heartbeat is load-bearing.** `event_stream.py` emits a `ping` every
  30 s, comfortably inside Cloudflare's idle timeout. Widen it and streams keep
  working on the LAN while silently dropping through the tunnel.
- **Never add a tunnel ingress rule for OpenBao, Postgres, ClickHouse, MinIO or
  the MCP transport.** On this host OpenBao is the real sealed instance holding
  every secret for both projects. The renderer greps the config and refuses.
- **`systemctl stop aca-gx10` stops this too.** `PartOf=` makes that explicit
  rather than leaving it to be discovered as network removal under a running
  container.
- **The frontend is static.** `apps/kanban-viz` builds to `dist/` and is served
  by the analyzer's Caddy; there is no frontend container here. See below.

## Kanban board (`/kanban/` on the analyzer's site)

The board is served by the analyzer's Caddy, behind its `basic_auth`, and
reaches this API over the shared `application` network. **The coordinator key
is never in the bundle**: Caddy injects it server-side. Anything baked into
the JavaScript is readable by whoever loads the page.

```bash
sudo make -C /opt/agentic-coding-tools/deploy/gx10 kanban
```

builds the checked-out commit (via `git archive`, so an untracked `.env.local`
cannot leak in) inside the digest-pinned `GX10_NODE_IMAGE` from
`/etc/aca/gx10-images.env`, into `/srv/aca/kanban/releases/<sha>`, then
switches the relative symlink `/srv/aca/kanban/current` to it. Caddy mounts the
parent, so a rebuild goes live without a Caddy restart. The build sets
`VITE_COORDINATOR_URL=/kanban/api`, `VITE_COORDINATOR_AUTH=proxy`, an empty key,
and `--base /kanban/`, and refuses an `index.html` that does not load assets
from `/kanban/`.

Three things the handoff's first sketch would have got wrong:

- **The board must send no `Authorization` header.** It used to send
  `Authorization: Bearer <key>` even with an empty key. An explicit header
  replaces the browser's cached basic-auth credentials, so every call would
  401 at Caddy. `VITE_COORDINATOR_AUTH=proxy` drops the header and still
  enables the write actions.
- **Stripping `X-API-Key` is not enough.** The API resolves keys in the order
  `Authorization: Bearer` → `X-Coordinator-API-Key` → `X-API-Key`. Caddy must
  delete the first two, or a client past basic auth could present another key
  that outranks the injected one. Deleting `Authorization` also keeps the
  site's basic-auth credentials from reaching the coordinator.
- **A relative API URL broke three requests.** `new URL("/kanban/api/...")`
  throws without a base; the board now resolves against the page origin.

### Analyzer side

In the analyzer's `deploy/gx10/Caddyfile`, inside the site block, beside the
`@langfuse` handle (Caddy runs path `handle`s most-specific first, so
`/kanban/api/*` wins over `/kanban/*`, and both over the catch-all):

```caddyfile
  redir /kanban /kanban/
  handle_path /kanban/api/* {
    # Separate handler, so it runs before the proxy sets the key below.
    request_header -Authorization
    request_header -X-Coordinator-API-Key
    request_header -X-API-Key
    reverse_proxy coordinator-api:8081 {
      header_up X-API-Key {$KANBAN_COORDINATOR_API_KEY}
      # The board streams /events/work over SSE; a buffering proxy hangs it.
      flush_interval -1
    }
  }
  handle_path /kanban/* {
    root * /srv/kanban/current
    try_files {path} /index.html
    file_server
  }
```

and on the `caddy` service in `docker-compose.gx10.yml`:

```yaml
    volumes:
    - /srv/aca/kanban:/srv/kanban:ro
```

Caddy's requests never transit Cloudflare, so they carry no Access assertion.
The API exempts exactly Caddy's fixed address (`CF_ACCESS_TRUSTED_PEERS=10.89.1.250`
in the compose), matched on the TCP peer rather than any forwarded header.
If the analyzer ever moves Caddy off that address, the board gets 403s.

`KANBAN_COORDINATOR_API_KEY` reaches `caddy.env` through the analyzer's
`render-secrets.sh`; where that renderer reads it from is the open decision in
the handoff's task 6.

### The kanban identity

A dedicated key, so it can be revoked alone. At
`secret/coordinator/gx10/runtime`: append it to `coordination_api_keys`, and add
`"<key>": {"agent_id": "gx10-kanban", "agent_type": "kanban_viz"}` to
`coordination_api_key_identities`. The board writes (labels, saved views, agent
kicks); those routes need only a valid key, so no extra profile is required.
Audit rows then attribute board actions to `gx10-kanban`.

### Verify once the coordinator is up

```bash
# 1. The page and its assets come from /kanban/, not the analyzer API.
curl -sku "$USER:$PASS" https://<origin>/kanban/ | grep '/kanban/assets/'
# 2. The proxy authenticates: 200 with no key sent by the client.
curl -sku "$USER:$PASS" -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' \
  -d '{"labels":[]}' https://<origin>/kanban/api/issues/list
# 3. Without basic auth, nothing: 401.
curl -sk -o /dev/null -w '%{http_code}\n' -d '{}' https://<origin>/kanban/api/issues/list
# 4. SSE is not buffered: open the board and confirm in devtools that
#    /kanban/api/events/work stays open and receives `ping` every 30 s.
```

Check (4) deliberately: the site block's `encode zstd gzip` sits in front of
every route, and whether it holds back small SSE frames has not been tested.
If it does, exclude the API path from `encode` with a `not path` matcher.
Also unverified: that `coordinator-api` resolves from the analyzer's Caddy by
service name across compose projects. This deployment already relies on the
reverse (`langfuse-web` from here), so it should, but a 502 points there first.


## Cutover from Railway

`coord.rotkohl.ai` is a DNS-only (grey-cloud) CNAME to Railway today: Railway's
certificates break behind Cloudflare's proxy, so Access could never sit in
front of it. The tunnel removes that constraint — Cloudflare terminates TLS
with its own certificate and reaches `coordinator-api` over the internal
network — so the cutover is also what closes the API-key-only gap.

Keep tunnel hostnames **one level deep** (`coord-gx10.rotkohl.ai`, never
`coord.gx10.rotkohl.ai`): a tunnel route is always proxied, and the free
Universal SSL certificate covers only `*.rotkohl.ai`.

### Decide first

- **Data.** Carried over: `seed-from-railway.sh` copies the Railway database,
  `schema_migrations` included, so the first GX-10 start applies only the
  migrations Railway has not run. Writes that land on Railway after the final
  dump are lost, which is why step 6 stops the Railway API first.
- **Keys.** If the GX-10 `coordination_api_keys` differ from Railway's, every
  client needs a new `COORDINATION_API_KEY` too. If they are the same, the
  Railway instance stays a live, Access-free door for those keys until it is
  shut down (last step).

### Steps

1. **Access application** — Zero Trust → Access → Applications → Self-hosted:
   `coord.rotkohl.ai`, path empty. Copy the **AUD tag** and the **team
   domain**. Creating it before the DNS move is harmless: it only applies once
   traffic is proxied.
2. **Service tokens, one per client** — each cloud harness, *plus one for
   local sessions* (`gx10-local`): after the move, this host's own hooks reach
   the API through Cloudflare like everyone else. Turn on the expiring-token
   notification. One policy, **Action: Service Auth**, including those
   tokens. No Bypass policy, not even for `/health`.
3. **OpenBao** — add `cf_access_team_domain` and `cf_access_aud` to
   `secret/coordinator/gx10/runtime` (`bao kv patch`, so the other fields stay).
4. **Tunnel** — `cloudflared tunnel create gx10-coordinator`; credentials to
   `/run/aca/gx10/cloudflared/credentials.json` (0600); a config with one
   ingress rule, `coord.rotkohl.ai` → `http://coordinator-api:8081`, then
   `http_status:404`; `GX10_COORD_TUNNEL_CONFIG` pointing at it.
5. **Clients** — set `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` beside
   `COORDINATION_API_KEY` in every environment, including this host's session
   environment. The coordination bridge, the HTTP proxy transport and the
   session hooks send them when both are set. Harmless against Railway, so do
   this before the switch.
6. **Freeze, seed, bring up.** Rehearse a–b on any day before; the real run
   is one sitting, and agents see an outage from (b) to step 7.

   ```bash
   # a. Anywhere with pg_dump >= Railway's server version. The DSN file holds
   #    the Railway Postgres DATABASE_PUBLIC_URL, mode 0600.
   RAILWAY_COORD_DSN_FILE=~/.railway-coord-dsn deploy/gx10/seed-from-railway.sh dump coord.dump
   deploy/gx10/seed-from-railway.sh check coord.dump   # any CHANGED/MISSING: stop
   # b. Stop the Railway coordinator *service* (not its Postgres), then re-run (a)
   #    so the final dump holds every write.
   # c. On GX-10, with the dump copied over (0600): start only Postgres, restore
   #    into the still-empty database, then hand the container back to the unit.
   sudo systemctl start aca-gx10-coordinator-secrets.service
   sudo podman-compose -p aca-gx10-coord -f /opt/agentic-coding-tools/deploy/gx10/docker-compose.coordinator.yml up -d coordinator-postgres
   sudo /opt/agentic-coding-tools/deploy/gx10/seed-from-railway.sh restore coord.dump
   sudo /opt/agentic-coding-tools/deploy/gx10/coordinator-runtime.sh down
   sudo make -C /opt/agentic-coding-tools/deploy/gx10 start   # applies the pending migrations
   # d. Once `make status` is healthy and step 8 passes: the dump holds every
   #    agent's memory and audit trail.
   shred -u coord.dump
   ```

   `restore` re-runs `check`, refuses a database that already has a schema
   (an API that started first has migrated it empty), and creates the
   `anon`/`authenticated`/`service_role` roles the row-level policies name —
   roles are cluster-level, so no `pg_dump` carries them.
7. **Switch DNS** — note the current Railway CNAME target (rollback), then
   `cloudflared tunnel route dns --overwrite-dns gx10-coordinator coord.rotkohl.ai`.
   Rollback is restoring that CNAME, grey-clouded, and restarting the Railway
   service; anything written to GX-10 in between stays behind.
8. **Prove it**:

   ```bash
   # A. No credentials: Cloudflare must answer (302/403). A 401 means the
   #    coordinator answered -- Access is NOT in front of it.
   curl -s -o /dev/null -w '%{http_code}\n' https://coord.rotkohl.ai/health
   # B. Token, no key: through Access, refused by the API (401).
   curl -s -o /dev/null -w '%{http_code}\n' -X POST https://coord.rotkohl.ai/locks/acquire \
     -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"
   # C. Both: 200.
   curl -s https://coord.rotkohl.ai/health \
     -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"
   ```

   Then start a fresh agent session and confirm the `[register_agent]` hook
   line reports success. The hooks swallow errors by design, so a missing
   token shows up only as that line failing.
9. **Retire Railway** — once stable, remove the coordinator's public Railway
   domain and stop the service. Until then its `*.up.railway.app` URL accepts
   any key it knows, with no Access in front of it.

The API itself also refuses requests that did not transit Access
(`CF_ACCESS_ENABLED`), fetching Cloudflare's signing keys from
`<team>.cloudflareaccess.com` through Squid. If every authenticated request
gets a 403 with *invalid Cloudflare Access assertion*, check that fetch first:
`make logs` shows the verification failure.
