# Contracts: add-local-agent-probe

| Sub-type | Applies | File |
|---|---|---|
| OpenAPI | No OpenAPI artifact changes. The only wire change is the additive, present-only `cli.probe` object inside each lane of the existing `GET /agents/dispatch-configs` payload; its shape is `cli-probe-block.schema.json`, and its placement and present-only omission are pinned by the agent-identity scenario "The probe block round-trips through dispatch-configs" (task 4.1). `work-packages.yaml` lists the JSON Schemas under `contracts.openapi` only because that slot is required by the work-packages schema. | — |
| Database | No — the cache is a per-user file, nothing is persisted in Postgres | — |
| Events | No | — |
| Config schema | Yes — `agents.yaml` `cli.probe` | `cli-probe-block.schema.json` |
| File format | Yes — per-machine probe cache | `vendor-probe-cache.schema.json` |

Note: the probe-argv rules have two layers.

- **Schema layer** (`cli-probe-block.schema.json`, portable ECMA-262 patterns, no inline flags):
  every argv the probe executes — `version_args`, each `help_args` value, `auth_status_args` —
  must be non-empty and must not contain a token matching `print-api-key`,
  `print-bearer-token`, `--credentials`, `--show-token`, or `logout` (case-insensitive);
  `credential_files`, when declared, is non-empty.
- **Semantic layer** (`agents_config.validate`, design D3): `auth_status_args` must not end
  in `login` (`codex login status` is accepted; `grok login` is rejected), and each
  `help_args` value must contain `--help`, `-h`, or `help`.

`wp-contracts` (task 1.1) pins the schema layer only; the semantic layer is pinned in
`wp-config` (task 4.1), where `agents_config.validate` lives.
