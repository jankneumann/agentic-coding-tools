# Cloudflare Access Setup (Service Tokens + Origin Verification)

This guide adds **Cloudflare Access** (Zero Trust) in front of the coordinator
API so that only authenticated callers reach it — cloud agents authenticate
with **service tokens**, humans with SSO. It complements, and does not replace,
the coordinator's own per-agent `X-API-Key`.

It is the recommended security layer when you move the coordinator off Railway
and host it locally behind a Cloudflare Tunnel (see
[`cloudflare-setup.md`](cloudflare-setup.md) for the tunnel/DNS itself and
[`cloud-deployment.md`](cloud-deployment.md) for the overall architecture).

> **Why this, and not a hand-rolled gateway?** Cloudflare Access is a managed,
> audited zero-trust proxy. Verification uses standard JWT + JWKS (RS256) via
> PyJWT — no custom auth protocol or crypto. See
> [`agent-coordinator/src/cloudflare_access.py`](../agent-coordinator/src/cloudflare_access.py).

---

## Threat model / what this buys you

- **Public API, no open ports.** The tunnel is outbound-only; Access rejects
  unauthenticated traffic *at Cloudflare's edge*, before it reaches your box.
- **Rate limiting the app lacks.** The coordinator has no application-layer rate
  limiting; Cloudflare rules provide it (see §4).
- **Origin-bypass protection.** With a tunnel, `cloudflared` connects to
  `localhost:8081`, so every request looks like it came from `127.0.0.1`. The
  signed `Cf-Access-Jwt-Assertion` header is the *only* proof a request really
  transited Access. The coordinator verifies it (§3), so even a request that
  reached the origin some other way is refused.
- **Two independent secrets.** A leaked coordinator `X-API-Key` alone can't call
  the API (no valid Access assertion); a leaked service token alone can't
  either (no valid `X-API-Key`). Rotate them independently.

---

## 1. Create the Access application

In the Cloudflare **Zero Trust** dashboard → **Access → Applications → Add an
application → Self-hosted**:

- **Application name:** `coordinator`
- **Session duration:** short (e.g. 24h) — service tokens ignore this, humans re-auth.
- **Application domain:** `coord.<yourdomain>` (the tunnel hostname).
- Save. Open the application and copy its **Application Audience (AUD) Tag** — a
  long hex string. This is your `CF_ACCESS_AUD`.

Your **team domain** is `https://<your-team>.cloudflareaccess.com` (Zero Trust →
Settings → Custom Pages / or the URL you log in at). This is `CF_ACCESS_TEAM_DOMAIN`.

## 2. Create service tokens (one per non-interactive client)

Zero Trust → **Access → Service Auth → Service Tokens → Create Service Token**.
Create **one per client** so you can rotate/revoke independently — this mirrors
the coordinator's own per-agent API-key design:

| Service token name    | Used by                       |
|-----------------------|-------------------------------|
| `claude-web`          | Claude Code Web               |
| `codex-cloud`         | Codex cloud                   |
| `gemini-cloud`        | Gemini cloud                  |

Each token yields a **Client ID** (`<id>.access`) and **Client Secret** (shown
once — store it in your secret manager). Default token lifetime is 1 year; set a
calendar reminder to rotate.

Then add an Access **policy** on the `coordinator` application:

- **Policy name:** `service-tokens`
- **Action:** **Service Auth**
- **Include:** **Service Token** → select the tokens created above (or
  *Any Access Service Token* to accept all of them).

To also allow yourself in a browser (over Tailscale or anywhere), add a second
policy **Action: Allow**, **Include: Emails →** your email. Humans get SSO;
machines get the service-token path.

## 3. Enable origin verification on the coordinator

Set these **server-side** env vars (see
[`agent-coordinator/CLAUDE.md`](../agent-coordinator/CLAUDE.md) and the
`cloudflare` profile):

```bash
export CF_ACCESS_TEAM_DOMAIN="https://<your-team>.cloudflareaccess.com"
export CF_ACCESS_AUD="<application-audience-tag>"   # from step 1
# Optional overrides:
# export CF_ACCESS_ENABLED=true                     # force on/off (else inferred)
# export CF_ACCESS_EXEMPT_PATHS=/live,/ready,/health,/metrics   # default
# export CF_ACCESS_JWKS_CACHE_SECONDS=3600
```

Behavior:

- **Enabled** when both `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` are set (or
  `CF_ACCESS_ENABLED=true`). The API verifies `Cf-Access-Jwt-Assertion` on every
  request except the exempt paths and CORS `OPTIONS` preflight; invalid/missing
  → **403**.
- **Disabled** (unset) → pass-through. Local/dev is unchanged.
- **Fail-fast on misconfig:** if enabled with a missing team domain or AUD, the
  app raises at startup rather than silently accepting traffic.

> Verification pins the token's `aud` to your AUD tag(s) and `iss` to your team
> domain, and checks the RS256 signature against Cloudflare's JWKS
> (`<team-domain>/cdn-cgi/access/certs`), which PyJWT fetches and caches.

## 4. Add a rate-limiting rule (fills an app-layer gap)

Cloudflare dashboard → **Security → WAF → Rate limiting rules → Create**:

- **If** `http.host eq "coord.<yourdomain>"`
- **Then** e.g. *When rate exceeds 600 requests per 1 minute per IP → Block for 1 min.*

Tune to your fleet size. Consider a stricter rule on the token-mint path
(`/events/auth`). Also confirm **Bot Fight Mode** is **off** for this hostname —
it breaks machine-to-machine JSON clients (see `cloudflare-setup.md §6`).

## 5. Configure the clients

Set the service token on each cloud agent (the coordinator client code sends
`CF-Access-Client-Id` / `CF-Access-Client-Secret` automatically when both are
present — see `skills/coordination-bridge/scripts/coordination_bridge.py` and
`agent-coordinator/src/http_proxy.py`):

```bash
export CF_ACCESS_CLIENT_ID="<client-id>.access"
export CF_ACCESS_CLIENT_SECRET="<client-secret>"
```

`scripts/setup_cloud.py` writes commented placeholders for these into
`.env.cloud`; uncomment and fill them per agent.

## 6. Verify end-to-end

```bash
# No token → blocked by Access at the edge (302/403), never reaches origin:
curl -si https://coord.<yourdomain>/locks/status/x | head -n 1

# With a service token → passes the edge; then the coordinator's own X-API-Key
# check applies:
curl -si https://coord.<yourdomain>/locks/status/x \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" | head -n 1

# Health probes are exempt (used by the tunnel/uptime checks):
curl -s https://coord.<yourdomain>/health
```

`uv run --project agent-coordinator python agent-coordinator/scripts/setup_cloud.py --domain coord.<yourdomain>
--verify` also sends the token when `CF_ACCESS_CLIENT_ID/SECRET` are exported.

---

## Operational notes

- **Health/metrics are exempt** so the tunnel's health check and Prometheus
  scraping keep working. Everything else requires Access. Adjust with
  `CF_ACCESS_EXEMPT_PATHS` if you want `/metrics` gated too.
- **Rotation.** Revoke/recreate a service token in Zero Trust; update that one
  agent's `CF_ACCESS_CLIENT_*`. No coordinator restart needed. Rotating the
  coordinator `X-API-Key`s is a separate, independent action.
- **Keep secrets out of git.** Store client secrets in OpenBao / `.env.cloud`
  (gitignored), never in the repo.
