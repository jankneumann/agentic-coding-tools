# Design: Parallel & Multi-Vendor Scrub Pipeline

**Change ID**: `parallel-scrub-pipeline`

## Architecture Overview

```
Bug-Scrub (parallel mode):
  ┌─────────────────────────────────────────────────┐
  │  ThreadPoolExecutor(max_workers=8)               │
  │  ├─ collect_pytest(project_dir)     ─┐           │
  │  ├─ collect_ruff(project_dir)        │           │
  │  ├─ collect_mypy(project_dir)        │ futures   │
  │  ├─ collect_openspec(project_dir)    │           │
  │  ├─ collect_architecture(project_dir)│           │
  │  ├─ collect_security(project_dir)    │           │
  │  ├─ collect_deferred(project_dir)    │           │
  │  └─ collect_markers(project_dir)    ─┘           │
  └──────────────────┬──────────────────────────────┘
                     ↓ all futures complete
              aggregate(results)
                     ↓
              render_report()

Fix-Scrub (parallel mode):
  classify(findings) → plan(classified)
                          ↓
  ┌──────────────────────────────────────────────────┐
  │  ThreadPoolExecutor(max_workers=N)               │
  │  ├─ ruff --fix group_A (files 1-5)  ─┐          │
  │  ├─ ruff --fix group_B (files 6-10)  │ futures  │
  │  └─ ruff --fix group_C (files 11-15)─┘          │
  └──────────────────┬───────────────────────────────┘
                     ↓
  ┌──────────────────────────────────────────────────┐
  │  Multi-vendor agent dispatch (per file-group)    │
  │  ├─ Vendor A: file-group 1 (all findings)        │
  │  ├─ Vendor B: file-group 2 (all findings)        │
  │  └─ Vendor C: file-group 3 (all findings)        │
  └──────────────────┬───────────────────────────────┘
                     ↓
  ┌──────────────────────────────────────────────────┐
  │  Parallel verification                           │
  │  ├─ pytest (subprocess)              ─┐          │
  │  ├─ mypy (subprocess)                 │ futures  │
  │  ├─ ruff (subprocess)                 │          │
  │  └─ openspec validate (subprocess)   ─┘          │
  └──────────────────┬───────────────────────────────┘
                     ↓
  track_completions() → render_fix_report()
```

## Design Decisions

### D1: ThreadPoolExecutor for Bug-Scrub Collectors

**Decision**: Use `concurrent.futures.ThreadPoolExecutor` (not `ProcessPoolExecutor`) for bug-scrub collectors.

**Rationale**: Python 3.14 on macOS defaults to `spawn` start method for multiprocessing. Collector functions are imported via `sys.path.insert(0, ...)` in main.py — worker processes spawned by `ProcessPoolExecutor` wouldn't be able to unpickle these function references because they don't inherit the parent's sys.path manipulation. `ThreadPoolExecutor` inherits the parent's module state, avoids serialization entirely, and is sufficient because the work is subprocess-bound (pytest, ruff, mypy invoke external processes). GIL contention is irrelevant for subprocess-bound workloads.

**Alternative considered**: `ProcessPoolExecutor` with explicit `fork` start method. Rejected because:
- `fork` is deprecated on macOS due to Apple framework compatibility issues
- Would need to set up sys.path in an initializer function in each worker
- Threads are simpler and sufficient for subprocess-bound work

**Alternative considered**: `asyncio` with `asyncio.create_subprocess_exec`. Rejected because:
- All collectors are sync functions returning dataclasses
- Async rewrite would require changing the public API (collector signature)

### D2: ThreadPoolExecutor for Fix-Scrub Auto-Fixes

**Decision**: Use `ThreadPoolExecutor` for parallel ruff auto-fix groups.

**Rationale**: Each fix group invokes `subprocess.run("ruff check --fix <files>")` on non-overlapping file sets. Thread-based parallelism is sufficient since the work is subprocess-bound.

### D3: Opt-in `--parallel` Flag

**Decision**: Both skills default to sequential execution. Parallel mode requires `--parallel`.

**Rationale**: Backward compatibility. Sequential mode is well-tested (341+ tests). Parallel mode is a performance optimization, not a correctness change. Users/agents can opt in when wall-clock time matters.

### D4: Multi-Vendor Dispatch per File-Group (not per Category)

**Decision**: Route agent-fix prompts to vendors per file-group, maintaining exclusive file ownership.

**Rationale**: The existing `generate_prompts()` groups findings by file and emits one prompt per file-group. A single file may contain mixed finding categories (type-error, code-marker, deferred-issue). Routing by category would split one file across multiple vendors, creating concurrent writes to the same file and breaking the file-scope isolation model. Instead, each file-group is assigned to exactly one vendor using round-robin or deterministic hashing, preserving exclusive file ownership.

The dispatch uses the existing `ReviewOrchestrator` from `skills/parallel-implement-feature/scripts/review_dispatcher.py`. Vendor discovery works via `from_coordinator()` (queries coordinator MCP `get_agent_dispatch_configs`) or `from_agents_yaml()` (reads `agent-coordinator/agents.yaml`). The dispatcher's `review` mode is reused with fix-oriented prompts — no new dispatch mode is needed.

