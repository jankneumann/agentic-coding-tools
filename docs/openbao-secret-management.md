# OpenBao secret management and cutover

The agent-coordinator/agents.yaml registry declares keyed agents, the credential_vendors catalog, and each agent's explicit vendor_credentials. The shared openbao_credentials.project_principals() projection creates one role and policy for each keyed agent, plus separate identity-reader and egress-gateway service roles. Agent documents live at secret/agents/<agent>, vendor documents at secret/vendors/<vendor>, and coordinator-internal settings remain at secret/coordinator. Those are KV-v2 logical paths; policies use secret/data/... API paths.

Setting BAO_ADDR selects OpenBao mode. Missing bootstrap files, failed authentication, denied reads, and malformed documents then fail closed. The non-Bao development mode uses existing file and environment inputs. CLI vendor processes retain their ambient environment in this release; SDK and OpenAI-compatible dispatch use scoped Bao lookup. A hand-authored openbao_role_id, shared BAO_SECRET_ID, or static coordinator API-key override cannot be used for cutover.

## Local server and live matrix

From agent-coordinator/, run docker compose --profile openbao up -d openbao. The Compose service uses an immutable OpenBao image digest and ephemeral dev mode with BAO_DEV_ROOT_TOKEN_ID=dev-root-token. Production needs TLS, durable storage, unseal procedures, and a limited provisioning token. CI runs the same pinned image through bash skills/bao-vault/scripts/tests/integration/run_live_matrix.sh from the repository root. The runner starts its own server, checks health, fails on zero tests, and tears it down.

## Prepare migration inputs

1. Back up the existing secret/coordinator KV-v2 document and previous deployable release outside git. Record the version and verify restoration.
2. Copy agent-coordinator/.secrets.yaml.example to the gitignored agent-coordinator/.secrets.yaml, restrict it to mode 0600, and fill every keyed agent's coordinator API key. Before preflight, copy vendor keys currently present only in deployment environment variables into this protected flat file. Include every intentionally retained coordinator-internal key. The flat file is migration input; make bao-dev does not seed retained internal values to secret/coordinator.
3. Create a versioned migration map outside git with source key names only. The agents mapping covers every keyed registry agent and agrees with each agent's exact environment placeholder. The vendors mapping covers every credential_vendors entry. retained_internal lists values that stay at secret/coordinator. Every flat-file key appears exactly once. Use legacy_role_aliases only for known pre-migration roles owned by listed agents.

Example shape (replace names with the full current registry and flat file):

~~~yaml
version: 1
agents:
  claude-code-local: CLAUDE_LOCAL_API_KEY
vendors:
  anthropic: ANTHROPIC_API_KEY
retained_internal:
  - LANGFUSE_PUBLIC_KEY
  - LANGFUSE_SECRET_KEY
  - LANGFUSE_HOST
legacy_role_aliases: {}
~~~

Store the map and bootstrap directory under a protected operator location. The bootstrap directory must be owned by the runtime user with mode 0700; bundles and session files use 0600. Mount only each principal's relevant bundle and session files into its trusted consumer. Never pass the root bootstrap directory to an agent child process.

## Preflight and provision

From the repository root, set BAO_ADDR, a provisioning BAO_TOKEN, BAO_BOOTSTRAP_DIR, and the input paths. BAO_MOUNT_PATH defaults to secret and must name an existing KV-v2 mount. Run the complete dry-run before mutation:

~~~bash
BAO_SECRETS_FILE=agent-coordinator/.secrets.yaml \
AGENTS_YAML=agent-coordinator/agents.yaml \
skills/.venv/bin/python skills/bao-vault/scripts/bao_seed.py \
  --migration-map /secure/bao/migration.yaml \
  --bootstrap-dir /secure/bao/bootstrap --dry-run
~~~

Resolve every preflight error and inspect the printed role, policy, path, and retirement plan. No credential values are printed. Then rerun without --dry-run to reconcile exact policies and data paths and issue one-use, response-wrapped SecretIDs. Apply emits sanitized mutation events. Reissuing a bundle after token revocation or expiry requires a provisioning run.

The coordinator identity reader uses principal spiffe://coordinator.rotkohl.ai/service/identity-reader and role service-identity-reader. It reads all keyed agent documents to build one atomic API-key snapshot. The egress gateway reads only declared vendor paths. Each agent reads its own agent document and its listed vendor documents. Verify denial cases with the live matrix before switching consumers.

## Internal coordinator handoff

Keep secret/coordinator for internal settings such as Langfuse. Explicitly stage or restore retained values there, then provision a separate internal AppRole and set BAO_INTERNAL_ROLE_ID and BAO_INTERNAL_SECRET_ID for profile_loader.py and langfuse_env.sh. BAO_SECRET_PATH defaults to coordinator for this internal loader only. The migration seeder does not copy retained internal values into that path.

Switch coordinator and dispatch deployments to BAO_ADDR, BAO_BOOTSTRAP_DIR, and BAO_MOUNT_PATH, delivering principal-specific protected files. The coordinator's GET /ready reports identity: ready|degraded|disabled separately from database status. On failed refresh it serves only the last complete snapshot for at most 120 seconds, then rejects authentication until a complete reload succeeds. Confirm identity: ready, inspect sanitized refresh events, and verify rotated keys revoke old access before retiring the legacy policy.

For final retirement, supply --confirm-cutover --internal-role-name <existing-internal-role> and matching BAO_INTERNAL_ROLE_ID and BAO_INTERNAL_SECRET_ID to the seeder. It verifies that this role reads secret/coordinator under the isolated policy and refuses unknown roles still using coordinator-read. Drain or restart processes holding old internal tokens before deleting the shared policy; a token issued before policy change can retain access until its lease ends. Review the cutover dry-run, then apply. The operation retires only owned legacy agent roles, aliases, paths, and the old shared policy. It preserves secret/coordinator and unrelated engines.

Rollback restores the previous release and the backed-up secret/coordinator document, then reissues previous deployment credentials through the normal secure channel. There is no dual-read or static-key override in OpenBao mode. Do not put role IDs, SecretIDs, wrap tokens, session tokens, API keys, or backups in git or logs.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Dry-run rejects a source key | Map every flat-file key once, including retained keys, and match registry placeholders. |
| CONFIGURATION_INVALID | Check BAO_ADDR, BAO_BOOTSTRAP_DIR ownership and modes, and the KV-v2 mount. |
| BOOTSTRAP_INVALID or TOKEN_EXPIRED | Deliver a fresh, one-use wrapped bundle. A consumed bundle cannot recover a revoked token. |
| AUTHORIZATION_DENIED | Check declared vendor scope and exact policy path. Do not broaden it to secret/coordinator. |
| identity: degraded | Inspect sanitized identity events, restore all keyed agent documents, and wait for a complete reload. |
| Langfuse values absent | Check retained values at secret/coordinator and the isolated BAO_INTERNAL_* AppRole. |

See packages/openbao-credentials/ for the projection and typed adapter, skills/bao-vault/scripts/bao_seed.py for reconciliation, and agent-coordinator/src/openbao_identity.py for snapshot behavior.
