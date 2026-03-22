## ADDED Requirements

### Requirement: OpenBao Secret Backend

The configuration system SHALL support OpenBao (Vault-compatible) as an alternative secret source alongside `.secrets.yaml`, activated by the presence of the `BAO_ADDR` environment variable.

- When `BAO_ADDR` is set, `_load_secrets()` SHALL authenticate to OpenBao using AppRole auth and read secrets from the KV v2 mount path
- When `BAO_ADDR` is not set, `_load_secrets()` SHALL continue using `.secrets.yaml` (existing behavior, unchanged)
- The OpenBao client SHALL use `BAO_ROLE_ID` and `BAO_SECRET_ID` environment variables for AppRole authentication
- The KV v2 mount path SHALL default to `secret` and be configurable via `BAO_MOUNT_PATH`
- The secret data path SHALL default to `coordinator` and be configurable via `BAO_SECRET_PATH`
- Secrets retrieved from OpenBao SHALL be returned as a flat `str→str` dict, identical in shape to the `.secrets.yaml` output
- The `${VAR}` interpolation layer, profile inheritance, and `FIELD_ENV_MAP` injection SHALL remain unchanged — only the secret source changes
- Authentication failures SHALL raise a clear error with the OpenBao address and role ID for debugging
- Network timeouts to OpenBao SHALL be configurable via `BAO_TIMEOUT` (default: 5 seconds)

#### Scenario: Secrets loaded from OpenBao when BAO_ADDR is set
- **WHEN** `BAO_ADDR=http://localhost:8200` is set in the environment
- **AND** `BAO_ROLE_ID` and `BAO_SECRET_ID` are set
- **AND** OpenBao KV v2 at `secret/data/coordinator` contains `{"DB_PASSWORD": "vault-pass", "CODEX_API_KEY": "key-from-vault"}`
- **THEN** `_load_secrets()` SHALL return `{"DB_PASSWORD": "vault-pass", "CODEX_API_KEY": "key-from-vault"}`
- **AND** profile interpolation of `${DB_PASSWORD}` SHALL resolve to `"vault-pass"`

#### Scenario: Fallback to .secrets.yaml when BAO_ADDR is not set
- **WHEN** `BAO_ADDR` is not set in the environment
- **THEN** `_load_secrets()` SHALL read from `.secrets.yaml` as before
- **AND** no OpenBao connection SHALL be attempted

#### Scenario: OpenBao authentication failure (invalid credentials)
- **WHEN** `BAO_ADDR` is set but `BAO_ROLE_ID` is invalid
- **THEN** `_load_secrets()` SHALL raise a `RuntimeError` with message containing the BAO_ADDR and the authentication error
- **AND** the coordinator SHALL not start with partial/missing secrets

#### Scenario: OpenBao authentication failure (missing credentials)
- **WHEN** `BAO_ADDR` is set but `BAO_ROLE_ID` or `BAO_SECRET_ID` is not set
- **THEN** `_load_secrets()` SHALL raise a `ValueError` indicating which required environment variable is missing
- **AND** the coordinator SHALL not start

#### Scenario: OpenBao unreachable
- **WHEN** `BAO_ADDR` is set but the server is unreachable
- **THEN** `_load_secrets()` SHALL raise a `ConnectionError` after the configured timeout
- **AND** the error message SHALL include `BAO_ADDR` for debugging

#### Scenario: OpenBao returns non-string values
- **WHEN** OpenBao KV v2 contains a key with a non-string value (e.g., integer, list, nested dict)
- **THEN** `_load_secrets_openbao()` SHALL filter the value out and log a warning
- **AND** the returned dict SHALL contain only string values, matching `.secrets.yaml` behavior

### Requirement: OpenBao Configuration Dataclass

The config module SHALL include an `OpenBaoConfig` dataclass for centralizing OpenBao connection settings.

- `OpenBaoConfig` SHALL be constructed from environment variables: `BAO_ADDR`, `BAO_ROLE_ID`, `BAO_SECRET_ID`, `BAO_MOUNT_PATH`, `BAO_SECRET_PATH`, `BAO_TIMEOUT`, `BAO_TOKEN_TTL`
- `BAO_TOKEN_TTL` SHALL default to `3600` (1 hour) and represent the token TTL in seconds
- `OpenBaoConfig.is_enabled()` SHALL return `True` when `BAO_ADDR` is set and non-empty
- `OpenBaoConfig` SHALL provide a `create_client()` method that returns an authenticated `hvac.Client`

#### Scenario: OpenBaoConfig from environment
- **WHEN** environment contains `BAO_ADDR=http://bao:8200`, `BAO_ROLE_ID=role-1`, `BAO_SECRET_ID=secret-1`
- **THEN** `OpenBaoConfig.from_env()` SHALL populate all fields with defaults for unset optional values
- **AND** `is_enabled()` SHALL return `True`

#### Scenario: OpenBaoConfig creates authenticated client
- **WHEN** `BAO_ADDR`, `BAO_ROLE_ID`, and `BAO_SECRET_ID` are set
- **AND** `create_client()` is called
- **THEN** the method SHALL return an `hvac.Client` connected to `BAO_ADDR`
- **AND** the client SHALL be authenticated via AppRole using the provided role ID and secret ID
- **AND** the client's `is_authenticated()` SHALL return `True`

#### Scenario: OpenBaoConfig disabled
- **WHEN** `BAO_ADDR` is not in the environment
- **THEN** `OpenBaoConfig.from_env()` SHALL return a config where `is_enabled()` returns `False`
- **AND** `create_client()` SHALL raise `RuntimeError("OpenBao is not configured")`

---

### Requirement: Bootstrap Seeding Script

