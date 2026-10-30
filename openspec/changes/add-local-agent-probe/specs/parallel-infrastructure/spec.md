## ADDED Requirements

### Requirement: Tiered Local Vendor Probe

The parallel-infrastructure skill SHALL provide one probe implementation,
`vendor_probe.py`, that evaluates each configured CLI lane on the local machine in three
token-free tiers: **L0 presence** (`shutil.which(command)`), **L1 capability** (the lane's
version command succeeds and every flag the lane's dispatch mode passes appears as a whole
token in that mode's help output), and **L2 auth**. L2 SHALL use exactly one method: when
`auth_status_args` is declared, `auth_ok` on exit 0 and `auth_failed` on non-zero exit
(`credential_files` ignored); otherwise, when `credential_files` is declared, `auth_ok` when every
listed path exists and `auth_failed` when any is missing; otherwise `auth_unknown`. A status
command that cannot be launched SHALL yield `auth_unknown`. Only the first line of version output,
truncated to 200 characters, SHALL be retained. Required flags SHALL be derived from the mode's
`dispatch_modes.<mode>.args` and from `cli` keys whose name ends in `_flag`, minus
`probe.ignore_flags`; the help command SHALL be `[command, <leading non-flag args>, "--help"]`
unless `probe.help_args` is declared. Every probe subprocess SHALL run with `stdin` bound to
`DEVNULL` and a timeout of `min(10 s, remaining lane budget)`; a lane's subprocesses SHALL share a
25-second per-lane deadline (a subprocess with no budget left is not run and its tier is
`probe_timeout`); modes sharing a help argv SHALL run it once; and the probe SHALL NOT execute any dispatch-mode argument vector (so no model
request is ever sent). A non-zero exit or timeout of the version command SHALL fail L1 for every
mode of the lane with reason `probe_failed` or `probe_timeout`; a non-zero exit or timeout of a
help command SHALL fail L1 for the modes using it with the same reasons.

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

#### Scenario: A failing version command fails every mode
- **WHEN** the lane's version command exits 1
- **THEN** every mode SHALL fail L1 with reason `probe_failed`, and no help command SHALL be run

#### Scenario: Modes sharing a help command run it once
- **WHEN** a lane's `review` and `alternative` modes both resolve to the help argv `[command, "--help"]`
- **THEN** the fake CLI SHALL record exactly one `--help` invocation, and both modes SHALL be evaluated against its output

#### Scenario: The per-lane deadline bounds a slow lane
- **WHEN** every subprocess of a lane's fake CLI sleeps for 9 seconds and the lane has a version command, two distinct help commands, and an auth-status command
- **THEN** the lane's probe SHALL finish within 26 seconds, and every tier whose subprocess was cut short or not started SHALL be recorded `probe_timeout`

#### Scenario: A status command takes precedence over credential files
- **WHEN** a lane declares both `auth_status_args` (fake command exits 1) and `credential_files` (all exist)
- **THEN** L2 SHALL be `auth_failed` with method `status_command`

#### Scenario: A missing credential file fails auth
- **WHEN** a lane declares only `credential_files: ["~/.fake/auth.json"]` and the file does not exist
- **THEN** L2 SHALL be `auth_failed` with method `credential_files`

#### Scenario: A hanging auth command times out without failing auth
- **WHEN** the lane's auth-status command does not exit within 10 seconds
- **THEN** L2 SHALL be `probe_timeout`, the subprocess SHALL be killed, and the lane SHALL NOT be excluded from discovery on that basis

#### Scenario: Auth output is never captured
- **WHEN** a fake auth-status command prints `sk-test-SENTINEL-AUTH-42` and exits 0
- **THEN** L2 SHALL be `auth_ok`, and the sentinel SHALL NOT appear in the probe's return value, stdout, stderr, logs, or cache file

#### Scenario: Credential files are checked for existence only
- **WHEN** a lane declares `credential_files: ["~/.fake/auth.json"]` and that file exists with unreadable permissions (mode `0000`)
- **THEN** L2 SHALL be `auth_ok` without the file being opened

### Requirement: Per-Machine Probe Cache

Probe results SHALL be persisted to a per-user cache outside any repository, at
`$AGENTIC_PROBE_CACHE`, else `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`, else
`~/.cache/agentic-coding-tools/vendor-probe.json` (first match wins), conforming to
`contracts/vendor-probe-cache.schema.json`. Each entry SHALL record the lane's resolved CLI
path, CLI version, a sha256 fingerprint, and the probe time. The fingerprint SHALL be computed
over a normalized projection of the `cli` block — `command`, each mode's `args`, every `*_flag`
key (with `model_flag` defaulting to `-m`, and any other `*_flag` key whose value is `null`
treated as absent), and `probe` (absent treated as `null`, distinct from a declared `{}`) — so that the
same lane fingerprints identically whether it was loaded from a local `agents.yaml`,
`AGENTS_YAML`, or `/agents/dispatch-configs`. An entry SHALL be fresh only while its TTL
(default 24 hours) has not elapsed and its CLI path and fingerprint match the current
environment. Runtime failures SHALL be stored in a separate `runtime_failures` map keyed by lane,
recordable without a probe entry and unaffected by fingerprint changes. Every write SHALL be a
read-modify-write under an in-process lock and, where `fcntl` is available, an exclusive file
lock, followed by an atomic replace; the file SHALL be created with mode `0600`. A cache that
cannot be parsed SHALL be treated as empty.

#### Scenario: Cache path precedence
- **WHEN** `AGENTIC_PROBE_CACHE` and `XDG_CACHE_HOME` are both set
- **THEN** the cache SHALL be read from and written to `$AGENTIC_PROBE_CACHE`; with only `XDG_CACHE_HOME` set it SHALL be `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`; with neither, `~/.cache/agentic-coding-tools/vendor-probe.json`

#### Scenario: The cache file is private
- **WHEN** the probe writes the cache file for the first time
- **THEN** the file SHALL have mode `0600`

#### Scenario: Declaring an empty probe block invalidates a version-only entry
- **WHEN** a fresh entry exists for a lane with no `probe` key and the lane is edited to declare `probe: {}`
- **THEN** the fingerprint SHALL differ and the entry SHALL be treated as stale

#### Scenario: Changing the CLI invalidates its entry
- **WHEN** a fresh entry exists for `codex-local` and the `codex` on `PATH` now resolves to a different realpath
- **THEN** the entry SHALL be treated as stale

#### Scenario: Changing the lane config invalidates its entry
- **WHEN** a fresh entry exists and the lane's `dispatch_modes` args are edited
- **THEN** the fingerprint SHALL differ and the entry SHALL be treated as stale

#### Scenario: The same lane fingerprints identically across config sources
- **WHEN** `codex-local` is loaded once from a local `agents.yaml` that omits `model_flag` and once from a `/agents/dispatch-configs` payload that serializes `model_flag: "-m"` and `prompt_via_stdin: false`
- **THEN** both SHALL produce the same `config_fingerprint`

#### Scenario: Editing a model list does not invalidate capability results
- **WHEN** a fresh entry exists and only the lane's `model_fallbacks` are edited
- **THEN** the fingerprint SHALL be unchanged and the entry SHALL remain fresh

#### Scenario: Concurrent writers do not lose updates
- **WHEN** two threads record runtime failures for `grok-local` and `pi-local` at the same time against the same cache file
- **THEN** after both complete the cache SHALL contain both runtime failures and SHALL validate against the schema

#### Scenario: A corrupt cache does not break dispatch
- **WHEN** the cache file contains `{not json`
- **THEN** reads SHALL return no entries, dispatch SHALL proceed unfiltered, and the next probe SHALL overwrite the file with a valid document

### Requirement: Cache-Filtered Reviewer Discovery

`discover_reviewers` SHALL exclude a lane for a mode when a fresh cache entry records, for that
lane, `cli_not_found`, `auth_failed`, a fresh runtime failure, or `missing_flags` or
`probe_failed` for that mode. `probe_timeout` SHALL NOT exclude a lane. Missing or stale entries
SHALL NOT exclude a lane, and discovery SHALL NOT start probe
subprocesses. Each exclusion SHALL be logged with lane, mode, and reason.
`AGENTIC_PROBE_IGNORE_CACHE=1` SHALL disable the filter. When dispatch classifies a lane failure
as `auth_required` or `vendor_unavailable`, the dispatcher SHALL record a runtime failure for
that lane in the cache with a 1-hour TTL, whether or not a probe entry exists for it; a failure to
write SHALL be logged and SHALL NOT alter the dispatch result. A later probe with L2 `auth_ok`
with method `status_command` SHALL clear an `auth_required` failure (an `auth_ok` from
`credential_files` SHALL NOT); a `vendor_unavailable` (billing/credits) failure SHALL clear only
when its TTL expires.

#### Scenario: A remembered auth failure skips the lane in the next run
- **WHEN** run 1 dispatches `grok-local`, which fails with error class `auth_required`, and run 2 starts within one hour
- **THEN** run 2's `discover_reviewers` SHALL omit `grok-local` and log reason `runtime_auth_required`

#### Scenario: A known-broken CLI is not dispatched
- **WHEN** a fresh entry records L1 `probe_failed` for `codex-local`'s `review` mode
- **THEN** `discover_reviewers` SHALL omit `codex-local` for `review` and log reason `probe_failed`

#### Scenario: Credential-file evidence does not clear a runtime auth failure
- **WHEN** `grok-local` (L2 via `credential_files`) has a fresh `auth_required` runtime failure and a re-probe reports L2 `auth_ok` because the file exists
- **THEN** the runtime failure SHALL remain until its TTL expires

#### Scenario: A billing failure is not cleared by a passing auth probe
- **WHEN** `pi-local` has a fresh `vendor_unavailable` runtime failure and a re-probe reports L2 `auth_ok`
- **THEN** the runtime failure SHALL remain and `discover_reviewers` SHALL still omit `pi-local` with reason `runtime_vendor_unavailable` until the TTL expires

#### Scenario: An unwritable cache does not fail the review
- **WHEN** a lane fails with `auth_required` and the cache directory is read-only
- **THEN** the dispatcher SHALL log a warning and return the same `ReviewResult` it returns without this change

#### Scenario: Missing cache never narrows the roster
- **WHEN** no cache file exists
- **THEN** `discover_reviewers` SHALL return the same reviewers it returns without this change

#### Scenario: Ignore switch restores the full roster
- **WHEN** a fresh entry marks `codex-local` `auth_failed` and `AGENTIC_PROBE_IGNORE_CACHE=1` is set
- **THEN** `codex-local` SHALL be eligible for discovery

### Requirement: Check-Vendors Uses the Tiered Probe

`review_dispatcher.py --check-vendors` SHALL decide each lane/mode's verified status with the
tiered probe and SHALL write the results to the probe cache. A lane/mode SHALL be verified only
when L0 and L1 pass, L2 is not `auth_failed`, and the lane has no fresh runtime failure after the
probe's clearing rules are applied — the same predicate `discover_reviewers` uses, so the INIT
quorum count equals the lanes dispatch will use. The existing `--json` keys, the unverified
reasons `cli_not_found` and `probe_timeout`, and exit codes 0/2 SHALL keep their meaning;
unverified entries MAY carry the new reasons `missing_flags`, `auth_failed`,
`runtime_auth_required`, and `runtime_vendor_unavailable`, and verified
entries MAY carry an additive `probe` object with tier details.

#### Scenario: Check-vendors rejects a lane whose login has expired
- **WHEN** a lane's CLI is installed, its flags are all present, and its auth-status command exits 1
- **THEN** `--check-vendors --json` SHALL list it under `unverified` with reason `auth_failed` and SHALL NOT count it toward `--min-vendors`

#### Scenario: Check-vendors does not count a lane dispatch will skip
- **WHEN** a lane passes L0–L2 but has a fresh `vendor_unavailable` runtime failure
- **THEN** `--check-vendors --json` SHALL list it under `unverified` with reason `runtime_vendor_unavailable` and SHALL NOT count it toward `--min-vendors`
