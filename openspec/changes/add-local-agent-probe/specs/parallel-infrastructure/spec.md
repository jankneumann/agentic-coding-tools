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
`dispatch_modes.<mode>.args` (tokens starting with `-`; `--flag=value` counted as `--flag`;
values and placeholder tokens such as `@review-findings-schema` skipped) and from the `cli`
`*_flag` keys of the same normalized projection the fingerprint uses (`model_flag` defaulting to
`-m`; `null` keys dropped), minus `probe.ignore_flags`; the help command for a mode SHALL be
`probe.help_args[<mode>]` when that mode is listed and `[command, <leading non-flag args>,
"--help"]` otherwise (a partial `help_args` map overrides only the modes it lists). Every declared probe argv
(`version_args`, `help_args` values, `auth_status_args`) SHALL be executed as arguments after
`cli.command` — `[command, *argv]` — never as a bare argv. Every probe subprocess SHALL run with `stdin` bound to
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

#### Scenario: Value and placeholder tokens are not required flags
- **WHEN** a lane's `review` mode passes `["-p", "--output-format=json", "--json-schema", "@review-findings-schema"]`
- **THEN** the required flags for `review` SHALL be exactly `-p`, `--output-format`, `--json-schema`, plus the lane's injected `*_flag` values

#### Scenario: An undeclared model flag is still required
- **WHEN** a lane loaded from a raw `agents.yaml` omits `model_flag` and its help output lacks `-m`
- **THEN** every mode SHALL fail L1 with `missing_flags` containing `-m`, as it does when `model_flag: "-m"` is declared

#### Scenario: Ignored flags are not required
- **WHEN** a lane's `review` mode passes `--json-schema`, help output lacks it, and the lane declares `probe: {ignore_flags: ["--json-schema"]}`
- **THEN** `review` SHALL pass L1

#### Scenario: A partial help override leaves other modes on generated help
- **WHEN** a lane declares `probe: {help_args: {review: ["exec", "--help"]}}` and its `alternative` mode passes `["-p"]`
- **THEN** the probe SHALL check `review` against `[command, "exec", "--help"]` and `alternative` against `[command, "--help"]`

#### Scenario: Version output is truncated before it is stored
- **WHEN** a fake version command prints a 500-character first line followed by more lines
- **THEN** the stored `cli_version` SHALL be the first 200 characters of the first line only

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

#### Scenario: An auth command that cannot be launched is unknown
- **WHEN** a lane declares `auth_status_args` and launching the command raises `FileNotFoundError`
- **THEN** L2 SHALL be `auth_unknown` and the lane SHALL NOT be excluded on that basis

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
cannot be parsed SHALL be treated as empty. A failure to write the cache (any `OSError`) SHALL be
logged at WARNING and SHALL NOT fail the caller: `probe_lanes()` SHALL still return the results it
computed, so `vendor_health`, the watchdog, `--check-vendors`, and `report` work on a read-only or
absent cache directory.

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

#### Scenario: A defaulted version argv fingerprints like an absent one
- **WHEN** one source carries `probe: {auth_status_args: ["auth", "status"]}` and another carries the same block plus `version_args: ["--version"]`
- **THEN** both SHALL produce the same `config_fingerprint`

#### Scenario: Editing a model list does not invalidate capability results
- **WHEN** a fresh entry exists and only the lane's `model_fallbacks` are edited
- **THEN** the fingerprint SHALL be unchanged and the entry SHALL remain fresh

#### Scenario: Concurrent writers do not lose updates
- **WHEN** two threads record runtime failures for `grok-local` and `pi-local` at the same time against the same cache file
- **THEN** after both complete the cache SHALL contain both runtime failures and SHALL validate against the schema

#### Scenario: An expired entry is stale
- **WHEN** an entry's `probed_at` is older than its `ttl_seconds`
- **THEN** the entry SHALL be treated as stale and SHALL NOT exclude the lane

#### Scenario: An unwritable cache does not fail a probe
- **WHEN** `probe_lanes()` runs and the cache directory is read-only
- **THEN** it SHALL log a warning and return the computed results

#### Scenario: A corrupt cache does not break dispatch
- **WHEN** the cache file contains `{not json`
- **THEN** reads SHALL return no entries, dispatch SHALL proceed unfiltered, and the next probe SHALL overwrite the file with a valid document

### Requirement: Cache-Filtered Reviewer Discovery

`discover_reviewers` SHALL exclude a lane for a mode when a fresh cache entry records, for that
lane, `cli_not_found`, `auth_failed`, a fresh runtime failure, or `missing_flags` or
`probe_failed` for that mode. `probe_timeout` SHALL NOT exclude a lane. Missing or stale entries
SHALL NOT exclude a lane, and discovery SHALL NOT start probe
subprocesses. Each exclusion SHALL be logged with lane, mode, and reason, and SHALL be recorded in
the review dispatch manifest as an `excluded_lanes` entry `{vendor, mode, reason, since}` (where
`since` is the entry's `probed_at` or the runtime failure's `observed_at`), so a narrowed round is
visible in the artefact operators read.
`AGENTIC_PROBE_IGNORE_CACHE=1` SHALL disable the filter. When dispatch classifies a lane failure
as `auth_required` or `vendor_unavailable` from the stderr of a non-zero-exit invocation, the
dispatcher SHALL record a runtime failure for
that lane in the cache with a 1-hour TTL, whether or not a probe entry exists for it; a failure to
write SHALL be logged and SHALL NOT alter the dispatch result. A later probe with L2 `auth_ok`
with method `status_command`, whose auth subprocess started after the failure's `observed_at`,
SHALL clear an `auth_required` failure (an `auth_ok` from
`credential_files` SHALL NOT); a `vendor_unavailable` (billing/credits) failure SHALL clear only
when its TTL expires.

