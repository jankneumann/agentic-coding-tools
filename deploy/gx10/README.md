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
| Images are pinned `tag@sha256` | `GX10_COORD_IMAGE`, `GX10_COORD_POSTGRES_IMAGE`, `GX10_CLOUDFLARED_IMAGE` in `/etc/aca/gx10-images.env`. The compose fails closed on an unset one. |
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
   `coordination_api_key`, `sse_signing_key`.
4. **A Cloudflare tunnel** — `cloudflared tunnel create gx10-coordinator` —
   with its credentials JSON at `/run/aca/gx10/cloudflared/credentials.json`
   (0600) and a config whose only ingress rule is the coordinator API.
   `GX10_COORD_TUNNEL_CONFIG` points the renderer at the reviewed config.
5. **A Cloudflare Access application** on `coord.<domain>` with a service
   token for cloud agents. Without it the tunnel publishes the API with only
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
  by the analyzer's Caddy; there is no frontend container here.
