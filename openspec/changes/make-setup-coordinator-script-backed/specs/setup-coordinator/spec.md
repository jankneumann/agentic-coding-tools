# setup-coordinator Specification Delta

## MODIFIED Requirements

### Requirement: Profile-Aware Setup

The setup-coordinator skill SHALL accept a `--profile <local|railway>` argument and drive setup steps from the active profile. Profile resolution, precondition checking, and capability reporting SHALL be performed by the skill's own script entrypoint rather than by shell fragments narrated in `SKILL.md`.

- When `--profile` is not provided, the skill SHALL read `COORDINATOR_PROFILE` env var, defaulting to `"local"`
- The skill SHALL read `agents.yaml` to determine which agents to configure, resolving its location from the `AGENTS_YAML` env var when set and otherwise from `$COORDINATOR_DIR/agents.yaml`
- The skill SHALL check for `.secrets.yaml` and prompt the user to create it from `.secrets.yaml.example` if missing
- Profile resolution SHALL be implemented against the profile YAML directly and SHALL NOT import `agent-coordinator` source modules

#### Scenario: Local profile setup
- **WHEN** `--profile local` is specified
- **THEN** the skill SHALL:
  1. Detect container runtime (Docker / Podman)
  2. Auto-start ParadeDB container if `docker.auto_start` is true
  3. Wait for container health
  4. Register MCP server in vendor config (e.g., `~/.claude/mcp.json`) with env vars from `get_mcp_env()`
  5. Verify MCP tool discovery
  6. Report capability flags

#### Scenario: Railway profile setup
- **WHEN** `--profile railway` is specified
- **THEN** the skill SHALL:
  1. Verify `COORDINATION_API_URL` is resolved (from profile + secrets)
  2. Test API health via `curl $COORDINATION_API_URL/health`
  3. Verify API key acceptance on a write endpoint
  4. Run `coordination_bridge.py detect` to verify capability flags
  5. Report capability flags

#### Scenario: Secrets file missing
- **WHEN** `.secrets.yaml` does not exist
- **THEN** the skill SHALL copy `.secrets.yaml.example` to `.secrets.yaml`
- **AND** prompt the user to fill in real values before continuing

#### Scenario: Agents file resolved from configuration
- **WHEN** the skill resolves which agents to configure
- **THEN** it SHALL read the file named by `AGENTS_YAML` if that variable is set
- **AND** otherwise read `$COORDINATOR_DIR/agents.yaml`
- **AND** when neither location yields a readable file it SHALL report both locations it tried and exit non-zero rather than configuring a default agent set

#### Scenario: Agent roster is never fetched over the network
- **WHEN** the skill resolves the agent roster with `COORDINATION_API_URL` set in the environment
- **THEN** it SHALL resolve only from the filesystem locations named above
- **AND** SHALL NOT issue a network request to obtain a roster
- **AND** SHALL NOT fall back to a roster relative to the current working directory

## ADDED Requirements

### Requirement: Script-Backed Entrypoint

The skill SHALL provide an executable entrypoint at `skills/setup-coordinator/scripts/setup_coordinator.py` exposing the subcommands `detect-harnesses`, `check`, `configure`, and `report`. `SKILL.md` SHALL invoke this entrypoint rather than restating its logic as shell fragments.

- Each subcommand SHALL be implemented as a `cmd_<name>(args) -> int` handler returning an exit code rather than calling `sys.exit` directly
- The entrypoint SHALL expose `main(argv: list[str] | None = None) -> int` so tests can invoke it without a subprocess
- Every subcommand SHALL accept `--json` for machine-readable output, bound to a destination other than `json` so the handler does not shadow the `json` module
- Exit codes SHALL be binary: `0` when the requested state is satisfied, non-zero when it is not

#### Scenario: Subcommand dispatch
- **WHEN** `setup_coordinator.py` is invoked with a recognized subcommand
- **THEN** the corresponding handler SHALL run and its integer return value SHALL become the process exit code