#### Scenario: A remembered auth failure skips the lane in the next run
- **WHEN** run 1 dispatches `grok-local`, which fails with error class `auth_required`, and run 2 starts within one hour
- **THEN** run 2's `discover_reviewers` SHALL omit `grok-local` and log reason `runtime_auth_required`

#### Scenario: A probe that started before the failure does not clear it
- **WHEN** a re-probe's auth-status command for `codex-local` starts at T, a dispatch records `auth_required` at T+1 s, and the auth command exits 0 at T+2 s
- **THEN** the runtime failure SHALL remain

#### Scenario: A remembered auth failure expires
- **WHEN** a lane's `auth_required` runtime failure is older than its 1-hour TTL
- **THEN** `discover_reviewers` SHALL include the lane

#### Scenario: A passing status command clears a remembered auth failure
- **WHEN** `codex-local` (L2 via `auth_status_args`) has a fresh `auth_required` runtime failure and a re-probe's auth-status command exits 0
- **THEN** the runtime failure SHALL be removed and `discover_reviewers` SHALL include `codex-local`

#### Scenario: Cache-driven exclusions appear in the dispatch manifest
- **WHEN** `discover_reviewers` omits `grok-local` for reason `runtime_auth_required`
- **THEN** the round's review manifest SHALL contain an `excluded_lanes` entry naming `grok-local`, the mode, the reason, and the failure's `observed_at`

#### Scenario: A known-broken CLI is not dispatched
- **WHEN** a fresh entry records L1 `probe_failed` for `codex-local`'s `review` mode
- **THEN** `discover_reviewers` SHALL omit `codex-local` for `review` and log reason `probe_failed`

#### Scenario: Credential-file evidence does not clear a runtime auth failure
- **WHEN** `grok-local` (L2 via `credential_files`) has a fresh `auth_required` runtime failure and a re-probe reports L2 `auth_ok` because the file exists
- **THEN** the runtime failure SHALL remain until its TTL expires

#### Scenario: A billing failure is not cleared by a passing auth probe
- **WHEN** `pi-local` has a fresh `vendor_unavailable` runtime failure and a re-probe reports L2 `auth_ok`
- **THEN** the runtime failure SHALL remain and `discover_reviewers` SHALL still omit `pi-local` with reason `runtime_vendor_unavailable` until the TTL expires

#### Scenario: A zero-exit review that mentions 402 is not remembered as unavailable
- **WHEN** `codex-local` exits 0 with unparseable stdout containing `HTTP 402 Payment Required` as review prose, and the per-run result is classified `vendor_unavailable`
- **THEN** no runtime failure SHALL be recorded for `codex-local`, and the next run's `discover_reviewers` SHALL include it

#### Scenario: An unwritable cache does not fail the review
- **WHEN** a lane fails with `auth_required` and the cache directory is read-only
- **THEN** the dispatcher SHALL log a warning and return the same `ReviewResult` it returns without this change

#### Scenario: Missing cache never narrows the roster
- **WHEN** no cache file exists
- **THEN** `discover_reviewers` SHALL return the same reviewers it returns without this change

#### Scenario: Ignore switch restores the full roster
- **WHEN** a fresh entry marks `codex-local` `auth_failed` and `AGENTIC_PROBE_IGNORE_CACHE=1` is set
- **THEN** `codex-local` SHALL be eligible for discovery

## MODIFIED Requirements

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after that mode is verified. For a CLI lane, verification SHALL use the tiered probe (`vendor_probe.py`, requirement *Tiered Local Vendor Probe*) with `reuse_fresh=False`, and SHALL write its results to the probe cache: a CLI lane/mode is verified only when L0 and L1 pass, L2 is not `auth_failed`, and the lane has no fresh runtime failure after the probe's clearing rules are applied — the same predicate `discover_reviewers` uses, so the INIT quorum count equals the lanes dispatch will use. For an SDK or API lane, verification SHALL remain the adapter's own authenticated no-op (such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` — `probe_command` naming the version argv — and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2. Unverified entries MAY carry the reasons `missing_flags`, `probe_failed`, `auth_failed`, `runtime_auth_required`, and `runtime_vendor_unavailable` in addition to `cli_not_found` and `probe_timeout`; verified entries MAY carry an additive `probe` object with tier details.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's version command does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned

#### Scenario: Check-vendors rejects a lane whose login has expired
- **WHEN** a lane's CLI is installed, its flags are all present, and its auth-status command exits 1
- **THEN** `--check-vendors --json` SHALL list it under `unverified` with reason `auth_failed` and SHALL NOT count it toward `--min-vendors`

#### Scenario: Check-vendors does not count a lane dispatch will skip
- **WHEN** a lane passes L0–L2 but has a fresh `vendor_unavailable` runtime failure
- **THEN** `--check-vendors --json` SHALL list it under `unverified` with reason `runtime_vendor_unavailable` and SHALL NOT count it toward `--min-vendors`

#### Scenario: Existing JSON keys and exit codes are preserved
- **WHEN** `--check-vendors --json --min-vendors 2` runs with one verified lane
- **THEN** the output SHALL contain `modes` and `probe_command` with their existing shapes and the process SHALL exit 2
