# Integration validation

Run from the managed `wp-integration` worktree against the pinned OpenBao v2.6.2 image digest in `agent-coordinator/docker-compose.yml`.

| Gate | Result |
| --- | --- |
| `bash skills/bao-vault/scripts/tests/integration/run_live_matrix.sh` | 8 passed; rootless Podman; health-checked random localhost port; container stopped by trap |
| `skills/.venv/bin/python -m pytest skills/bao-vault/scripts/tests/test_langfuse_env.py skills/bao-vault/scripts/tests/test_bao_seed.py -q` | 32 passed |
| `skills/.venv/bin/ruff check skills/bao-vault/scripts/tests/integration skills/bao-vault/scripts/tests/test_langfuse_env.py` | Passed |
| `openspec validate restructure-openbao-per-agent-secrets --strict` | Passed |
| Package scope check against `wp-integration.scope.write_allow` | Rechecked after review follow-up; all changed files within scope |
| `git diff --check` | Passed |

The live matrix exercises exact agent, identity-reader, egress-gateway, and internal AppRole permissions, including denial of `secret/coordinator`; one-use wrap replay and fresh recovery; local and server-side wrap creation-path forgery; two processes contending for one wrapped bundle (one unwrap and login, one session reuse); coordinator key rotation, static-key bypass denial, degraded readiness, and recovery; the Langfuse internal helper; and periodic-token renewal past a tuned 5-second AppRole auth-mount max TTL (three individually asserted renewals over six seconds, same token). The test restores mount tuning afterward and cleans up temporary roles and policy. Each test gets a fresh reconciliation and protected session directory. Individual process-contention, coordinator-rotation, and periodic-renewal selections passed 1/1 each with seven deselected.

The runner now parses pytest's JUnit report after a successful exit and requires at least one passed case. An injected pytest plugin that skipped all eight cases yielded `8 skipped` followed by `Live OpenBao matrix collected no passing tests`, with runner exit code 1.

The CI coverage guard, `skills/.venv/bin/python -m pytest skills/tests/ci_coverage -q`, passed 135 tests after the parent branch added the Dependabot pip entry for `packages/openbao-credentials/pyproject.toml`.