#### Scenario: Machine-readable output
- **WHEN** any subcommand is invoked with `--json`
- **THEN** the process SHALL emit a single JSON document on stdout
- **AND** SHALL NOT interleave human-readable table output with it

#### Scenario: No subcommand supplied
- **WHEN** `setup_coordinator.py` is invoked with no subcommand
- **THEN** it SHALL print usage and exit non-zero

### Requirement: Harness Presence Detection

The skill SHALL detect which coding-agent harnesses are present on the current host and SHALL report presence only, never inferred credential validity. Detection SHALL NOT issue billed inference calls.

- Detection SHALL reuse `vendor_health.check_all_vendors()` for the CLI-on-PATH and environment-variable credential layers, without modifying that module, passing it a filesystem path the skill has already resolved and confirmed to exist
- Detection SHALL additionally check for a vendor's home-directory configuration artifact
- Detection SHALL report exactly the agents whose identifier ends in `-local` and that declare a non-empty `cli.command`, and SHALL derive the reported vendor key by removing the `-local` suffix
- Each vendor SHALL be classified into exactly one of four states: `ready` (CLI present and config artifact present), `cli_missing`, `config_missing`, or `unknown` (the vendor has no detectable configuration location)
- Output SHALL state that presence is not proof of valid or unexpired credentials

#### Scenario: Remote and command-less agents are excluded
- **WHEN** the resolved agent roster contains agents whose identifier does not end in `-local`
- **THEN** those agents SHALL NOT appear in the report
- **AND** the report SHALL contain at most one entry per vendor key
- **AND** an agent declaring an empty `cli.command` SHALL likewise be excluded rather than reported with an empty command

#### Scenario: Vendor fully present
- **WHEN** a vendor's CLI is on PATH and its home-directory configuration artifact exists
- **THEN** the vendor SHALL be reported with state `ready`

#### Scenario: Vendor CLI absent
- **WHEN** a vendor's CLI is not on PATH
- **THEN** the vendor SHALL be reported with state `cli_missing`
- **AND** the report SHALL name the CLI command that was searched for

#### Scenario: Vendor has no detectable config location
- **WHEN** a vendor declares no home-directory configuration artifact to check
- **THEN** the vendor SHALL be reported with state `unknown`
- **AND** SHALL NOT be reported as `config_missing`
- **AND** the report SHALL NOT instruct the operator to run a login command for that vendor

#### Scenario: Presence is not validity
- **WHEN** a vendor is reported as `ready`
- **THEN** the output SHALL indicate that credential validity and expiry were not checked

### Requirement: Atomic Permission Allowlist Update

The `configure` subcommand SHALL add the `mcp__coordination__*` wildcard to the Claude Code permissions allow-list without the defects present in the shell-fragment implementation it replaces.

- The settings file path SHALL be resolved absolutely from an explicit root, and SHALL NOT depend on the process working directory
- The write SHALL preserve all unrelated keys, values, and ordering; only the permissions allow-list SHALL differ between input and output
- Serialization SHALL NOT canonicalize the document: key order SHALL be the order read from the input, and the input's indentation and trailing-newline convention SHALL be preserved
- The write SHALL be atomic — a temporary file replaced into position — so a concurrent reader observes either the old or the new content, never a partial file
- The "already present" check SHALL be scoped to the allow-list, and SHALL NOT be satisfied by the wildcard appearing in a `deny` list or any other key
- Applying the change to a file that already carries the wildcard in its allow-list SHALL make no modification to the file
- Individual `mcp__coordination__<tool>` entries SHALL be replaced by the single wildcard

#### Scenario: Wildcard added to a settings file with unrelated keys
- **WHEN** `configure` runs against a settings file containing sibling top-level keys and an allow-list without the wildcard
- **THEN** the wildcard SHALL be appended to the allow-list
- **AND** every sibling top-level key SHALL be byte-identical to its prior value

