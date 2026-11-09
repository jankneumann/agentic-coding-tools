# vendor-ux Specification

## Purpose
TBD - created by archiving change vendor-ux-enhancements. Update Purpose after archive.
## Requirements
### Requirement: Adversarial Prompt Prefix

The system SHALL define an adversarial prompt prefix that wraps a standard review prompt with contrarian framing. The prefix SHALL instruct the reviewer to:
- Challenge design decisions and question whether the chosen approach is optimal
- Identify edge cases, failure modes, and scalability concerns
- Question assumptions that the standard review would take at face value
- Suggest alternative approaches that might be superior

#### Scenario: Adversarial prompt wraps standard review

Given a standard review prompt for a plan
When the `--adversarial` flag is set
Then the adversarial prefix is prepended to the prompt before dispatch

### Requirement: No New Dispatch Mode Required

Adversarial review SHALL reuse the existing `review` dispatch mode. The adversarial framing is applied at the prompt level, not the dispatch level. No changes to `agents.yaml` CLI configs are required.

#### Scenario: Adversarial uses review dispatch mode

Given an adversarial review is triggered
When the review is dispatched to a vendor
Then the dispatch mode is `review` (not a new mode)

### Requirement: Findings Schema Compliance

Adversarial review findings SHALL conform to the existing `review-findings.schema.json` without modifications. Finding types SHALL use existing enum values (`architecture`, `correctness`, `performance`, `security`).

#### Scenario: Adversarial findings match schema

Given an adversarial review produces findings
When the findings are parsed
Then they conform to `review-findings.schema.json` without schema errors

### Requirement: Consensus Equal Weight

Adversarial findings SHALL have equal weight in the consensus synthesis pipeline. A finding from an adversarial review is confirmed only when matched by another vendor (adversarial or standard) with `match_score >= 0.6`.

#### Scenario: Adversarial finding enters consensus

Given an adversarial review finding and a standard review finding
When consensus synthesis runs
Then the adversarial finding is confirmed if match_score >= 0.6

### Requirement: Review Skill Integration

Both `parallel-review-plan` and `parallel-review-implementation` skills SHALL accept an `--adversarial` flag. When set, the skill SHALL prepend the adversarial prompt prefix to the review prompt before calling `review_dispatcher.py` with `--mode review` (unchanged).

#### Scenario: Review skill accepts adversarial flag

Given the `parallel-review-plan` skill is invoked with `--adversarial`
When the review prompt is constructed
Then the adversarial prefix is prepended before dispatch

### Requirement: Quick Task Skill Definition

The system SHALL provide a `/quick-task` skill that accepts a freeform text prompt and dispatches it to a vendor for execution.

#### Scenario: Quick task dispatches prompt

Given the user invokes `/quick-task "fix the typo in README"`
When the skill runs
Then the prompt is dispatched to a vendor and the result is returned

### Requirement: No OpenSpec Artifacts

`/quick-task` SHALL NOT create any OpenSpec artifacts (no change-id, proposal, specs, tasks, or work packages). It SHALL NOT create or use worktrees.

#### Scenario: Quick task creates no artifacts

Given a quick task is executed
When the task completes
Then no files are created under `openspec/changes/` or `.git-worktrees/`

### Requirement: Vendor Selection

`/quick-task` SHALL accept an optional `--vendor <name>` flag. When specified, it SHALL dispatch only to the named vendor. When omitted, it SHALL use the first available vendor from `ReviewOrchestrator.discover_reviewers(dispatch_mode="quick")`.

#### Scenario: Quick task with explicit vendor

Given the user invokes `/quick-task --vendor codex-local "list files"`
When the task is dispatched
Then only the `codex-local` vendor is used

### Requirement: Dispatch Mode

`/quick-task` SHALL use a `quick` dispatch mode defined in `agents.yaml`. This mode SHALL use read-write CLI args appropriate for ad-hoc tasks (not worktree-scoped).

#### Scenario: Quick dispatch mode in agents.yaml

Given `agents.yaml` is loaded
When the `quick` dispatch mode is looked up
Then it contains read-write CLI args for ad-hoc tasks

