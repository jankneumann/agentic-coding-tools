# Tasks: Parallel & Multi-Vendor Scrub Pipeline

**Change ID**: `parallel-scrub-pipeline`

## Task Groups

### TG1: Bug-Scrub Parallel Collectors

- [ ] T1.1: Create `skills/bug-scrub/scripts/parallel_runner.py` with `run_collectors_parallel()` using ProcessPoolExecutor
- [ ] T1.2: Add `--parallel` / `--max-workers` CLI flags to `skills/bug-scrub/scripts/main.py`
- [ ] T1.3: Integrate parallel runner into `main.py:run()` with conditional dispatch
- [ ] T1.4: Create `skills/bug-scrub/tests/test_parallel_runner.py` — unit tests for parallel execution, error handling, timeout
- [ ] T1.5: Add equivalence test: sequential vs parallel produces identical SourceResult lists

### TG2: Fix-Scrub Parallel Auto-Fixes

- [ ] T2.1: Create `skills/fix-scrub/scripts/parallel_auto.py` with `execute_auto_fixes_parallel()` using ThreadPoolExecutor
- [ ] T2.2: Add file-group overlap assertion to `plan_fixes.py` (safety check for parallel mode)
- [ ] T2.3: Add `--parallel` CLI flag to `skills/fix-scrub/scripts/main.py`
- [ ] T2.4: Integrate parallel auto-fix into `main.py:run()` with conditional dispatch
- [ ] T2.5: Create `skills/fix-scrub/tests/test_parallel_auto.py` — unit tests for parallel ruff execution

### TG3: Fix-Scrub Parallel Verification

- [ ] T3.1: Create `skills/fix-scrub/scripts/parallel_verify.py` with `verify_parallel()` using ThreadPoolExecutor
- [ ] T3.2: Integrate parallel verify into `main.py:run()` when `--parallel` is set
- [ ] T3.3: Create `skills/fix-scrub/tests/test_parallel_verify.py` — tests for concurrent quality checks
- [ ] T3.4: Add equivalence test: sequential vs parallel verify produces identical VerificationResult

### TG4: Fix-Scrub Multi-Vendor Agent Dispatch

- [ ] T4.1: Create `skills/fix-scrub/scripts/vendor_dispatch.py` with category-to-vendor routing
- [ ] T4.2: Define vendor dispatch config schema (extend `agent-dispatch-configs.yaml` or new config)
- [ ] T4.3: Add `--vendors` CLI flag to fix-scrub `main.py`
- [ ] T4.4: Integrate vendor dispatch into fix-scrub SKILL.md layer (agent prompt routing)
- [ ] T4.5: Create `skills/fix-scrub/tests/test_vendor_dispatch.py` — routing logic, fallback, unavailable vendor
- [ ] T4.6: Add default vendor dispatch config mapping categories to vendor preferences

### TG5: Integration & Documentation

- [ ] T5.1: Run full test suite (bug-scrub + fix-scrub) and fix any regressions
- [ ] T5.2: Update bug-scrub SKILL.md with `--parallel` usage documentation
- [ ] T5.3: Update fix-scrub SKILL.md with `--parallel` and `--vendors` usage documentation
- [ ] T5.4: CI validation — ensure ruff, mypy strict, pytest all pass

## Dependencies

```
TG1 (bug-scrub parallel) — independent
TG2 (fix-scrub parallel auto) — independent
TG3 (fix-scrub parallel verify) — independent
TG4 (multi-vendor dispatch) — depends on MVRO infrastructure (already exists)
TG5 (integration) — depends on TG1, TG2, TG3, TG4
```

## Parallel Execution Potential

TG1, TG2, TG3, and TG4 are fully independent work packages — they touch non-overlapping file scopes and can be implemented by separate agents concurrently. TG5 is the integration gate.
