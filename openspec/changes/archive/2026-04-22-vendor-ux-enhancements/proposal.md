# Proposal: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`
**Status**: Draft
**Created**: 2026-04-01
**Inspired by**: [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) — a lightweight Claude Code plugin for Codex integration

## Why

Our multi-vendor review orchestration system is architecturally sophisticated — config-driven dispatch, consensus synthesis, convergence loops — but it lacks three UX patterns that the simpler `codex-plugin-cc` plugin gets right:

1. **No adversarial review mode**: Our reviews check for correctness, security, and spec compliance, but never deliberately challenge design decisions. The plugin's `/codex:adversarial-review` fills a gap we have in our review dispatch.

2. **No quick-task delegation**: Every vendor interaction requires full OpenSpec ceremony (proposal → specs → tasks → work packages). The plugin's `/codex:rescue` enables ad-hoc "just fix this bug" delegation. We need this for small tasks that don't warrant a change-id.

3. **No unified vendor readiness check**: To verify if vendors are available, users must manually check CLI installation, API keys, and model access for each vendor independently. The plugin's `/codex:setup` shows how a single command can verify everything.

## What Changes

### Feature 1: Adversarial Review Mode

Add `--mode adversarial` flag to review dispatch that uses a contrarian prompt persona. Instead of checking "is this correct?", adversarial review asks "why is this the wrong approach?" and "what will break under edge cases?".

- Adds a new `dispatch_mode: "adversarial"` to `agents.yaml` CLI configs
- Adds adversarial prompt templates to `review_dispatcher.py`
- Adversarial findings flow through the same consensus pipeline with **equal weight** — a finding is only confirmed if another vendor (adversarial or standard) independently agrees
- Both `parallel-review-plan` and `parallel-review-implementation` skills gain `--adversarial` flag

### Feature 2: Micro-Task Quick Dispatch

A new skill `/quick-task` that delegates small ad-hoc tasks directly to any configured vendor **without OpenSpec artifacts**. Think bug investigation, quick fixes, code explanations, small refactors.

- Reuses `ReviewOrchestrator` + `CliVendorAdapter` for vendor discovery and dispatch
- Uses the `alternative` dispatch mode (read-write) instead of `review` (read-only)
- No change-id, no worktree, no proposal — just prompt → vendor → result
- Supports vendor selection (`--vendor codex`) or auto-selection (first available)
- Results returned inline to the user, not written to OpenSpec artifacts

### Feature 3: Vendor Health Check

A `/vendor:status` command that checks all configured vendors' readiness in one shot, **plus** a watchdog integration for continuous monitoring.

**CLI command** (standalone, no coordinator dependency):
- Iterates `agents.yaml`, checks CLI availability (`shutil.which`), API key resolution, model access
- Reports per-vendor status table: CLI installed, API key valid, models available, dispatch modes supported

**Watchdog integration** (requires coordinator):
- New `_check_vendor_health()` method in `WatchdogService`
- Emits `vendor.unavailable` events when a previously-available vendor goes offline
- Periodic health probes at watchdog interval (60s default)

## Impact

- **Review quality**: Adversarial mode catches design-level issues that standard reviews miss
- **Developer velocity**: Quick-task removes the OpenSpec tax for small tasks (est. 5-10min saved per task)
- **Operational visibility**: Health check prevents "why isn't my review dispatching?" debugging sessions
- **No breaking changes**: All features are additive — existing dispatch, consensus, and skill interfaces unchanged

## Approaches Considered

### Approach A: Integrated Extension (Recommended)

**Description**: Extend existing infrastructure (`review_dispatcher.py`, `agents.yaml`, `WatchdogService`) with new modes and a lightweight skill. All three features share the same vendor discovery and dispatch path.

**Pros**:
- Minimal new code — reuses `CliVendorAdapter`, `ReviewOrchestrator`, `ApiKeyResolver`
- Single `agents.yaml` as source of truth for all vendor interactions
- Adversarial findings naturally flow through existing consensus pipeline
- Health check reuses the same `can_dispatch()` logic already in the adapter

**Cons**:
- `review_dispatcher.py` grows in scope (prompt templates, health checks)
- Quick-task uses `alternative` dispatch mode which is designed for implementation, not ad-hoc tasks — may need a new mode

**Effort**: M

### Approach B: Plugin Architecture

**Description**: Create each feature as an independent plugin with its own vendor discovery and dispatch. Similar to how `codex-plugin-cc` is structured — self-contained slash commands with minimal dependencies.

**Pros**:
- Each feature is independently deployable and testable
- Simpler per-feature code — no need to understand the full orchestration stack
- Closer to the plugin model that inspired these features

**Cons**:
- Duplicates vendor discovery logic across 3 plugins
- Adversarial review would need its own consensus integration (can't reuse existing pipeline)
- Health check would duplicate `can_dispatch()` and API key resolution logic
- Diverges from our config-driven, single-adapter architecture

**Effort**: L

### Approach C: Minimal CLI Scripts

**Description**: Implement all three as standalone Python scripts in `skills/` that import from `review_dispatcher.py` but don't modify it. Adversarial mode is just a prompt wrapper, quick-task is a dispatch script, health check is a diagnostic script.

**Pros**:
- Zero modifications to existing infrastructure code
- Lowest risk — if a feature doesn't work out, just delete the script
- Quick to implement

**Cons**:
- Adversarial mode can't integrate with consensus synthesis without modifying the synthesizer
- Quick-task can't reuse dispatch modes without `agents.yaml` changes
- Health check probes would be ad-hoc rather than using the adapter's built-in checks
- No watchdog integration (scripts are one-shot, not daemon-integrated)

**Effort**: S

### Selected Approach

**Approach A: Integrated Extension** — selected because it maximizes reuse of existing infrastructure while keeping all vendor interactions routed through the single `ReviewOrchestrator` → `CliVendorAdapter` path. The three features are small enough that extending existing code is lower-effort than creating parallel systems.

## Dependencies

- `remote-control-coordinator` change (for watchdog integration in Feature 3) — the watchdog service and event bus must be merged first for the continuous monitoring component. The standalone CLI health check has no dependency.
- `agents.yaml` schema — adding `adversarial` dispatch mode requires coordinated update with any agents that consume this config.

## Risks

- **Adversarial prompt quality**: The value of adversarial review depends entirely on prompt engineering. Poor prompts produce noise rather than insight. Mitigation: start with a single well-tested prompt template, iterate based on findings quality.
- **Quick-task scope creep**: Without OpenSpec guardrails, users might delegate large tasks that should go through the full workflow. Mitigation: add a complexity heuristic that warns when a task looks too large for quick dispatch.
- **Vendor health probe cost**: Some vendors charge per API call. Health probes every 60s could accumulate cost. Mitigation: use lightweight probe (list models endpoint) and make probe interval configurable.
