# Tasks — extend-coordinator-keys-to-new-harnesses

Small change, applied directly in one pass (no work packages).

- [x] 1.1 `agents.yaml`: add `api_key` + `openbao_role_id` to `claude-local`, `codex-local`,
  `antigravity-local`, `grok-local`, `pi-local`; document that `api_key` is the coordinator
  credential (distinct from `sdk.api_key_env`) and applies to any transport (S)
- [x] 1.2 `agents.yaml`: add the `grok-remote` entry — identity + key, no `cli` section, with
  the reason for its absence recorded inline (S)
- [x] 1.3 `get_api_key_identities()`: derive from every agent declaring an `api_key` instead
  of filtering on `transport == "http"` (S)
- [x] 1.4 `bao_seed.py`: create AppRoles on the same `api_key` rule; rename `http_agents` →
  `keyed_agents` and update the module docstring (S)
- [x] 1.5 `.secrets.yaml.example`: add the eight coordinator key variables, separated from
  the vendor model keys (XS)
- [x] 1.6 `setup_cloud.py`: add `grok-remote` to `AGENTS` and a `--grok-remote-key` flag (XS)
- [x] 1.7 Tests: identity map includes keyed `mcp` agents; AppRole created for a keyed `mcp`
  agent; shipped `agents.yaml` roster is exactly the eight expected agents, all keyed, with
  distinct key variables (M)
- [x] 1.8 Docs: `cloud-deployment.md` (local agents need keys; alias list; per-harness key
  generation), `openbao-secret-management.md` (secrets split, AppRole list),
  `skills/setup-coordinator/SKILL.md` (keyed agents, not HTTP agents) (S)