### Requirement: Output Format

`/quick-task` SHALL return the vendor's raw stdout to the user without parsing into structured findings. If the vendor returns non-zero exit code, the skill SHALL display the error and stderr.

#### Scenario: Quick task returns raw output

Given a vendor returns stdout with results
When the quick task completes
Then the raw stdout is displayed to the user without structured parsing

### Requirement: Complexity Warning

If the user's prompt exceeds 500 words OR references more than 5 files, `/quick-task` SHALL emit a warning suggesting the user consider `/plan-feature` for larger tasks. The warning SHALL NOT block execution.

#### Scenario: Complex prompt triggers warning

Given a prompt with 600 words
When the quick task is invoked
Then a warning is emitted suggesting `/plan-feature`
And the task still executes

### Requirement: Timeout

`/quick-task` SHALL have a default timeout of 300 seconds (5 minutes), configurable via `--timeout <seconds>`.

#### Scenario: Quick task times out

Given a quick task with `--timeout 10`
When the vendor does not respond within 10 seconds
Then the task is terminated with a timeout error

### Requirement: CLI Script

The system SHALL provide `vendor_health.py` as a standalone script that checks all configured vendors' readiness.

#### Scenario: Health check runs standalone

Given `vendor_health.py` is invoked
When it runs
Then it checks all vendors in `agents.yaml` and reports their status

### Requirement: Health Check Dimensions

For each vendor in `agents.yaml`, the health check SHALL verify:
- **CLI availability, capability, and auth**: from the shared tiered probe (`vendor_probe.py`) — L0 presence, per-mode L1 capability, and L2 auth (requirement *Health Check Delegates to the Tiered Probe*)
- **API key resolution**: `ApiKeyResolver` can resolve a key (OpenBao or env var)
- **Dispatch modes**: Which modes have `can_dispatch()` returning true and pass L1
- **Model access**: Lightweight endpoint probe (vendor-specific) confirms model availability

#### Scenario: Health check verifies all dimensions

Given a vendor with CLI installed and API key configured
When the health check runs
Then all four dimensions (CLI availability/capability/auth, API key, modes, model) are reported

### Requirement: Health Output Format

The CLI script SHALL support `--json` flag for machine-readable output and default to a human-readable table.

#### Scenario: Health check JSON output

Given `vendor_health.py --json` is invoked
When the check completes
Then the output is valid JSON with vendor status entries

### Requirement: Skill Wrapper

A `/vendor:status` skill SHALL invoke `vendor_health.py` and present results to the user.

#### Scenario: Vendor status skill runs

Given the user invokes `/vendor:status`
When the skill runs
Then it displays the vendor health table

### Requirement: Watchdog Integration

`WatchdogService` SHALL include a `_check_vendor_health()` method that:
- Calls `check_all_vendors()` from `vendor_health.py`
- Compares current state against previous check
- Emits `vendor.unavailable` event (urgency: medium) when a previously-available vendor becomes unavailable
- Emits `vendor.recovered` event (urgency: low) when a previously-unavailable vendor becomes available
- Does NOT emit events on first run (no baseline to compare against)

#### Scenario: Watchdog detects vendor going unavailable

Given a vendor was available on the previous check
When the vendor becomes unavailable on the current check
Then a `vendor.unavailable` event is emitted with urgency medium

### Requirement: Event Channel

Vendor health events SHALL emit on the `coordinator_agent` channel with event types `vendor.unavailable` and `vendor.recovered`.

#### Scenario: Vendor event uses correct channel

Given a vendor health state change occurs
When the event is emitted
Then it uses the `coordinator_agent` channel

### Requirement: Probe Cost

Health probes SHALL NOT send inference requests. They SHALL use lightweight endpoints (model listing or authentication verification) to minimize API cost.

#### Scenario: Health probe avoids inference

Given a vendor health check runs
When it probes model access
Then no inference request is sent (only model listing or auth verification)

### Requirement: Configurable Interval

The watchdog vendor health check interval SHALL be independently configurable via `VENDOR_HEALTH_INTERVAL_SECONDS` environment variable (default: 300 seconds / 5 minutes), separate from the main watchdog interval.

