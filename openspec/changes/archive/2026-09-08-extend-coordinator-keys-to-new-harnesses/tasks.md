# Tasks — extend-coordinator-keys-to-new-harnesses

Small change, applied directly in one pass (no work packages).

- [x] 1.1 `agents.yaml`: add `api_key` + `openbao_role_id` to `claude-local`,
  `codex-local`, `antigravity-local`, `grok-local`, `pi-local` (S)
- [x] 1.2 `agents.yaml`: add the `grok-remote` entry — identity + key, no `cli`
  section, with the reason for its absence recorded inline (S)
- [x] 1.3 `bao_seed.py`: create AppRoles on the `api_key` rule instead of
  `transport == "http"`; rename `http_agents` → `keyed_agents` and record in the
  docstring why the credential, not the transport, is the selector (S)
- [x] 1.4 `.secrets.yaml.example`: add the coordinator key variables, separated from
  the vendor model keys (XS)
- [x] 1.5 Tests: AppRole created for a keyed `mcp` agent (the case the old selector
  dropped); rename the two tests that named `transport` as the rule so they describe
  the rule they actually pin (S)
- [x] 1.6 Spec: record the transport-independent identity rule that main implemented
  in code (D5) but never wrote down, and add the Harness Key Coverage requirement (S)

## Dropped as superseded by main

- `get_api_key_identities()` transport filter — main implemented it (design D5)
- `setup_cloud.py` roster + `--grok-remote-key` flag — main derives both from
  `agents.yaml` (design D7); adding a hardcoded roster back would regress it
- `cloud-deployment.md` / `openbao-secret-management.md` / `setup-coordinator`
  wording — main has since rewritten these in its own words
