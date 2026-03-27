# Spec Delta: Parallel Scrub Pipeline

**Parent spec**: `openspec/specs/skill-workflow/spec.md`
**Change ID**: `parallel-scrub-pipeline`

## ADDED Requirements

### Requirement: Bug-scrub parallel collector execution

Bug-scrub SHALL support a `--parallel` CLI flag that runs all selected collectors concurrently using `concurrent.futures.ProcessPoolExecutor`. When `--parallel` is set, bug-scrub SHALL accept `--max-workers <N>` to limit concurrency (default: number of selected sources, max 8). Parallel collector execution SHALL produce results in the same order as the source list (deterministic output). If any collector raises an exception during parallel execution, bug-scrub SHALL record a `SourceResult` with `status="error"` and continue collecting from remaining sources. Parallel mode SHALL produce reports identical to sequential mode given the same inputs.

#### Scenario: parallel flag runs collectors concurrently
- GIVEN bug-scrub is invoked with `--parallel`
- WHEN the collection phase executes
- THEN all selected collectors run via ProcessPoolExecutor
- AND results are collected in submission order

#### Scenario: max-workers limits concurrency
- GIVEN bug-scrub is invoked with `--parallel --max-workers 4` and 8 sources selected
- WHEN collectors execute
- THEN at most 4 collectors run concurrently

#### Scenario: failed collector does not abort others
- GIVEN the mypy collector raises an exception during parallel execution
- WHEN all futures resolve
- THEN a SourceResult(source="mypy", status="error") is included in results
- AND all other collectors complete normally

#### Scenario: identical reports in both modes
- GIVEN a project with known findings
- WHEN bug-scrub runs sequentially and then with `--parallel`
- THEN both runs produce identical bug-scrub-report.json output

### Requirement: Fix-scrub parallel auto-fix and verification

Fix-scrub SHALL support a `--parallel` CLI flag that runs auto-fix groups and verification checks concurrently. Parallel auto-fix execution SHALL only process file groups with non-overlapping `file_path` sets concurrently. Fix-scrub `plan_fixes()` SHALL assert non-overlap of file paths across auto-fix groups when parallel mode is requested. Parallel verification SHALL run pytest, mypy, ruff, and openspec concurrently using `concurrent.futures.ThreadPoolExecutor`. Parallel verification SHALL collect all results before reporting (no fail-fast).

#### Scenario: parallel auto-fix on non-overlapping groups
- GIVEN fix-scrub is invoked with `--parallel`
- AND auto-fix groups have non-overlapping file paths
- WHEN auto-fix executes
- THEN non-overlapping groups run concurrently via ThreadPoolExecutor

#### Scenario: overlapping groups prevented
- GIVEN a FixPlan has two auto_groups with overlapping file_paths
- WHEN parallel mode validates the plan
- THEN an AssertionError is raised with a descriptive message

#### Scenario: parallel verification runs all checks concurrently
- GIVEN fix-scrub runs with `--parallel`
- WHEN the verification phase executes
- THEN pytest, mypy, ruff, and openspec run as concurrent futures
- AND all results are collected before the VerificationResult is assembled

#### Scenario: failed check does not abort others
- GIVEN pytest fails during parallel verification
- WHEN all checks complete
- THEN the VerificationResult includes results from all 4 tools

### Requirement: Multi-vendor agent dispatch for fix-scrub

Fix-scrub SHALL support a `--vendors` CLI flag accepting a comma-separated list of vendor names for agent-tier dispatch. When `--vendors` is set, fix-scrub SHALL route agent-fix prompts to vendors based on finding category using a dispatch config. The vendor dispatch config SHALL map finding categories (`type-error`, `code-marker`, `deferred-issue`) to ordered vendor preferences. If a preferred vendor is unavailable, fix-scrub SHALL fall back to the next vendor in the preference list, then to a default vendor. Multi-vendor dispatch SHALL generate vendor-specific prompt files (`agent-fix-prompts-<vendor>.json`) for SKILL.md consumption. The default dispatch config SHALL be defined in `skills/fix-scrub/scripts/vendor_dispatch_config.yaml`.

#### Scenario: vendors flag routes to specified vendors
- GIVEN fix-scrub is invoked with `--vendors claude,codex`
- WHEN agent-tier prompts are generated
- THEN prompts are routed only to claude and codex

#### Scenario: category-based routing
- GIVEN a type-error finding and dispatch config preferring claude for type-error
- WHEN vendor routing executes
- THEN the fix prompt is assigned to claude

#### Scenario: fallback on vendor unavailability
- GIVEN codex is unavailable and config prefers [codex, claude] for code-marker
- WHEN vendor routing executes for a code-marker finding
- THEN the prompt is routed to claude

#### Scenario: per-vendor prompt files created
- GIVEN prompts routed to claude and codex
- WHEN prompt files are written
- THEN `agent-fix-prompts-claude.json` and `agent-fix-prompts-codex.json` are created

### Requirement: Backward compatibility for scrub skills

Without `--parallel`, both skills SHALL behave identically to their current sequential implementation. Without `--vendors`, fix-scrub SHALL generate a single `agent-fix-prompts.json` as it does today. All existing CLI flags and their defaults SHALL remain unchanged.

#### Scenario: default mode is sequential
- GIVEN bug-scrub is invoked without `--parallel`
- WHEN collection executes
- THEN collectors run sequentially in a for-loop (existing behavior)

#### Scenario: default mode is single-vendor
- GIVEN fix-scrub is invoked without `--vendors`
- WHEN agent prompts are generated
- THEN a single `agent-fix-prompts.json` file is written

#### Scenario: existing flags preserved
- GIVEN bug-scrub is invoked with `--source pytest,ruff --severity medium`
- WHEN the command executes
- THEN behavior is identical to current implementation
