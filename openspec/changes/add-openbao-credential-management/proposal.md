# Change: Add OpenBao Credential Management

## Why

Our current secrets management relies on static `.secrets.yaml` files copied or symlinked into each worktree (`scripts/worktree-bootstrap.sh:20-26`), with `profile_loader.py` interpolating `${VAR}` placeholders at startup. This approach has three scaling gaps: (1) no credential rotation without restarting services, (2) no revocation when an agent session ends or a key leaks — you must redeploy everything, and (3) no audit trail of which agent read which secret. For local single-developer use this is acceptable, but as the coordinator moves to cloud deployment with heterogeneous agents at different trust levels (`agents.yaml` already models trust 1–5), the static-file model becomes a liability. OpenBao (the open-source Vault fork under the Linux Foundation / OpenSSF) provides dynamic secrets with automatic lease expiry, per-identity scoping via AppRole auth, and a built-in audit log — directly addressing all three gaps without requiring a proprietary cloud secret manager.

## What Changes

### 1. OpenBao Client Integration in Profile Loader

- Add an `openbao` secret backend to `profile_loader.py` alongside the existing `.secrets.yaml` backend
- When `BAO_ADDR` is set in the environment, `_load_secrets()` authenticates to OpenBao (AppRole) and reads secrets from KV v2 (mount path configurable via `BAO_MOUNT_PATH`, default `secret`; data path configurable via `BAO_SECRET_PATH`, default `coordinator`) instead of `.secrets.yaml`
- The `${VAR}` interpolation layer, profile inheritance, and `FIELD_ENV_MAP` injection remain unchanged — only the secret **source** changes
- Fallback: when `BAO_ADDR` is not set, behaviour is identical to today (`.secrets.yaml` file)

### 2. AppRole Auth for Agent Identity

- Each HTTP-transport agent declared in `agents.yaml` maps to an OpenBao AppRole with a policy granting read access to the coordinator secrets path (per-agent sub-path scoping is a future enhancement)
- `agents_config.py` gains an `openbao_role_id` field per agent entry
- On coordinator startup, `get_api_key_identities()` can resolve agent API keys from OpenBao instead of static `${CLAUDE_WEB_API_KEY}` interpolation
- Agent sessions receive SecretIDs (via environment variable) that authenticate to OpenBao and obtain a scoped token with a configurable TTL (`BAO_TOKEN_TTL`, default 1 hour)
- When the session ends, the token lease expires and any dynamic credentials it generated are auto-revoked

### 3. Dynamic Database Credentials

- Enable the OpenBao database secrets engine for PostgreSQL
- Configure an OpenBao database role template (`coordinator-agent`) that generates unique per-agent PostgreSQL credentials with a 1-hour TTL and max 24-hour renewal — each agent gets its own short-lived Postgres role from this template
- `profile_loader.py` resolves `POSTGRES_DSN` dynamically via the database secrets engine instead of the static `${DB_PASSWORD}` interpolation
- Each agent receives its own short-lived Postgres role — enabling per-agent audit in the database itself
- Local dev: continues to use the static `postgres:postgres` default; no OpenBao dependency

### 4. Bootstrap Seeding from secrets.yaml

- New script `scripts/bao-seed.py`: reads `.secrets.yaml` and writes each key-value pair into OpenBao KV v2 at `secret/data/coordinator`
- Configures AppRoles and policies from `agents.yaml` definitions
- Configures the database secrets engine connection and roles
- Idempotent: safe to re-run; updates existing secrets, does not duplicate
- Intended for initial setup and CI/CD pipeline provisioning — not for runtime use
- Accepts `--dry-run` flag to preview changes without writing

### 5. Docker Compose Dev Profile for OpenBao

- Add an `openbao` service to `agent-coordinator/docker-compose.yml` (dev mode, auto-unsealed)
- New `make bao-dev` target: starts OpenBao in dev mode, runs `bao-seed.py` to populate it from `.secrets.yaml`
- New profile `openbao.yaml` extending `local.yaml` that sets `BAO_ADDR=http://localhost:8200`
- Developers can opt in to test the full OpenBao flow locally without affecting the default `make dev` path

### 6. Worktree Secret Elimination

- `worktree-bootstrap.sh` stops copying `.secrets.yaml` when `BAO_ADDR` is set
- Each worktree agent authenticates to OpenBao independently using its AppRole credentials (passed via environment, not file)
- Eliminates the file-based secret sharing that prevents scaling to cloud agents

## Impact

- Affected specs: `configuration` (secret loading, interpolation, bootstrap seeding), `agent-identity` (AppRole per agent, dynamic database credentials, API key identity generation)
- Affected code:
  - `agent-coordinator/src/profile_loader.py` — new `_load_secrets_openbao()` backend, conditional dispatch in `_load_secrets()`
  - `agent-coordinator/src/agents_config.py` — `openbao_role_id` field, dynamic key resolution
  - `agent-coordinator/src/config.py` — new `OpenBaoConfig` dataclass (`BAO_ADDR`, `BAO_ROLE_ID`, `BAO_SECRET_ID`, `BAO_MOUNT_PATH`, `BAO_SECRET_PATH`, `BAO_TIMEOUT`, `BAO_TOKEN_TTL`)
  - `agent-coordinator/agents.yaml` — `openbao_role_id` per agent entry
  - `agent-coordinator/profiles/openbao.yaml` — new profile extending `local`
  - `agent-coordinator/docker-compose.yml` — OpenBao service definition
  - `agent-coordinator/Makefile` — `bao-dev`, `bao-seed` targets
  - `agent-coordinator/pyproject.toml` — `hvac` dependency (OpenBao-compatible Python client)
  - `scripts/bao-seed.py` — new bootstrap/seeding script
  - `scripts/worktree-bootstrap.sh` — conditional secret copying
- **BREAKING**: None. All changes are additive and opt-in via `BAO_ADDR`. Without `BAO_ADDR`, the system behaves identically to today. Local development with `.secrets.yaml` remains the default path.
