# Spec: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## 1. Adversarial Review Mode

### 1.1 Adversarial Prompt Prefix

The system SHALL define an adversarial prompt prefix that wraps a standard review prompt with contrarian framing. The prefix SHALL instruct the reviewer to:
- Challenge design decisions and question whether the chosen approach is optimal
- Identify edge cases, failure modes, and scalability concerns
- Question assumptions that the standard review would take at face value
- Suggest alternative approaches that might be superior

### 1.2 No New Dispatch Mode Required

Adversarial review SHALL reuse the existing `review` dispatch mode. The adversarial framing is applied at the prompt level, not the dispatch level. No changes to `agents.yaml` CLI configs are required.

### 1.3 Findings Schema Compliance

Adversarial review findings SHALL conform to the existing `review-findings.schema.json` without modifications. Finding types SHALL use existing enum values (`architecture`, `correctness`, `performance`, `security`).

### 1.4 Consensus Equal Weight

Adversarial findings SHALL have equal weight in the consensus synthesis pipeline. A finding from an adversarial review is confirmed only when matched by another vendor (adversarial or standard) with `match_score >= 0.6`.

### 1.5 Review Skill Integration

Both `parallel-review-plan` and `parallel-review-implementation` skills SHALL accept an `--adversarial` flag. When set, the skill SHALL prepend the adversarial prompt prefix to the review prompt before calling `review_dispatcher.py` with `--mode review` (unchanged).

## 2. Micro-Task Quick Dispatch

### 2.1 Skill Definition

The system SHALL provide a `/quick-task` skill that accepts a freeform text prompt and dispatches it to a vendor for execution.

### 2.2 No OpenSpec Artifacts

`/quick-task` SHALL NOT create any OpenSpec artifacts (no change-id, proposal, specs, tasks, or work packages). It SHALL NOT create or use worktrees.

### 2.3 Vendor Selection

`/quick-task` SHALL accept an optional `--vendor <name>` flag. When specified, it SHALL dispatch only to the named vendor. When omitted, it SHALL use the first available vendor from `ReviewOrchestrator.discover_reviewers(dispatch_mode="quick")`.

### 2.4 Dispatch Mode

`/quick-task` SHALL use a `quick` dispatch mode defined in `agents.yaml`. This mode SHALL use read-write CLI args appropriate for ad-hoc tasks (not worktree-scoped).

### 2.5 Output Format

`/quick-task` SHALL return the vendor's raw stdout to the user without parsing into structured findings. If the vendor returns non-zero exit code, the skill SHALL display the error and stderr.

### 2.6 Complexity Warning

If the user's prompt exceeds 500 words OR references more than 5 files, `/quick-task` SHALL emit a warning suggesting the user consider `/plan-feature` for larger tasks. The warning SHALL NOT block execution.

### 2.7 Timeout

`/quick-task` SHALL have a default timeout of 300 seconds (5 minutes), configurable via `--timeout <seconds>`.

## 3. Vendor Health Check

### 3.1 CLI Script

The system SHALL provide `vendor_health.py` as a standalone script that checks all configured vendors' readiness.

### 3.2 Health Check Dimensions

For each vendor in `agents.yaml`, the health check SHALL verify:
- **CLI availability**: `shutil.which(command)` returns a path
- **API key resolution**: `ApiKeyResolver` can resolve a key (OpenBao or env var)
- **Dispatch modes**: Which modes have `can_dispatch()` returning true
- **Model access**: Lightweight endpoint probe (vendor-specific) confirms model availability

### 3.3 Output Format

The CLI script SHALL support `--json` flag for machine-readable output and default to a human-readable table:

```
Vendor        CLI    API Key   Modes                    Models
claude-local  ✓      ✓         review, adversarial      claude-sonnet-4-6
codex-local   ✓      ✓         review, quick            gpt-5.4
gemini-local  ✗      ✓         -                        -
```

### 3.4 Skill Wrapper

A `/vendor:status` skill SHALL invoke `vendor_health.py` and present results to the user.

### 3.5 Watchdog Integration

`WatchdogService` SHALL include a `_check_vendor_health()` method that:
- Calls `check_all_vendors()` from `vendor_health.py`
- Compares current state against previous check
- Emits `vendor.unavailable` event (urgency: medium) when a previously-available vendor becomes unavailable
- Emits `vendor.recovered` event (urgency: low) when a previously-unavailable vendor becomes available
- Does NOT emit events on first run (no baseline to compare against)

### 3.6 Event Channel

Vendor health events SHALL emit on the `coordinator_agent` channel with event types `vendor.unavailable` and `vendor.recovered`.

### 3.7 Probe Cost

Health probes SHALL NOT send inference requests. They SHALL use lightweight endpoints (model listing or authentication verification) to minimize API cost.

### 3.8 Configurable Interval

The watchdog vendor health check interval SHALL be independently configurable via `VENDOR_HEALTH_INTERVAL_SECONDS` environment variable (default: 300 seconds / 5 minutes), separate from the main watchdog interval.