#### Scenario: Custom vendor health interval

Given `VENDOR_HEALTH_INTERVAL_SECONDS=60` is set
When the watchdog starts
Then vendor health checks run every 60 seconds

### Requirement: Health Check Delegates to the Tiered Probe

`vendor_health.py` SHALL obtain CLI availability, per-mode capability, and auth status from the
shared tiered probe (`vendor_probe.py`) instead of its own `shutil.which` check, so that
`/vendor-status` and `review_dispatcher.py --check-vendors` report the same verdict for the same
lane. Its existing `--json` fields (`cli_installed`, `api_key_available`, `dispatch_modes`,
`models`, `healthy`, `error`) SHALL keep their meaning, except that `dispatch_modes` narrows from
"configured modes when the CLI is installed" to "modes that pass L1" — for a lane without a
`probe` block this equals today's list whenever `--version` succeeds. It SHALL add `cli_version`, `missing_flags` (per mode), and `auth_status`
(`auth_ok`, `auth_failed`, `auth_unknown`, `probe_timeout`) and `runtime_failure`
(`runtime_auth_required`, `runtime_vendor_unavailable`, or `null`, from a fresh
`runtime_failures` record after the probe's clearing rules). A lane SHALL NOT be `healthy` when
`auth_status` is `auth_failed` or `runtime_failure` is non-null — the same predicate
`--check-vendors` and `discover_reviewers` use. The probe SHALL remain loadable from the coordinator container
by file path alongside `vendor_health.py`, using only the standard library. The `vendor_health`
CLI SHALL re-probe; the programmatic `check_all_vendors()` used by the coordinator watchdog SHALL
evaluate L0 live and reuse L1/L2 cache entries younger than one hour without starting
subprocesses (re-probing older ones), and the watchdog SHALL run it off the
event loop (`asyncio.to_thread`).

#### Scenario: vendor-status and check-vendors agree
- **WHEN** a lane's CLI is installed but lacks a flag its `review` mode uses
- **THEN** `vendor_health --json` SHALL omit `review` from that lane's `dispatch_modes` and report it in `missing_flags`, and `--check-vendors --json` SHALL list the lane as `unverified` for `review` with reason `missing_flags`

#### Scenario: An expired login makes a lane unhealthy
- **WHEN** a lane's CLI and flags pass and its auth-status command exits 1
- **THEN** `vendor_health --json` SHALL report `auth_status: "auth_failed"` and `healthy: false` for that lane

#### Scenario: A remembered billing failure makes a lane unhealthy in both entry points
- **WHEN** a lane passes L0–L2 and has a fresh `vendor_unavailable` runtime failure
- **THEN** `vendor_health --json` SHALL report `runtime_failure: "runtime_vendor_unavailable"` and `healthy: false`, and `--check-vendors --json` SHALL list the lane `unverified` with the same reason

#### Scenario: The health CLI re-probes
- **WHEN** a fresh cache entry exists and `vendor_health.py` is run from the command line against fake CLIs that record their argv
- **THEN** the fake CLIs SHALL record a version invocation

#### Scenario: The watchdog probe runs off the event loop
- **WHEN** the watchdog's vendor-health check runs
- **THEN** `check_all_vendors()` SHALL be invoked through `asyncio.to_thread`

#### Scenario: The watchdog loader still works
- **WHEN** `agent-coordinator/src/watchdog.py` loads `vendor_health.py` by path from a directory that also contains `vendor_probe.py` and has no PyYAML installed
- **THEN** `check_all_vendors` SHALL run without an import error

#### Scenario: The watchdog reuses fresh probe results
- **WHEN** `check_all_vendors()` is called twice within the probe TTL against fake CLIs that record their argv
- **THEN** the second call SHALL start no subprocesses and SHALL return the same verdicts

#### Scenario: Health probes stay token-free
- **WHEN** the health check runs against fake CLIs that record every argv they receive
- **THEN** no recorded argv SHALL equal or contain a dispatch-mode `args` vector

