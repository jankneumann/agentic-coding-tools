## ADDED Requirements

### Requirement: Health Check Delegates to the Tiered Probe

`vendor_health.py` SHALL obtain CLI availability, per-mode capability, and auth status from the
shared tiered probe (`vendor_probe.py`) instead of its own `shutil.which` check, so that
`/vendor-status` and `review_dispatcher.py --check-vendors` report the same verdict for the same
lane. Its existing `--json` fields (`cli_installed`, `api_key_available`, `dispatch_modes`,
`models`, `healthy`, `error`) SHALL keep their meaning, except that `dispatch_modes` narrows from
"configured modes when the CLI is installed" to "modes that pass L1" — for a lane without a
`probe` block this equals today's list whenever `--version` succeeds. It SHALL add `cli_version`, `missing_flags` (per mode), and `auth_status`
(`auth_ok`, `auth_failed`, `auth_unknown`, `probe_timeout`). A lane SHALL NOT be `healthy` when
`auth_status` is `auth_failed`. The probe SHALL remain loadable from the coordinator container
by file path alongside `vendor_health.py`, using only the standard library. The `vendor_health`
CLI SHALL re-probe; the programmatic `check_all_vendors()` used by the coordinator watchdog SHALL
reuse fresh cache entries without starting subprocesses, and the watchdog SHALL run it off the
event loop (`asyncio.to_thread`).

#### Scenario: vendor-status and check-vendors agree
- **WHEN** a lane's CLI is installed but lacks a flag its `review` mode uses
- **THEN** `vendor_health --json` SHALL omit `review` from that lane's `dispatch_modes` and report it in `missing_flags`, and `--check-vendors --json` SHALL list the lane as `unverified` for `review` with reason `missing_flags`

#### Scenario: An expired login makes a lane unhealthy
- **WHEN** a lane's CLI and flags pass and its auth-status command exits 1
- **THEN** `vendor_health --json` SHALL report `auth_status: "auth_failed"` and `healthy: false` for that lane

#### Scenario: The watchdog loader still works
- **WHEN** `agent-coordinator/src/watchdog.py` loads `vendor_health.py` by path from a directory that also contains `vendor_probe.py` and has no PyYAML installed
- **THEN** `check_all_vendors` SHALL run without an import error

#### Scenario: The watchdog reuses fresh probe results
- **WHEN** `check_all_vendors()` is called twice within the probe TTL against fake CLIs that record their argv
- **THEN** the second call SHALL start no subprocesses and SHALL return the same verdicts

#### Scenario: Health probes stay token-free
- **WHEN** the health check runs against fake CLIs that record every argv they receive
- **THEN** no recorded argv SHALL equal or contain a dispatch-mode `args` vector
