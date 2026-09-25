# Plan review resolution ledger

The first pass returned schema-valid findings from Codex, Antigravity, Claude
Code, and Grok. Pi returned an invalid JSON schema payload; its output was
excluded from consensus. Reviewers read the plan while it was being revised,
so several findings refer to an earlier revision. The current plan revision is
`7` in `work-packages.yaml`.

| Finding cluster | Resolution in current plan |
|---|---|
| Static allowlist bypasses rotated identities | D4, COORD-09, and tasks 3.1/3.5 make the installed snapshot the sole configured-Bao accepted-key set and reject unbound static keys at cutover. |
| Missing caller or loader write scopes | `wp-dispatch` owns `review_dispatcher.py`; `wp-coordinator` owns `agents_config.py` and `profile_loader.py`; integration owns `langfuse_env.sh`. |
| One-use bootstrap breaks short-lived dispatch or long-lived services | D3 and the session-cache schema require a locked protected token cache; projected AppRoles issue short-period renewable tokens without an explicit maximum TTL. CFG-17 tests sequential and concurrent processes. |
| Flat source file cannot map to namespaced documents | The versioned migration-map schema and `--migration-map PATH` preflight assign each agent/vendor source key, account for retained internal fields, and name legacy role aliases. CFG-18 covers missing or duplicate mappings. |
| `secret/coordinator` also stores internal settings | D5, CFG-19, and package tasks retain the data path under renamed internal-only credentials, install an internal-only policy, and retire legacy agent grants only after confirmed cutover. |
| Mount-relative paths differ from policy API paths | D1, CFG-03/16, topology schema, and contract README distinguish `agents/<name>` passed to hvac from `<mount>/data/agents/<name>` in policies; `BAO_MOUNT_PATH` is validated. |
| Vendor identifiers and payload shape undefined | `credential_vendors` is the registry catalog; agent/vendor payload schemas require one nonempty `api_key`; gateway paths are the exact union of agent-declared vendors. AI-13/14 and CFG-20 cover these rules. |
| Audit and readiness contracts drift | Audit schema now includes action, resource, timeout, and safe correlation fields; COORD-07 uses the typed code. `/ready` reports disabled outside Bao, HTTP 200 during valid grace, and 503 after expiry or startup failure. |
| Container and live fixture can pass without usable Bao | Projection owns Dockerfile and CI smoke import; integration owns pinned Compose/CI fixture and a runner that fails when Bao is absent or no live assertions run. |
| Work packages cannot update canonical task status | The implementation package DAG is serialized and each worker may update `tasks.md` with its code in the same commit, per implement-feature's checkbox rule. |

The independent Codex convergence audit found two remaining wording/sequence
issues. Both were fixed: the README now names mount-relative logical paths,
and task 5.3 no longer claims to test the Langfuse helper before task 5.7
migrates it. A second vendor pass yielded valid Claude Code and Grok findings. Antigravity timed out and Pi returned an invalid payload; neither was counted. The second-pass consensus has no multi-vendor blocking agreement, but all actionable single-vendor findings were independently checked and resolved: the dispatch-config wire now carries `principal_id` and `vendor_credentials`; role-derived bundle/session/lock names are fixed; server-side wrapping lookup is explicit; the endpoint fixture is in the producer package; migration-map agent keys must match registry placeholders; the CLI credential boundary is stated; vendor keys must be staged into the protected seed input; and the Docker copy is builder-only. Grok's inherited config-contract finding led to a separate internal `OpenBaoConfig` requirement and principal configuration requirement, with explicit failure scenarios and `config.py` ownership. The Docker COPY and README path findings had already been fixed before the second reviewer read a stable revision.

At implementation contract freeze, `wp-contracts` found the audit schema permitted a principal mutation without `principal_id` or `resource`. Revision 5 adds a conditional required-field rule for principal and bootstrap events; representative negative and positive examples were validated before projection dispatch.

Projection implementation review found cached-token recovery could not use a newly delivered bundle. Revision 6 adds `bootstrap_token_sha256` to the protected session cache and requires server validity checking plus digest-gated rebootstrap under the lock. It also enforces explicit registry credential declarations; both findings block projection integration until tested.

Revision 7 expands `wp-projection` to the existing `test_agents_config_isolation.py` fixture, whose temporary registry YAML must declare the newly required vendor catalog. Its verification command now runs that test. No production scope changed.
