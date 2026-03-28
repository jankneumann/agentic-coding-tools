# Tasks: Parallel & Multi-Vendor Scrub Pipeline

**Change ID**: `parallel-scrub-pipeline`

## Task Groups

### TG1: Bug-Scrub Parallel Collectors (wp-parallel-collectors)

- [ ] T1.1: Create `skills/bug-scrub/scripts/parallel_runner.py` with `run_collectors_parallel()` using ThreadPoolExecutor
- [ ] T1.4: Create `skills/bug-scrub/tests/test_parallel_runner.py` — unit tests for parallel execution, error handling, per-collector timeout
- [ ] T1.5: Add normalized equivalence test: sequential vs parallel produces identical SourceResult lists (excluding duration_ms)

### TG2: Fix-Scrub Parallel Auto-Fixes (wp-parallel-autofix)

- [ ] T2.1: Create `skills/fix-scrub/scripts/parallel_auto.py` with `execute_auto_fixes_parallel()` using ThreadPoolExecutor
- [ ] T2.2: Add file-group overlap assertion to `plan_fixes.py` (safety check for parallel mode)
- [ ] T2.5: Create `skills/fix-scrub/tests/test_parallel_auto.py` — unit tests for parallel ruff execution

### TG3: Fix-Scrub Parallel Verification (wp-parallel-verify)

- [ ] T3.1: Create `skills/fix-scrub/scripts/parallel_verify.py` with `verify_parallel()` using ThreadPoolExecutor — must match existing `verify()` signature (`original_failures: dict[str, set[str]] | None`)
- [ ] T3.3: Create `skills/fix-scrub/tests/test_parallel_verify.py` — tests for concurrent quality checks, regression detection
- [ ] T3.4: Add equivalence test: sequential vs parallel verify produces identical VerificationResult

### TG4: Fix-Scrub Multi-Vendor Agent Dispatch (wp-vendor-dispatch)

- [ ] T4.1: Create `skills/fix-scrub/scripts/vendor_dispatch.py` with per-file-group round-robin vendor routing and vendor discovery via ReviewOrchestrator
- [ ] T4.5: Create `skills/fix-scrub/tests/test_vendor_dispatch.py` — routing logic, exclusive file ownership assertion, unavailable vendor fallback

### TG5: Orchestrator Integration (wp-orchestrator-update)

- [ ] T1.2: Add `--parallel` / `--max-workers` CLI flags to `skills/bug-scrub/scripts/main.py`
- [ ] T1.3: Integrate parallel runner into `main.py:run()` with conditional dispatch
- [ ] T2.3: Add `--parallel` CLI flag to `skills/fix-scrub/scripts/main.py`
- [ ] T2.4: Integrate parallel auto-fix into fix-scrub `main.py:run()` with conditional dispatch
- [ ] T3.2: Integrate parallel verify into fix-scrub `main.py:run()` when `--parallel` is set
- [ ] T4.3: Add `--vendors` CLI flag to fix-scrub `main.py` and wire vendor dispatch

### TG6: Documentation (wp-skill-docs)

- [ ] T5.2: Update bug-scrub SKILL.md with `--parallel` usage documentation
- [ ] T5.3: Update fix-scrub SKILL.md with `--parallel` and `--vendors` usage documentation

### TG7: Integration & Validation (wp-integration)

- [ ] T5.1: Run full test suite (bug-scrub + fix-scrub) and fix any regressions
- [ ] T5.4: CI validation — ensure ruff, mypy strict, pytest all pass

## Dependencies

```
TG1 (parallel collectors) ─┐
TG2 (parallel auto-fix)    │ all independent, run in parallel
TG3 (parallel verify)      │
TG4 (vendor dispatch)     ─┘
         ↓
TG5 (orchestrator) — depends on TG1, TG2, TG3, TG4
TG6 (docs) — depends on TG1, TG4
         ↓
TG7 (integration) — depends on TG5, TG6
```

## Parallelizability Assessment

- **Independent tasks**: 9 (TG1: 3, TG2: 3, TG3: 3, TG4: 2 — no shared files)
- **Sequential chains**: 2 (TG5 after TG1-4, TG7 after TG5+TG6)
- **Max parallel width**: 4 (TG1, TG2, TG3, TG4 run concurrently)
- **File overlap conflicts**: None — main.py modification centralized in TG5/wp-orchestrator-update
