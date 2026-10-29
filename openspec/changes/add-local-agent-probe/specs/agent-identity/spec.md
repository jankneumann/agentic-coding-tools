## ADDED Requirements

### Requirement: Declarative CLI Probe Block

An agent's `cli` block in `agents.yaml` MAY declare a `probe` object with optional keys
`version_args` (string list, default `["--version"]`), `help_args` (map of mode name to string
list), `auth_status_args` (string list), `credential_files` (string list of paths), and
`ignore_flags` (string list). `AGENTS_SCHEMA` SHALL accept exactly these keys and reject others.
It SHALL reject an `auth_status_args` list in which any token matches `print-api-key`,
`print-bearer-token`, `--credentials`, `--show-token`, or `logout` (case-insensitive), or whose
last token is `login`. `CliConfig` SHALL carry the block, and `get_dispatch_configs()` SHALL include
`probe` in a lane's `cli` payload when, and only when, it is declared.

#### Scenario: A credential-printing auth command is rejected at load
- **WHEN** an agent declares `probe: {auth_status_args: ["auth", "print-api-key", "--provider", "openai"]}`
- **THEN** loading `agents.yaml` SHALL fail schema validation naming the offending token

#### Scenario: A status subcommand under login is accepted, a bare login is not
- **WHEN** one agent declares `probe: {auth_status_args: ["login", "status"]}` and another declares `probe: {auth_status_args: ["login"]}`
- **THEN** the first SHALL validate and the second SHALL fail validation

#### Scenario: An unknown probe key is rejected
- **WHEN** an agent declares `probe: {required_flags: ["--json-schema"]}`
- **THEN** loading `agents.yaml` SHALL fail schema validation

#### Scenario: The probe block round-trips through dispatch-configs
- **WHEN** `claude-local` declares `probe: {auth_status_args: ["auth", "status"]}`
- **THEN** `GET /agents/dispatch-configs` SHALL return that object under `claude-local`'s `cli.probe`, and a lane without a probe block SHALL have no `probe` key