A seeding script SHALL exist to populate OpenBao from `.secrets.yaml` and `agents.yaml`, enabling migration from file-based to vault-based secrets.

- `scripts/bao-seed.py` SHALL read `.secrets.yaml` and write each key-value pair to OpenBao KV v2 at the configured mount/path
- The script SHALL read `agents.yaml` and create an AppRole per HTTP-transport agent with a policy scoped to required secrets
- The script SHALL configure the database secrets engine connection and role when `--with-db-engine` is passed
- The script SHALL be idempotent: re-running updates existing secrets and roles without duplication
- The script SHALL support `--dry-run` to preview all changes without writing to OpenBao
- The script SHALL require `BAO_ADDR` and `BAO_TOKEN` (root/admin token) environment variables

#### Scenario: Seed secrets from .secrets.yaml
- **WHEN** `.secrets.yaml` contains `DB_PASSWORD: "mypass"` and `CODEX_API_KEY: "key123"`
- **AND** `bao-seed.py` is run with `BAO_ADDR` and `BAO_TOKEN` set
- **THEN** OpenBao KV v2 at `secret/data/coordinator` SHALL contain both key-value pairs
- **AND** the script SHALL print each key written (not the values)

#### Scenario: Seed AppRoles from agents.yaml
- **WHEN** `agents.yaml` defines `codex-cloud` with `transport: http` and `api_key: ${CODEX_API_KEY}`
- **THEN** `bao-seed.py` SHALL create an AppRole named `codex-cloud` in OpenBao
- **AND** the AppRole policy SHALL grant read access to `secret/data/coordinator` (shared path for MVP; per-agent sub-paths are a future enhancement)
- **AND** the AppRole token SHALL have a max TTL matching `BAO_TOKEN_TTL`

#### Scenario: Dry run previews without writing
- **WHEN** `bao-seed.py --dry-run` is run
- **THEN** the script SHALL print all planned operations (write secret, create role, configure engine)
- **AND** no changes SHALL be made to OpenBao

#### Scenario: Idempotent re-run
- **WHEN** `bao-seed.py` is run twice with the same `.secrets.yaml`
- **THEN** the second run SHALL update (not duplicate) existing secrets
- **AND** existing AppRoles SHALL be updated, not recreated

#### Scenario: Missing .secrets.yaml source file
- **WHEN** `bao-seed.py` is run but `.secrets.yaml` does not exist
- **THEN** the script SHALL exit with a non-zero exit code
- **AND** the error message SHALL indicate that `.secrets.yaml` is required as the source

#### Scenario: Missing BAO_TOKEN or BAO_ADDR for seeding
- **WHEN** `bao-seed.py` is run without `BAO_TOKEN` or `BAO_ADDR` set
- **THEN** the script SHALL exit with a non-zero exit code
- **AND** the error message SHALL indicate which required environment variable is missing

#### Scenario: agents.yaml missing during seeding
- **WHEN** `bao-seed.py` is run but `agents.yaml` does not exist
- **THEN** the script SHALL seed secrets from `.secrets.yaml` successfully
- **AND** AppRole creation SHALL be skipped with a warning message

### Requirement: Worktree Secret Handling

The worktree bootstrap process SHALL conditionally skip `.secrets.yaml` file copying when OpenBao is enabled, allowing agents in worktrees to authenticate independently.

- When `BAO_ADDR` is set, `worktree-bootstrap.sh` SHALL NOT copy or symlink `.secrets.yaml` into the worktree
- When `BAO_ADDR` is not set, `worktree-bootstrap.sh` SHALL continue to copy `.secrets.yaml` as before (existing behavior)
- Each worktree agent SHALL authenticate to OpenBao independently using its own AppRole credentials passed via environment variables

#### Scenario: Worktree bootstrap with OpenBao enabled
- **WHEN** `BAO_ADDR` is set in the environment
- **AND** `worktree-bootstrap.sh` is executed for a new worktree
- **THEN** the script SHALL NOT copy or symlink `.secrets.yaml` into the worktree
- **AND** a log message SHALL indicate that OpenBao is being used for secrets

#### Scenario: Worktree bootstrap without OpenBao (default)
- **WHEN** `BAO_ADDR` is not set in the environment
- **AND** `worktree-bootstrap.sh` is executed for a new worktree
- **THEN** the script SHALL copy or symlink `.secrets.yaml` into the worktree as before

---

## MODIFIED Requirements

### Requirement: Secret Interpolation (from configuration spec)

**MODIFIED**: The secret interpolation resolution order SHALL be extended to support OpenBao as a secret source.

- When OpenBao is enabled (`BAO_ADDR` set), secrets SHALL be resolved from OpenBao instead of `.secrets.yaml`
- The `${VAR}` and `${VAR:-default}` syntax SHALL remain identical
- The resolution order SHALL remain: secrets dict (now sourced from OpenBao or file) → `os.environ`
- Escape syntax `$${VAR}` SHALL continue to produce literal `${VAR}`

#### Scenario: Interpolation uses OpenBao secrets
- **WHEN** `BAO_ADDR` is set and OpenBao contains `DB_PASSWORD: "vault-pass"`
- **THEN** `${DB_PASSWORD}` in profile YAML SHALL resolve to `"vault-pass"`
- **AND** the interpolation syntax and behavior SHALL be identical to file-based resolution

#### Scenario: Interpolation uses .secrets.yaml when OpenBao is disabled
- **WHEN** `BAO_ADDR` is not set
- **AND** `.secrets.yaml` contains `DB_PASSWORD: "file-pass"`
- **THEN** `${DB_PASSWORD}` SHALL resolve to `"file-pass"` as before
