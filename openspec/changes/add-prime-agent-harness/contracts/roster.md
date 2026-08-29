# Prime vendor roster contract

Every work package writes against these canonical strings. Aliases or independently
authored setup-cloud roster branches are planning defects.

| Meaning | Canonical value |
|---|---|
| Provider key / `type` | `prime` |
| CLI binary | `prime-agent` |
| Agent id | `prime-local` |
| Profile | `prime_local` |
| Coordinator key destination | `prime_local_key` |
| Coordinator CLI flag | `--prime-local-key` |
| Coordinator runtime environment | `COORDINATION_API_KEY` |
| Provider credential environment | `PRIME_API_KEY` |
| Setup-cloud alias | `cprime-agent` |

`prime` and `pi` are distinct whole vendor keys. An unanchored substring match is
invalid.

## Credential boundary

The setup-cloud roster is derived generically from `agents.yaml`. Adding
`prime-local` therefore projects its coordinator flag, identity-map entry, and
alias without changing production `setup_cloud.py`. The generated coordinator key
is never a Prime Inference credential.

`PRIME_API_KEY` is operator-supplied through the provider-secret path and named by
`cli.api_key_env`. Setup-cloud MUST NOT generate, accept, upload, serialize, or
alias it as a coordinator identity.

## Dispatch modes

`alternative` and `quick` are enabled after empirical Phase 1 confirms their
invocation shape. `review` is enabled only when P6 proves both harness-native write
prevention and positive repository-read evidence.

All modes use `--mode json`. If P7 proves a lifecycle command is required,
`prime-local.cli.cleanup` follows `cli-dispatch-config.schema.json`; otherwise the
entry omits cleanup while the generic config capability remains supported.

