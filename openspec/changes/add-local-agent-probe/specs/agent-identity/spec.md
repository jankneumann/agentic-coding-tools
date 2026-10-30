## ADDED Requirements

### Requirement: Declarative CLI Probe Block

An agent's `cli` block in `agents.yaml` MAY declare a `probe` object with optional keys
`version_args` (string list, default `["--version"]`), `help_args` (map of mode name to string
list), `auth_status_args` (string list), `credential_files` (string list of paths), and
`ignore_flags` (string list; each item starts with `-`). `AGENTS_SCHEMA` SHALL accept exactly these keys and reject others. Every declared list SHALL be
non-empty, and it SHALL reject any probe argv — `version_args`, a `help_args` value, or
`auth_status_args` — in which any token matches `print-api-key`, `print-bearer-token`,
`--credentials`, `--show-token`, or `logout` (case-insensitive). Loading SHALL additionally fail — via `agents_config.validate`, because
these rules are not expressible in JSON Schema — for an `auth_status_args` list whose
last token is `login`, and for a `help_args` value none of whose tokens is exactly `--help`, `-h`, or `help` (whole-token
match; `--helpful` does not count). `CliConfig` SHALL carry the block, and `get_dispatch_configs()` SHALL include
`probe` in a lane's `cli` payload when, and only when, it is declared — a declared empty `{}`
included (presence, not truthiness).

#### Scenario: A credential-printing auth command is rejected at load
- **WHEN** an agent declares `probe: {auth_status_args: ["auth", "print-api-key", "--provider", "openai"]}`
- **THEN** loading `agents.yaml` SHALL fail schema validation naming the offending token

#### Scenario: A credential-printing version command is rejected at load
- **WHEN** an agent declares `probe: {version_args: ["auth", "print-api-key"]}`
- **THEN** loading `agents.yaml` SHALL fail validation naming the offending token

#### Scenario: A help override that is not a help command is rejected
- **WHEN** an agent declares `probe: {help_args: {review: ["exec", "-s", "read-only"]}}`
- **THEN** loading `agents.yaml` SHALL fail validation

#### Scenario: An empty declared list is rejected
- **WHEN** an agent declares `probe: {ignore_flags: []}` or `probe: {credential_files: []}`
- **THEN** loading `agents.yaml` SHALL fail schema validation

#### Scenario: A status subcommand under login is accepted, a bare login is not
- **WHEN** one agent declares `probe: {auth_status_args: ["login", "status"]}` and another declares `probe: {auth_status_args: ["login"]}`
- **THEN** the first SHALL validate and the second SHALL fail validation

#### Scenario: An empty probe block survives the round-trip
- **WHEN** an agent declares `probe: {}`
- **THEN** `GET /agents/dispatch-configs` SHALL return `cli.probe` as `{}` for that lane, and the dispatcher's mirror `CliConfig.probe` SHALL be `{}`, not `None`

#### Scenario: An unknown probe key is rejected
- **WHEN** an agent declares `probe: {required_flags: ["--json-schema"]}`
- **THEN** loading `agents.yaml` SHALL fail schema validation

#### Scenario: The probe block round-trips through dispatch-configs
- **WHEN** `claude-local` declares `probe: {auth_status_args: ["auth", "status"]}`
- **THEN** `GET /agents/dispatch-configs` SHALL return that object under `claude-local`'s `cli.probe`, and a lane without a probe block SHALL have no `probe` key
