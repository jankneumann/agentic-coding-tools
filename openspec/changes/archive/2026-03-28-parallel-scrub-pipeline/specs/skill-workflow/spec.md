# Spec Delta: Parallel Scrub Pipeline

**Parent spec**: `openspec/specs/skill-workflow/spec.md`
**Change ID**: `parallel-scrub-pipeline`

## ADDED Requirements

### Requirement: Bug-scrub parallel collector execution

Bug-scrub SHALL support a `--parallel` CLI flag that runs all selected collectors concurrently using `concurrent.futures.ThreadPoolExecutor`. When `--parallel` is set, bug-scrub SHALL accept `--max-workers <N>` to limit concurrency (default: number of selected sources, max 8). Parallel collector execution SHALL produce results in the same order as the source list (deterministic output). If any collector raises an exception during parallel execution, bug-scrub SHALL record a `SourceResult` with `status="error"` and continue collecting from remaining sources. Parallel mode SHALL produce reports with identical findings, ordering, and source statuses as sequential mode (transient fields `timestamp` and `duration_ms` are excluded from equivalence).

#### Scenario: parallel flag runs collectors concurrently
- GIVEN bug-scrub is invoked with `--parallel`
- WHEN the collection phase executes
- THEN all selected collectors run via ThreadPoolExecutor
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

#### Scenario: collector exceeds timeout
- GIVEN a collector exceeds the per-collector timeout (default 300s)
- WHEN parallel mode is active
- THEN the collector returns SourceResult(status="error") with a timeout message
- AND remaining collectors continue

#### Scenario: normalized equivalence between modes
- GIVEN a project with known findings
- WHEN bug-scrub runs sequentially and then with `--parallel`
- THEN both runs produce identical findings, ordering, and source statuses
- AND transient fields (timestamp, duration_ms) are excluded from comparison

### Requirement: Fix-scrub parallel auto-fix and verification

Fix-scrub SHALL support a `--parallel` CLI flag that runs auto-fix groups and verification checks concurrently. Parallel auto-fix execution SHALL only process file groups with non-overlapping `file_path` sets concurrently. Fix-scrub `plan_fixes()` SHALL assert non-overlap of file paths across auto-fix groups when parallel mode is requested. Parallel verification SHALL run pytest, mypy, ruff, and openspec concurrently using `concurrent.futures.ThreadPoolExecutor`. Parallel verification SHALL collect all results before reporting (no fail-fast). The `verify_parallel()` function SHALL accept the same `original_failures: dict[str, set[str]] | None` parameter as the existing `verify()` function to preserve regression-delta behavior.

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

#### Scenario: parallel verify preserves regression detection
- GIVEN fix-scrub runs with `--parallel` and original_failures provided
- WHEN a tool reports new failures not in original_failures
- THEN those are included in VerificationResult.regressions

### Requirement: Multi-vendor agent dispatch for fix-scrub

Fix-scrub SHALL support a `--vendors` CLI flag accepting a comma-separated list of vendor names for agent-tier dispatch. When `--vendors` is set, fix-scrub SHALL assign each file-group prompt to exactly one vendor using round-robin distribution, maintaining exclusive file ownership. Multi-vendor dispatch SHALL generate vendor-specific prompt files (`agent-fix-prompts-<vendor>.json`) for SKILL.md consumption. Vendor discovery SHALL use `ReviewOrchestrator.from_coordinator()` with fallback to `from_agents_yaml()`. If a specified vendor is unavailable, fix-scrub SHALL skip it and redistribute its file-groups to remaining vendors with a warning.

#### Scenario: vendors flag routes to specified vendors
- GIVEN fix-scrub is invoked with `--vendors claude,codex`
- WHEN agent-tier prompts are generated for 4 file-groups
- THEN file-groups are assigned round-robin: claude gets groups 0,2 and codex gets groups 1,3

#### Scenario: exclusive file ownership maintained
- GIVEN fix-scrub is invoked with `--vendors claude,codex`
- WHEN vendor routing executes
- THEN each file-group is assigned to exactly one vendor
- AND no file path appears in more than one vendor's prompt file

#### Scenario: unavailable vendor redistributed
- GIVEN codex is unavailable and `--vendors claude,codex` is set
- WHEN vendor routing executes
- THEN all file-groups are assigned to claude
- AND a warning is emitted about codex being unavailable

#### Scenario: per-vendor prompt files created
- GIVEN prompts routed to claude and codex
- WHEN prompt files are written
- THEN `agent-fix-prompts-claude.json` and `agent-fix-prompts-codex.json` are created

### Requirement: Backward compatibility for scrub skills

Without `--parallel`, both skills SHALL behave identically to their current sequential implementation. Without `--vendors`, fix-scrub SHALL generate a single `agent-fix-prompts.json` as it does today. All existing CLI flags and their defaults SHALL remain unchanged. `--parallel` and `--vendors` SHALL be orthogonal — they can be used independently or together.

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

#### Scenario: parallel and vendors used together
- GIVEN fix-scrub is invoked with `--parallel --vendors claude,codex`
- WHEN execution runs
- THEN parallel auto-fixes execute concurrently
- AND agent prompts are routed to specified vendors per file-group
