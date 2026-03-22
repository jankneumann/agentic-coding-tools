# Design: add-openbao-credential-management

## Context

The agent-coordinator loads secrets from `.secrets.yaml` via `profile_loader.py:_load_secrets()`, which returns a flat `str→str` dict. This dict feeds into `${VAR}` interpolation across all profile values — database DSNs, API keys, coordination keys. The file is copied to each git worktree by `worktree-bootstrap.sh`. For local single-developer use this works, but it blocks three cloud-deployment requirements: credential rotation without restart, per-agent credential scoping, and revocation when a session ends or key leaks.

OpenBao (the Linux Foundation / OpenSSF fork of HashiCorp Vault, post-BSL license change) provides:
- **KV v2**: Versioned key-value store (drop-in replacement for `.secrets.yaml`)
- **AppRole auth**: Machine identity with scoped policies (maps to `agents.yaml` entries)
- **Database secrets engine**: Per-client PostgreSQL credentials with automatic TTL expiry
- **Audit logging**: Built-in record of every secret read/write

### Stakeholders
- **Agent developers**: Need credentials without managing files; dynamic DB creds simplify local → cloud migration
- **Platform operators**: Need rotation, revocation, and audit without redeploying
- **Security reviewers**: Need per-agent credential scoping and audit trail

### Constraints
- MUST not break local development (`.secrets.yaml` path must remain default)
- MUST use the same `dict[str, str]` interface that `_load_secrets()` returns today
- MUST not require OpenBao for test suites (tests use env vars or fixtures)
- `hvac` (Python Vault/OpenBao client) is the only new runtime dependency
- OpenBao dev server auto-unseals — no production unsealing workflow needed for MVP

## Goals / Non-Goals

**Goals:**
- Replace `.secrets.yaml` with OpenBao as the secret source when `BAO_ADDR` is set
- Map `agents.yaml` entries to AppRoles for per-agent credential scoping
- Enable per-agent dynamic PostgreSQL credentials via the database secrets engine
- Provide a seeding script to migrate from `.secrets.yaml` to OpenBao
- Add Docker Compose dev profile for local OpenBao testing

**Non-Goals:**
- Production unsealing workflow (Shamir/auto-unseal) — deferred to deployment guide
- Transit secrets engine for encryption-as-a-service — not needed yet
- Multi-cluster OpenBao replication — single-instance is sufficient
- UI/dashboard for OpenBao — CLI and API are sufficient
- Replacing the profile inheritance system — only the secret source changes
- Response-wrapping for SecretID delivery — a security hardening step for production; MVP uses direct `BAO_SECRET_ID` env var
- Per-agent sub-path scoping in OpenBao policies — MVP uses a shared `secret/data/coordinator` read policy; granular per-secret scoping deferred

## Decisions

### Decision 1: OpenBao over HashiCorp Vault

**Choice**: Use OpenBao (LF/OpenSSF fork) instead of HashiCorp Vault.

**Alternatives considered:**
- **HashiCorp Vault**: Industry standard, but BSL-licensed since August 2023. Cannot be embedded in open-source tooling without license concerns. API-identical to OpenBao for our use cases.
- **AWS Secrets Manager / GCP Secret Manager**: Cloud-native, managed. But locks to a specific cloud provider and doesn't run locally for development.
- **SOPS (Mozilla)**: Encrypts secrets at rest in git. Simple but no dynamic credentials, no per-agent scoping, no audit log, no revocation.
- **Infisical**: Open-source secret manager. Less mature ecosystem, no database secrets engine equivalent, smaller community.

**Rationale**: OpenBao is API-compatible with Vault (uses the same `hvac` Python client), permissively licensed (MPL-2.0), backed by LF/OpenSSF, and provides all three required engines (KV v2, AppRole, database). Zero migration cost if the team ever needs to switch to Vault Enterprise.

### Decision 2: AppRole auth over token-based or Kubernetes auth

**Choice**: Use AppRole auth method for agent identity binding.

**Alternatives considered:**
- **Static tokens**: Simplest. But tokens don't expire, can't be scoped per-agent, and if leaked grant full access until manually revoked.
- **Kubernetes auth**: Natural for K8s deployments. But the coordinator runs in Docker Compose locally and on Railway in cloud — neither is K8s.
- **TLS certificate auth**: Strong identity. But requires PKI infrastructure, certificate distribution, and rotation — heavy for our use case.
- **Userpass**: Designed for humans. Passwords in env vars are equivalent to current `.secrets.yaml` with extra steps.

**Rationale**: AppRole is designed for machine-to-machine auth. The `role_id` (public, identifies the agent type) + `secret_id` (private, one-time-use for session binding) model maps directly to our `agents.yaml` entries. Secret IDs can be wrapped (response-wrapping) for single-use, preventing replay.

