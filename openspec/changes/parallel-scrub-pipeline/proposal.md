# Proposal: Parallel & Multi-Vendor Scrub Pipeline

**Change ID**: `parallel-scrub-pipeline`
**Status**: Draft
**Created**: 2026-03-26

## Why

The bug-scrub and fix-scrub skills run all phases sequentially despite having naturally independent stages. Bug-scrub's 8 collectors are pure functions with no shared state — running them in parallel yields 3-6x wall-clock improvement. Fix-scrub's auto-fix groups operate on non-overlapping file sets and its verification tools are independent subprocesses. Additionally, agent-tier fixes are currently single-vendor, missing the throughput and cross-validation benefits of multi-vendor dispatch that the MVRO infrastructure already supports.

## Summary

Add parallel execution and multi-vendor agent dispatch to the `/bug-scrub` and `/fix-scrub` skills. Both skills currently execute all phases sequentially, despite having naturally independent stages. This change introduces:

1. **Parallel collectors in bug-scrub** — run 8 independent signal collectors concurrently via `concurrent.futures.ProcessPoolExecutor`, reducing wall-clock time from ~30-60s to ~10s (bounded by the slowest collector).
2. **Parallel auto-fix execution in fix-scrub** — dispatch non-overlapping `ruff --fix` file groups concurrently.
3. **Parallel quality checks in fix-scrub** — run pytest, mypy, ruff, and openspec verification concurrently.
4. **Multi-vendor agent dispatch in fix-scrub** — route agent-tier fix prompts to different AI vendors (Claude, Codex, Gemini) based on finding category and vendor strengths, using the existing MVRO dispatch infrastructure.

## Motivation

- **Wall-clock time**: Bug-scrub collectors are I/O-bound (subprocess calls) and file-scan-bound. Running them in parallel yields 3-6x speedup.
- **Fix throughput**: Agent-tier fixes are currently dispatched to a single vendor. Multi-vendor dispatch increases throughput and provides cross-validation (one vendor's fix can be spot-checked by another).
- **Existing infrastructure**: The MVRO (Multi-Vendor Review Orchestration) dispatch and consensus infrastructure already exists in `skills/mvro/`. Reusing it avoids reinventing routing, dispatch, and result aggregation.

## Scope

### In Scope
- Parallel collector execution in bug-scrub `main.py`
- Parallel auto-fix groups in fix-scrub `execute_auto.py`
- Parallel verification checks in fix-scrub `verify.py`
- Multi-vendor dispatch config for fix-scrub agent prompts
- New `--parallel` CLI flag for both skills (opt-in, default off for backward compatibility)
- New `--vendors` CLI flag for fix-scrub to select dispatch targets

### Out of Scope
- Changing the Finding/SourceResult data models (stable contract)
- Modifying individual collector logic
- Adding new collectors or fix tiers
- Async/await rewrite (unnecessary — subprocess-based parallelism is sufficient)

## Success Criteria

1. Bug-scrub with `--parallel` produces identical reports to sequential mode
2. Fix-scrub with `--parallel` produces identical fix outcomes to sequential mode
3. Wall-clock time for bug-scrub collection phase reduced by >= 2x on projects with >= 4 sources
4. Multi-vendor dispatch routes findings to configured vendors without errors
5. All existing tests pass unchanged; new tests cover parallel paths
6. No regressions in CI (ruff, mypy strict, pytest)

## Risks

| Risk | Mitigation |
|------|------------|
| Subprocess race conditions (e.g., shared pytest cache) | Each collector already uses independent tool invocations; add `--cache-dir` isolation for pytest |
| ProcessPoolExecutor overhead on small projects | Default to sequential; `--parallel` is opt-in |
| Multi-vendor dispatch failures (vendor unavailable) | Fallback to single-vendor with warning, matching MVRO pattern |
| File-group overlap in parallel auto-fix | Plan phase already groups by file_path; add explicit overlap assertion |

## Dependencies

- MVRO dispatch infrastructure (`skills/mvro/scripts/`) for multi-vendor routing
- Agent dispatch config schema (`skills/mvro/scripts/agent_dispatch_configs.py`) for vendor selection
- Existing bug-scrub/fix-scrub test suites (341+ tests) as regression baseline