#### Scenario: Wildcard present only in the deny list
- **WHEN** the settings file contains `mcp__coordination__*` in a `deny` list but not in `allow`
- **THEN** `configure` SHALL add the wildcard to the allow-list
- **AND** SHALL NOT report the permission as already configured

#### Scenario: Settings file is not in canonical JSON form
- **WHEN** `configure` runs against a settings file whose top-level keys are not in sorted order, or whose indentation is not two spaces
- **THEN** the output SHALL retain the input's key order and indentation
- **AND** the only textual difference between input and output SHALL fall inside the permissions allow-list

#### Scenario: Idempotent re-run
- **WHEN** `configure` runs against a settings file that already carries the wildcard in its allow-list
- **THEN** the file SHALL NOT be modified
- **AND** the command SHALL report success
- **AND** this SHALL hold whether or not the file is in canonical JSON form, so that a re-run against an externally formatted file is still a no-op

#### Scenario: Concurrent reader safety
- **WHEN** the settings file is written
- **THEN** the write SHALL be performed to a temporary file and moved into place atomically
- **AND** no reader SHALL observe truncated or partially written content

#### Scenario: Working directory independence
- **WHEN** `configure` is invoked from a directory other than the settings file's repository root
- **THEN** it SHALL operate on the settings file resolved from its explicit root argument
- **AND** SHALL NOT create a settings file relative to the current working directory

### Requirement: Portable Skill Payload

The entrypoint SHALL remain usable when installed into a consumer repository that does not contain `agent-coordinator/`.

- The entrypoint SHALL import only the Python standard library and sibling skill modules at module scope
- The entrypoint SHALL NOT import `agent-coordinator` source modules
- Sibling-skill imports SHALL be declared in `cross_skill_dependencies` in `skills/install-manifest.json`
- Where a sibling module may be absent from an installed payload, the import SHALL degrade to an inline fallback rather than raising at import time
- Where a sibling module depends on a third-party package that a consumer payload may not provide, the resulting failure SHALL be caught at the point of use and reported as a degraded capability

#### Scenario: Sibling skill unavailable
- **WHEN** a sibling skill module is not present in the installed payload
- **THEN** the entrypoint SHALL continue to load
- **AND** the affected capability SHALL degrade with a reported warning rather than aborting the process

#### Scenario: Entrypoint loads in a consumer payload with no source checkout
- **WHEN** the installed payload is invoked with `--help` from a repository that contains no `agent-coordinator/` checkout and no `PYTHONPATH`
- **THEN** the entrypoint SHALL exit zero
- **AND** SHALL NOT require a third-party package to be importable at module scope

#### Scenario: Dependency direction enforced
- **WHEN** the repository dependency-direction linter runs over the skills tree
- **THEN** it SHALL report no `agent-coordinator` import originating from `skills/setup-coordinator/`

### Requirement: Test Suite Registration

The skill's test suite SHALL live at `skills/tests/setup-coordinator/` and SHALL be discoverable by the repository's continuous integration configuration.

- The suite directory SHALL be listed in `testpaths` in `skills/pyproject.toml`
- The suite SHALL NOT contain an `__init__.py`, so that the module under test resolves from the `sys.path` entry established in `conftest.py`
- Tests SHALL operate on temporary fixtures and SHALL NOT read or modify the operator's real home-directory configuration or the repository's own settings file

#### Scenario: Suite is collected by CI
- **WHEN** the skills test suite is collected using the repository's pytest configuration **without naming the suite directory as an argument**
- **THEN** the tests under `skills/tests/setup-coordinator/` SHALL be collected and executed
- **AND** a collection run that names the directory explicitly SHALL NOT be accepted as evidence, because it bypasses `testpaths`

#### Scenario: Tests do not touch operator state
- **WHEN** the suite runs
- **THEN** every filesystem write SHALL target a temporary directory
- **AND** no assertion SHALL depend on the contents of the operator's real home directory
