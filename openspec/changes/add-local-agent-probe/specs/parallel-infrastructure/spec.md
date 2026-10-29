## ADDED Requirements

### Requirement: Tiered Local Vendor Probe

The parallel-infrastructure skill SHALL provide one probe implementation,
`vendor_probe.py`, that evaluates each configured CLI lane on the local machine in three
token-free tiers: **L0 presence** (`shutil.which(command)`), **L1 capability** (the lane's
version command succeeds and every flag the lane's dispatch mode passes appears as a whole
token in that mode's help output), and **L2 auth** (a declared auth-status command exits 0, or
every declared credential file exists). Required flags SHALL be derived from the mode's
`dispatch_modes.<mode>.args` and from `cli` keys whose name ends in `_flag`, minus
`probe.ignore_flags`; the help command SHALL be `[command, <leading non-flag args>, "--help"]`
unless `probe.help_args` is declared. Every probe subprocess SHALL run with `stdin` closed and a
10-second timeout, and the probe SHALL NOT execute any dispatch-mode argument vector (so no
model request is ever sent).

#### Scenario: A flag missing from help output fails L1 for that mode only
- **WHEN** a lane's `review` mode passes `--json-schema` and the fake CLI's `--help` output does not contain `--json-schema`, while its `alternative` mode's flags are all present
- **THEN** the probe SHALL report `review` as failed with reason `missing_flags` listing `--json-schema`, and SHALL report `alternative` as passed

#### Scenario: Subcommand flags are checked against subcommand help
- **WHEN** a lane declares `review: {args: ["exec", "-s", "read-only"]}` and no `probe.help_args`
- **THEN** the probe SHALL run `[command, "exec", "--help"]` and check it for `-s`

#### Scenario: Injected flags are required
- **WHEN** a lane declares `model_flag: "-m"` and the help output lacks `-m`
- **THEN** every mode of that lane SHALL fail L1 with `missing_flags` containing `-m`

#### Scenario: A lane without a probe block keeps today's behaviour
- **WHEN** a lane's `cli` block has no `probe` key
- **THEN** L1 SHALL be decided by `<command> --version` alone, and L2 SHALL be `auth_unknown`

#### Scenario: Auth output is never captured
- **WHEN** a fake auth-status command prints `sk-test-SENTINEL-AUTH-42` and exits 0
- **THEN** L2 SHALL be `auth_ok`, and the sentinel SHALL NOT appear in the probe's return value, stdout, stderr, logs, or cache file

#### Scenario: Credential files are checked for existence only
- **WHEN** a lane declares `credential_files: ["~/.fake/auth.json"]` and that file exists with unreadable permissions (mode `0000`)
- **THEN** L2 SHALL be `auth_ok` without the file being opened

### Requirement: Per-Machine Probe Cache

Probe results SHALL be persisted to a per-user cache outside any repository, at
`$AGENTIC_PROBE_CACHE`, else `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`, else
`~/.cache/agentic-coding-tools/vendor-probe.json`, conforming to
`contracts/vendor-probe-cache.schema.json`. Each entry SHALL record the lane's resolved CLI
path, CLI version, a sha256 fingerprint of its `cli` block, and the probe time. An entry SHALL be
fresh only while its TTL (default 24 hours) has not elapsed and its CLI path and fingerprint match
the current environment. Writes SHALL be atomic and the file SHALL be created with mode `0600`.
A cache that cannot be parsed SHALL be treated as empty.

#### Scenario: Changing the CLI invalidates its entry
- **WHEN** a fresh entry exists for `codex-local` and the `codex` on `PATH` now resolves to a different realpath
- **THEN** the entry SHALL be treated as stale

#### Scenario: Changing the lane config invalidates its entry
- **WHEN** a fresh entry exists and the lane's `dispatch_modes` args are edited
- **THEN** the fingerprint SHALL differ and the entry SHALL be treated as stale

#### Scenario: A corrupt cache does not break dispatch
- **WHEN** the cache file contains `{not json`
- **THEN** reads SHALL return no entries, dispatch SHALL proceed unfiltered, and the next probe SHALL overwrite the file with a valid document

### Requirement: Cache-Filtered Reviewer Discovery

`discover_reviewers` SHALL exclude a lane for a mode when a fresh cache entry records, for that
lane, `cli_not_found`, `auth_failed`, a fresh runtime failure, or `missing_flags` for that mode.
Missing or stale entries SHALL NOT exclude a lane, and discovery SHALL NOT start probe
subprocesses. Each exclusion SHALL be logged with lane, mode, and reason.
`AGENTIC_PROBE_IGNORE_CACHE=1` SHALL disable the filter. When dispatch classifies a lane failure
as `auth_required` or `vendor_unavailable`, the dispatcher SHALL record a runtime failure for
that lane in the cache with a 1-hour TTL; a later probe with L2 `auth_ok` SHALL clear it.

#### Scenario: A remembered auth failure skips the lane in the next run
- **WHEN** run 1 dispatches `grok-local`, which fails with error class `auth_required`, and run 2 starts within one hour
- **THEN** run 2's `discover_reviewers` SHALL omit `grok-local` and log reason `runtime_auth_required`

#### Scenario: Missing cache never narrows the roster
- **WHEN** no cache file exists
- **THEN** `discover_reviewers` SHALL return the same reviewers it returns without this change

#### Scenario: Ignore switch restores the full roster
- **WHEN** a fresh entry marks `codex-local` `auth_failed` and `AGENTIC_PROBE_IGNORE_CACHE=1` is set
- **THEN** `codex-local` SHALL be eligible for discovery

### Requirement: Check-Vendors Uses the Tiered Probe

`review_dispatcher.py --check-vendors` SHALL decide each lane/mode's verified status with the
tiered probe and SHALL write the results to the probe cache. A lane/mode SHALL be verified only
when L0 and L1 pass and L2 is not `auth_failed`. The existing `--json` keys, the unverified
reasons `cli_not_found` and `probe_timeout`, and exit codes 0/2 SHALL keep their meaning;
unverified entries MAY carry the new reasons `missing_flags` and `auth_failed`, and verified
entries MAY carry an additive `probe` object with tier details.

#### Scenario: Check-vendors rejects a lane whose login has expired
- **WHEN** a lane's CLI is installed, its flags are all present, and its auth-status command exits 1
- **THEN** `--check-vendors --json` SHALL list it under `unverified` with reason `auth_failed` and SHALL NOT count it toward `--min-vendors`