**Vendor assignment strategy**:
```python
# Round-robin: distribute file-groups evenly across available vendors
for i, (file_path, prompt) in enumerate(agent_prompts):
    vendor = available_vendors[i % len(available_vendors)]
    vendor_prompts[vendor].append({"file": file_path, "prompt": prompt})
```

**Alternative considered**: Category-based routing (type-errors to Claude, markers to Codex). Rejected because:
- Breaks file-scope isolation when a file has mixed categories
- Adds complexity without clear quality benefit
- Round-robin already distributes load evenly

### D5: Parallel Verification

**Decision**: Run quality checks (pytest, mypy, ruff, openspec) concurrently in fix-scrub's verify phase.

**Rationale**: Each tool operates independently on the project directory. No shared state. Concurrent execution reduces verify wall-clock from ~20s (sequential) to ~8s (bounded by pytest). Each tool uses its own cache directory (.pytest_cache, .mypy_cache, .ruff_cache).

### D6: Result Determinism via Normalized Comparison

**Decision**: Parallel collectors return results in submission order. Equivalence tests compare normalized output excluding transient fields.

**Rationale**: Reports include transient fields (`timestamp`, `duration_ms`) that differ between runs. Literal JSON comparison would fail even with identical findings. Equivalence tests strip/freeze transient fields before comparison, comparing only: source ordering, statuses, finding lists, and messages.

## Module Changes

### `skills/bug-scrub/scripts/parallel_runner.py` (new)

Encapsulates parallel execution logic:
```python
def run_collectors_parallel(
    collectors: dict[str, Callable[[str], SourceResult]],
    project_dir: str,
    max_workers: int = 8,
    timeout_per_collector: int = 300,
) -> list[SourceResult]:
    """Run collectors in parallel via ThreadPoolExecutor, return results in submission order."""
```

### `skills/bug-scrub/scripts/main.py` (modified — by wp-orchestrator-update only)

- Add `--parallel` and `--max-workers` CLI flags
- Conditionally use `parallel_runner.run_collectors_parallel()` or existing sequential loop

### `skills/fix-scrub/scripts/parallel_auto.py` (new)

```python
def execute_auto_fixes_parallel(
    auto_groups: list[FixGroup],
    project_dir: str,
    max_workers: int = 4,
) -> tuple[list[ClassifiedFinding], list[ClassifiedFinding]]:
    """Run ruff --fix on non-overlapping file groups in parallel."""
```

### `skills/fix-scrub/scripts/parallel_verify.py` (new)

```python
def verify_parallel(
    project_dir: str,
    original_failures: dict[str, set[str]] | None = None,
) -> VerificationResult:
    """Run quality checks concurrently. Matches existing verify() signature."""
```

### `skills/fix-scrub/scripts/vendor_dispatch.py` (new)

```python
def route_prompts_to_vendors(
    agent_prompts: list[tuple[str, str]],
    available_vendors: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Route agent-fix prompts to vendors per file-group (round-robin).

    Maintains exclusive file ownership — each file-group goes to exactly one vendor.
    Returns dict mapping vendor name to list of {"file": str, "prompt": str}.
    """
```

### `skills/fix-scrub/scripts/main.py` (modified — by wp-orchestrator-update only)

- Add `--parallel` and `--vendors` CLI flags
- Conditionally use parallel auto-fix, parallel verify, and multi-vendor dispatch

## Testing Strategy

- **Unit tests**: Each new module gets its own test file matching existing patterns (mocked subprocess, fixture data)
- **Normalized equivalence tests**: Run both sequential and parallel modes on identical input, assert identical output after stripping transient fields (timestamp, duration_ms)
- **Vendor dispatch tests**: Mock vendor list, verify round-robin assignment, file-scope isolation
- **Integration**: Covered by existing CI pipeline (ruff, mypy, pytest)

## File Inventory

| File | Action | Owner Package | Purpose |
|------|--------|---------------|---------|
| `skills/bug-scrub/scripts/parallel_runner.py` | Create | wp-parallel-collectors | Parallel collector execution |
| `skills/bug-scrub/tests/test_parallel_runner.py` | Create | wp-parallel-collectors | Tests for parallel collector execution |
| `skills/fix-scrub/scripts/parallel_auto.py` | Create | wp-parallel-autofix | Parallel auto-fix execution |
| `skills/fix-scrub/tests/test_parallel_auto.py` | Create | wp-parallel-autofix | Tests for parallel auto-fix |
| `skills/fix-scrub/scripts/parallel_verify.py` | Create | wp-parallel-verify | Parallel quality checks |
| `skills/fix-scrub/tests/test_parallel_verify.py` | Create | wp-parallel-verify | Tests for parallel verify |
| `skills/fix-scrub/scripts/vendor_dispatch.py` | Create | wp-vendor-dispatch | Multi-vendor agent dispatch |
| `skills/fix-scrub/tests/test_vendor_dispatch.py` | Create | wp-vendor-dispatch | Tests for vendor dispatch |
| `skills/bug-scrub/scripts/main.py` | Modify | wp-orchestrator-update | Add `--parallel` flag, integrate parallel runner |
| `skills/fix-scrub/scripts/main.py` | Modify | wp-orchestrator-update | Add `--parallel`, `--vendors` flags |