### Decision 3: Conditional dispatch in `_load_secrets()` over a provider abstraction

**Choice**: Simple `if BAO_ADDR: load_from_openbao() else: load_from_file()` conditional in the existing `_load_secrets()` function.

**Alternatives considered:**
- **SecretProvider interface + registry**: Extensible, supports future backends (AWS SM, GCP SM). But introduces an abstraction layer for exactly two backends, violating YAGNI. Can be refactored later if a third backend appears.
- **Separate entry points**: `_load_secrets_file()` and `_load_secrets_openbao()` called from `load_profile()`. Spreads the decision across call sites.

**Rationale**: The conditional is one `if/else` in a single function. Both backends return the same `dict[str, str]`. The rest of the profile loading pipeline (`interpolate()`, `_interpolate_tree()`, `_inject_env()`) is completely unaware of where secrets came from. Minimal change, maximum clarity.

### Decision 4: `hvac` client library over raw HTTP

**Choice**: Use the `hvac` Python library (Vault/OpenBao client).

**Alternatives considered:**
- **Raw `httpx`/`requests` calls**: No new dependency. But reimplements AppRole login flow, KV v2 read (versioned response unwrapping), database credential generation, and lease renewal. Error-prone and maintains a large surface.
- **`ansible-modules-hashivault`**: Ansible-oriented, not designed for runtime use in Python applications.

**Rationale**: `hvac` is the standard Python client for Vault-compatible APIs, well-maintained, and API-compatible with OpenBao. It handles auth token lifecycle, response unwrapping, and engine-specific request formatting. One dependency vs. hundreds of lines of HTTP client code.

### Decision 5: Docker Compose dev mode (auto-unseal) for local testing

**Choice**: Run OpenBao in dev mode (`openbao server -dev`) in Docker Compose for local development.

**Alternatives considered:**
- **Shared dev OpenBao instance**: Team-wide server. But requires network access, doesn't work offline, and introduces a shared dependency.
- **Testcontainers in pytest**: Ephemeral per-test-run. Good for CI but slow for iterative development (container startup per run).
- **Mock `hvac` client in tests**: No real OpenBao needed. Best for unit tests, but doesn't validate the actual API interaction.

**Rationale**: Dev mode auto-unseals with a root token, starts in <1 second, and resets on restart. Combined with `bao-seed.py`, developers get a fully populated OpenBao in one `make bao-dev` command. Unit tests continue to mock `hvac`; integration tests can use the dev container.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|------|----------|------------|
| OpenBao dev server data loss on restart | Low | Dev mode is ephemeral by design; `bao-seed.py` re-populates in seconds. Production uses persistent storage. |
| `hvac` library compatibility with OpenBao | Medium | OpenBao maintains Vault API compatibility. `hvac` works unchanged. Pin `hvac>=2.1.0` for KV v2 support. Test in CI against OpenBao container. |
| Developers must install Docker for OpenBao testing | Low | OpenBao is opt-in (`BAO_ADDR`). Default path remains `.secrets.yaml` with no Docker dependency. |
| AppRole secret_id leaks | Medium | MVP: SecretIDs are passed via environment variables with short TTLs. Future enhancement: response-wrapping (single-use tokens) for production hardening. Rotate SecretIDs regularly. |
| Database secrets engine generates many PostgreSQL roles | Low | Roles auto-expire after TTL. Add a cleanup cron or use max_ttl to bound accumulation. Dev mode: roles vanish on restart. |
| Network dependency on OpenBao at startup | Medium | Fail-fast with clear error. No silent fallback to `.secrets.yaml` when `BAO_ADDR` is set — that would mask misconfiguration. |

## Migration Plan

### Phase 1: Core Integration (this change)
1. Add `hvac` dependency to `pyproject.toml`
2. Add `OpenBaoConfig` dataclass to `config.py`
3. Add `_load_secrets_openbao()` to `profile_loader.py` with conditional dispatch
4. Create `scripts/bao-seed.py` for initial population
5. Add OpenBao dev service to `docker-compose.yml`
6. Add `openbao.yaml` profile extending `local.yaml`
7. Update `worktree-bootstrap.sh` to skip file copy when `BAO_ADDR` is set
8. Add `openbao_role_id` field to agents config

### Phase 2: Dynamic Database Credentials (this change, gated)
9. Configure database secrets engine in `bao-seed.py --with-db-engine`
10. Add dynamic DSN resolution to profile loader when database engine is available

### Rollback
- Unset `BAO_ADDR` → immediate revert to `.secrets.yaml` behavior
- Remove `hvac` from dependencies and OpenBao-related code if feature is abandoned
- No database schema changes — rollback is code-only
