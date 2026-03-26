# Tasks: Multi-Vendor Review Orchestration

## Task 1: Review Dispatcher Script

**Status**: planned
**Depends on**: —

Create `skills/parallel-implement-feature/scripts/review_dispatcher.py`:

- [ ] `CliConfig`, `ModeConfig` data classes (parsed from agents.yaml `cli` section)
- [ ] `CliVendorAdapter` — single generic class, config-driven (no per-vendor subclasses)
- [ ] `CliVendorAdapter.build_command(mode, prompt, model)` — construct CLI args from config
- [ ] `CliVendorAdapter.can_dispatch(mode)` — verify binary exists and mode is configured
- [ ] `ReviewOrchestrator` with `discover_reviewers()`, `dispatch_all_reviews()`, `wait_for_results()`
- [ ] `ReviewOrchestrator.classify_error(stderr)` — detect capacity/auth/transient/unknown errors
- [ ] `discover_reviewers()` — load agents.yaml, filter agents with `cli` section, check coordinator discovery
- [ ] Model fallback on capacity errors (retry with `cli.model_fallbacks` chain)
- [ ] Auth error detection and user-facing re-login messages
- [ ] `write_review_manifest()` — emit `reviews/review-manifest.json` with vendor metadata, timing, models attempted
- [ ] CLI entry point for standalone testing
- [ ] Unit tests for command construction, error classification, model fallback, manifest generation

## Task 2: Consensus Synthesizer Script

**Status**: planned
**Depends on**: —

Create `skills/parallel-implement-feature/scripts/consensus_synthesizer.py`:

- [ ] `VendorFindings`, `FindingMatch`, `ConsensusFinding`, `ConsensusReport` data classes
- [ ] `load_findings()` — load and validate per-vendor findings JSON
- [ ] `match_findings()` — cross-vendor finding matching (location + type + similarity)
- [ ] `compute_consensus()` — classify as confirmed/unconfirmed/disagreement
- [ ] `write_report()` — output consensus-report.json
- [ ] CLI entry point for standalone testing
- [ ] Unit tests for matching algorithm with fixture findings

## Task 3: Consensus Report Schema

**Status**: planned
**Depends on**: —

Create `openspec/schemas/consensus-report.schema.json`:

- [ ] Schema definition extending review-findings pattern
- [ ] `reviewers` array with vendor, timing, success metadata
- [ ] `consensus_findings` array with match status, agreed criticality/disposition
- [ ] `quorum_met` boolean
- [ ] `review_manifest` metadata section

## Task 4: Integration Orchestrator Enhancement

**Status**: planned
**Depends on**: Task 1, Task 2, Task 3

Update `skills/parallel-implement-feature/scripts/integration_orchestrator.py`:

- [ ] `record_review_findings()` — accept optional `vendor` parameter
- [ ] `record_consensus()` — new method for consensus reports
- [ ] `check_integration_gate()` — use consensus findings (confirmed block, unconfirmed warn)
- [ ] Update `generate_execution_summary()` to include multi-vendor review section
- [ ] Update existing tests for backward compatibility

## Task 5: Review Dispatch Skill Integration

**Status**: planned
**Depends on**: Task 1, Task 4

Update parallel workflow skills to use review dispatcher:

- [ ] Update `parallel-implement-feature/SKILL.md` Phase C to reference multi-vendor dispatch
- [ ] Add review dispatch step between package completion and integration gate
- [ ] Add consensus synthesis step before integration gate check
- [ ] Update `parallel-review-plan/SKILL.md` to document vendor dispatch usage
- [ ] Update `parallel-review-implementation/SKILL.md` to document vendor dispatch usage

## Task 6: Vendor Adapter Tests

**Status**: planned
**Depends on**: Task 1

- [ ] Mock subprocess tests for each adapter (codex, gemini, claude)
- [ ] Timeout handling tests
- [ ] Invalid JSON output handling tests
- [ ] Missing CLI binary tests (graceful degradation)
- [ ] Discovery fallback tests (coordinator unavailable → `which` detection)

## Task 7: Agent Config Schema Extension

**Status**: planned
**Depends on**: —

Extend `agents.yaml` and `agents_config.py` with `cli` configuration section:

- [ ] Add `CliConfig` dataclass: `command`, `dispatch_modes`, `model_flag`, `model`, `model_fallbacks`
- [ ] Add optional `cli: CliConfig | None` to `AgentEntry` dataclass
- [ ] Add `cli` sections to all 6 agent entries in `agents.yaml` with dispatch modes, model flags, and fallbacks
- [ ] Update `load_agents_config()` to parse `cli` section (backward-compatible: missing `cli` = None)
- [ ] Unit tests for loading agents.yaml with and without cli sections

## Task 8: Spec Updates

**Status**: planned
**Depends on**: Task 4, Task 5

- [ ] Add multi-vendor review requirements to `openspec/specs/skill-workflow/spec.md`
- [ ] Document consensus model in parallel development design doc
