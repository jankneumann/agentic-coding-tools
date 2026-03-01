# Delta Spec: Configuration — Profile-Based Loading

## ADDED Requirements

### Requirement: Profile-Based Configuration

The configuration system SHALL support YAML-based deployment profiles with inheritance, secret interpolation, and environment variable override.

- Profile files SHALL reside in `agent-coordinator/profiles/` as `<name>.yaml`
- A profile MAY declare `extends: <parent>` to inherit settings from another profile
- Inheritance SHALL use deep merge: child dict keys override parent dict keys at any depth; scalars and lists replace entirely
- Circular inheritance SHALL be detected and SHALL raise an error
- The active profile SHALL be determined by: explicit argument > `COORDINATOR_PROFILE` env var > `"local"` default
- When no `profiles/` directory exists, the system SHALL fall back to pure env-var behavior with no error

#### Scenario: Local profile loads successfully
- **WHEN** `COORDINATOR_PROFILE=local` and `profiles/local.yaml` exists with `extends: base`
- **THEN** base settings are deep-merged with local overrides
- **AND** resolved values are injected into `os.environ` as defaults

#### Scenario: Env var overrides profile value
- **WHEN** `POSTGRES_DSN` is set in both the environment and the active profile
- **THEN** the environment variable value SHALL take precedence
- **AND** the profile value SHALL be ignored

#### Scenario: No profiles directory
- **WHEN** the `profiles/` directory does not exist
- **THEN** `Config.from_env()` SHALL behave identically to the current implementation
- **AND** no error SHALL be raised

#### Scenario: Circular inheritance detected
- **WHEN** profile A extends B and profile B extends A
- **THEN** the loader SHALL raise a `ValueError` with a message identifying the cycle

### Requirement: Secret Interpolation

Profile values SHALL support `${VAR}` interpolation syntax resolved against `.secrets.yaml` and environment variables.

- `${VAR}` SHALL resolve by checking `.secrets.yaml` first, then environment variables
- `${VAR:-default}` SHALL fall back to `default` when the variable is not found in either source
- `$${VAR}` SHALL produce the literal string `${VAR}` (escape syntax)
- Unresolvable `${VAR}` (no default, not in secrets, not in env) SHALL be left as the literal `${VAR}` string so downstream code can surface a clear error
- `.secrets.yaml` SHALL be gitignored; `.secrets.yaml.example` SHALL be git-tracked as a template

#### Scenario: Secret resolved from .secrets.yaml
- **WHEN** profile contains `postgres_dsn: "postgresql://postgres:${DB_PASSWORD}@localhost:54322/postgres"`
- **AND** `.secrets.yaml` contains `DB_PASSWORD: "mypassword"`
- **THEN** the resolved value SHALL be `"postgresql://postgres:mypassword@localhost:54322/postgres"`

#### Scenario: Secret resolved from env var (secrets file absent)
- **WHEN** `.secrets.yaml` does not exist
- **AND** env var `DB_PASSWORD=envpass` is set
- **THEN** `${DB_PASSWORD}` SHALL resolve to `"envpass"`

#### Scenario: Default value used
- **WHEN** `${COORDINATION_ALLOWED_HOSTS:-}` is in a profile
- **AND** `COORDINATION_ALLOWED_HOSTS` is not set anywhere
- **THEN** the resolved value SHALL be `""` (empty string)

### Requirement: Field-to-Environment Mapping

The profile loader SHALL use an explicit mapping from profile YAML paths to environment variable names.

- The mapping SHALL be auditable (defined as a constant, not generated dynamically)
- The `docker` block in profiles SHALL NOT be mapped to environment variables (it is profile-only metadata)
- The `providers` block SHALL NOT be mapped to environment variables (it is profile-only metadata)

#### Scenario: Settings mapped to env vars
- **WHEN** local profile contains `settings.postgres_dsn`
- **THEN** the value SHALL be injected as `POSTGRES_DSN` in `os.environ`

#### Scenario: Docker block not mapped
- **WHEN** local profile contains `docker.enabled: true`
- **THEN** no `DOCKER_ENABLED` environment variable SHALL be created
