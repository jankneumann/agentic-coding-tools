# Integration validation

Run from the managed `wp-integration` worktree against the pinned OpenBao v2.6.2 image digest in `agent-coordinator/docker-compose.yml`.

| Gate | Result |
| --- | --- |
| `bash skills/bao-vault/scripts/tests/integration/run_live_matrix.sh` | 7 passed; rootless Podman; health-checked random localhost port; container stopped by trap |
| `skills/.venv/bin/python -m pytest skills/bao-vault/scripts/tests/test_langfuse_env.py skills/bao-vault/scripts/tests/test_bao_seed.py -q` | 32 passed |
| `skills/.venv/bin/ruff check skills/bao-vault/scripts/tests/integration skills/bao-vault/scripts/tests/test_langfuse_env.py` | Passed |
| `openspec validate restructure-openbao-per-agent-secrets --strict` | Passed |
| Package scope check against `wp-integration.scope.write_allow` | 11 files within scope; no violations before this evidence file |
| `git diff --check` | Passed |

The live matrix exercises exact agent, identity-reader, egress-gateway, and internal AppRole permissions; one-use wrap replay and fresh recovery; local and server-side wrap creation-path forgery; coordinator key rotation and degraded readiness; the Langfuse internal helper; and periodic-token renewal beyond its original lease. Each forgery test bootstraps its own session so it can run in isolation.

The CI coverage guard, `skills/.venv/bin/python -m pytest skills/tests/ci_coverage -q`, passed 135 tests after the parent branch added the Dependabot pip entry for `packages/openbao-credentials/pyproject.toml`.
