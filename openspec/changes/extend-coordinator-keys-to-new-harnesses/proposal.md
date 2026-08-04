# Extend the coordinator key set to the agy / grok / pi harnesses

> Change ID: `extend-coordinator-keys-to-new-harnesses`
> Effort: S

## Why

`add-agy-grok-pi-harnesses` added three vendors to the roster (`antigravity-local`,
`grok-local`, `pi-local`) and wired their CLI dispatch, but none of them received a
coordinator credential. `agents.yaml` carried `api_key` for exactly two agents —
`claude-remote` and `codex-remote` — so the three new harnesses had no entry in
`COORDINATION_API_KEY_IDENTITIES` and no way to authenticate except by borrowing another
agent's key. Grok also had no cloud entry at all, though it runs in both locations.

The gap was structural, not an oversight in that change: `get_api_key_identities()` filtered
on `transport == "http"`, so a key on a local harness would have been dropped even if
declared. That filter encodes an assumption the deployment does not hold — local harnesses
authenticate over HTTP through the session hooks (`register_agent`, `report_status`,
`precompact_handoff`), through `http_proxy` when the local database is unreachable, and for
every coordination call when the coordinator is hosted (the deployment this repo actually
runs, where all agents point at the Railway service instead of a local MCP server).
`setup_cloud.py` had already diverged from `agents.yaml` on exactly this point: it generates
per-agent keys for all five local harnesses.

## What Changes

- **ADD** coordinator `api_key` + `openbao_role_id` to every local harness in `agents.yaml`:
  `antigravity-local`, `grok-local`, `pi-local`, plus `claude-local` and `codex-local`, which
  `setup_cloud.py` already provisioned keys for without a declarative counterpart.
- **ADD** a `grok-remote` agent entry (`transport: http`, trust level 2, sandbox isolation)
  so grok is keyed in both locations. Identity and key only — no `cli` section, because the
  cloud submit/poll shape has not been probed the way the local flags were in
  `add-agy-grok-pi-harnesses`, and a guessed dispatch mode fails at runtime while looking
  configured.
- **MODIFY** `get_api_key_identities()` to derive identities from every agent that declares
  an `api_key`, whatever its transport.
- **MODIFY** `bao_seed.py` to create AppRoles on the same rule (`api_key` present, not
  `transport == "http"`), keeping the AppRole set and the identity map aligned.
- **ADD** the eight coordinator key variables to `.secrets.yaml.example`, split from the
  vendor model keys they are routinely confused with.
- **ADD** `grok-remote` to the `setup_cloud.py` key set and a `--grok-remote-key` flag.
- **UPDATE** docs that describe the key set: `cloud-deployment.md` (which claimed local
  agents need no key, and still advertised the retired `cgemini` alias),
  `openbao-secret-management.md`, and the `setup-coordinator` skill.

Location coverage is deliberate: pi is local-only, antigravity is local-only, grok is both.

## Impact

- No runtime behavior change until secrets are populated: unresolved `${VAR}` placeholders
  are skipped by the identity map, so a checkout without `.secrets.yaml` derives exactly the
  key set it derived before.
- Deployments that set `COORDINATION_API_KEYS` / `COORDINATION_API_KEY_IDENTITIES`
  explicitly (Railway today) are unaffected — the explicit env vars still win.
- Populating the new secrets admits each harness under its own identity, so audit entries,
  lock ownership, and trust levels resolve per vendor × location instead of collapsing onto
  whichever key was shared.
