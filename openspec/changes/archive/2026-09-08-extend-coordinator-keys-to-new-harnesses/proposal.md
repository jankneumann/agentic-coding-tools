# Extend the coordinator key set to the agy / grok / pi harnesses

> Change ID: `extend-coordinator-keys-to-new-harnesses`
> Effort: S
> Supersedes PR #352 (same change id; see "Relationship to #352" below)

## Why

`add-agy-grok-pi-harnesses` added three vendors to the roster (`antigravity-local`,
`grok-local`, `pi-local`) and wired their CLI dispatch, but none of them received a
coordinator credential. `agents.yaml` carries `api_key` for exactly two agents —
`claude-remote` and `codex-remote` — so the three new harnesses have no entry in
`COORDINATION_API_KEY_IDENTITIES` and no way to authenticate except by borrowing
another agent's key. Grok also has no cloud entry at all, though it runs in both
locations.

The *mechanism* half of this gap is already fixed on main.
`get_api_key_identities()` no longer filters on `transport == "http"` (design D5),
and `setup_cloud.py` derives its whole roster and its `--<agent>-key` flags from
`agents.yaml` (design D7). What is still missing is the *data* — the keys
themselves — and one place where the old transport rule survived.

## What Changes

- **ADD** coordinator `api_key` + `openbao_role_id` to every local harness in
  `agents.yaml`: `antigravity-local`, `grok-local`, `pi-local`, plus `claude-local`
  and `codex-local`. Under D7 this is also what gives `setup_cloud.py` their key
  flags — no change to that script is needed.
- **ADD** a `grok-remote` agent entry (`transport: http`, trust level 2, sandbox
  isolation) so grok is keyed in both locations. Identity and key only — no `cli`
  section, because the cloud submit/poll shape has not been probed the way the local
  flags were in `add-agy-grok-pi-harnesses`, and a guessed dispatch mode fails at
  runtime while looking configured.
- **MODIFY** `bao_seed.py` to create AppRoles on the `api_key` rule rather than
  `transport == "http"`. This is a live inconsistency on main today: the identity map
  covers every keyed agent (D5) while AppRole seeding still covers only HTTP-transport
  ones, so an agent can hold an identity row whose key OpenBao was never told to serve.
- **ADD** the coordinator key variables to `.secrets.yaml.example`, split from the
  vendor model keys they are routinely confused with.
- **MODIFY** the `agent-identity` spec to record the transport-independent identity
  rule. Main implemented D5 in code but the spec still describes only the OpenBao
  resolution, so the written contract is behind the behavior.

Location coverage is deliberate: pi is local-only, antigravity is local-only, grok is
both.

## Relationship to #352

PR #352 proposed this change in August under the same change id. While it sat, main
implemented the mechanism independently — `get_api_key_identities()` (D5) and the
registry-driven `setup_cloud.py` (D7). Merging #352 now would resolve conflicts
*against* main and reintroduce the hardcoded `AGENTS` roster that D7 deliberately
deleted, so its still-valid remainder is landed here instead and #352 is closed.

Dropped as superseded: the `get_api_key_identities()` change and its tests, the
`setup_cloud.py` roster and `--grok-remote-key` flag (both now derived), and the
doc-wording edits main has since made in its own words.

## Impact

- No runtime behavior change until secrets are populated: unresolved `${VAR}`
  placeholders are skipped by the identity map, so a checkout without `.secrets.yaml`
  derives exactly the key set it derived before. Verified: 8 agents in the registry,
  0 identities with placeholders unresolved, 8 once populated.
- Deployments that set `COORDINATION_API_KEYS` / `COORDINATION_API_KEY_IDENTITIES`
  explicitly (Railway today) are unaffected — the explicit env vars still win.
- Populating the new secrets admits each harness under its own identity, so audit
  entries, lock ownership, and trust levels resolve per vendor × location instead of
  collapsing onto whichever key was shared.
