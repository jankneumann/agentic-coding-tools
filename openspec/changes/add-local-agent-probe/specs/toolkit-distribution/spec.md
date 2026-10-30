## ADDED Requirements

### Requirement: Informational Vendor Probe Report

After its mirror-parity and stamp checks, `install.sh --check` SHALL print a vendor probe report
produced by `vendor_probe.py report` — one row per resolvable CLI lane with its version and
L0/L1/L2 status, and a remediation hint for each failing tier — bounded by a 60-second overall
timeout. The report SHALL NOT affect the exit code: `--check` SHALL exit with exactly the status
the drift checks alone produce. When the report cannot be produced (no `python3`, no resolvable
agents configuration, timeout, or probe error) it SHALL print a single line beginning
`probe report unavailable:` with the reason. Zero dispatchable vendors SHALL be reported as a
valid state, not an error.

#### Scenario: No vendor CLIs installed
- **WHEN** `--check` runs on a target whose mirrors match and no vendor CLI is on `PATH`
- **THEN** it SHALL print a report with every lane failing L0, and exit `0`

#### Scenario: Drift still fails regardless of the report
- **WHEN** a mirror has runtime drift and every vendor probe passes
- **THEN** `--check` SHALL exit `1`

#### Scenario: Unresolvable config is reported, not fatal
- **WHEN** `--check` runs in a consumer repo with no `AGENTS_YAML`, no `COORDINATION_API_URL`, and no local `agent-coordinator/agents.yaml`
- **THEN** it SHALL print `probe report unavailable: no agents configuration resolved` and its exit code SHALL be unchanged

#### Scenario: A bare interpreter without PyYAML is reported, not fatal
- **WHEN** `--check` runs where `skills/.venv` is absent and `python3` cannot import `yaml`
- **THEN** it SHALL print a line beginning `probe report unavailable:` and its exit code SHALL be unchanged

#### Scenario: A hung probe is cut off at the overall timeout
- **WHEN** `--check` runs and a lane's fake CLI never exits
- **THEN** `--check` SHALL finish within the 60-second report bound plus its drift checks, print a report or a `probe report unavailable: timeout` line, and exit with the drift checks' status
