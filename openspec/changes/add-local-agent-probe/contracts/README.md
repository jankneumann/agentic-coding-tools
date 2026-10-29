# Contracts: add-local-agent-probe

| Sub-type | Applies | File |
|---|---|---|
| OpenAPI | Additive field only — `cli.probe` in the existing `GET /agents/dispatch-configs` payload; no new endpoint | covered by `cli-probe-block.schema.json` |
| Database | No — the cache is a per-user file, nothing is persisted in Postgres | — |
| Events | No | — |
| Config schema | Yes — `agents.yaml` `cli.probe` | `cli-probe-block.schema.json` |
| File format | Yes — per-machine probe cache | `vendor-probe-cache.schema.json` |

Note: the auth-arg rule has two parts. The JSON Schema pattern denies credential-printing
tokens and `logout` anywhere; `agents_config.validate` additionally rejects a list whose last
token is `login` (design D3). `codex login status` is accepted; `grok login` is rejected.
Contract tests in `wp-contracts` pin both the accept and reject cases.
