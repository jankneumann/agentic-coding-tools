# Spec: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## ADDED Requirements

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
- **CLI availability**: `shutil.which(command)` returns a path
- **API key resolution**: `ApiKeyResolver` can resolve a key (OpenBao or env var)
- **Dispatch modes**: Which modes have `can_dispatch()` returning true
- **Model access**: Lightweight endpoint probe (vendor-specific) confirms model availability

#### Scenario: Health check verifies all dimensions

Given a vendor with CLI installed and API key configured
When the health check runs
Then all four dimensions (CLI, API key, modes, model) are reported

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
