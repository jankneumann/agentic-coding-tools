# Design: Parallel & Multi-Vendor Scrub Pipeline

**Change ID**: `parallel-scrub-pipeline`

## Architecture Overview

```
Bug-Scrub (parallel mode):
  ┌─────────────────────────────────────────────────┐
  │  ProcessPoolExecutor(max_workers=8)              │
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
  │  Multi-vendor agent dispatch (MVRO)              │
  │  ├─ Claude: type-error fixes (mypy findings)     │
  │  ├─ Codex: code-marker fixes (TODO/FIXME)        │
  │  └─ Gemini: deferred-item fixes                  │
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

### D1: ProcessPoolExecutor for Bug-Scrub Collectors

**Decision**: Use `concurrent.futures.ProcessPoolExecutor` (not `ThreadPoolExecutor`) for bug-scrub collectors.

**Rationale**: Collectors invoke subprocesses (pytest, ruff, mypy) and do file I/O. ProcessPoolExecutor avoids GIL contention and provides true parallelism. Each collector is a pure function `(project_dir) -> SourceResult` with no shared mutable state.

**Alternative considered**: `asyncio` with `asyncio.create_subprocess_exec`. Rejected because:
- All collectors are sync functions returning dataclasses
- Async rewrite would require changing the public API (collector signature)
- ProcessPoolExecutor wraps existing sync code without modification

### D2: ThreadPoolExecutor for Fix-Scrub Auto-Fixes

**Decision**: Use `ThreadPoolExecutor` for parallel ruff auto-fix groups.

**Rationale**: Each fix group invokes `subprocess.run("ruff check --fix <files>")` on non-overlapping file sets. Thread-based parallelism is sufficient since the work is subprocess-bound, and threads avoid the serialization overhead of process pools for the small FixGroup dataclass.

### D3: Opt-in `--parallel` Flag

**Decision**: Both skills default to sequential execution. Parallel mode requires `--parallel`.

**Rationale**: Backward compatibility. Sequential mode is well-tested (341+ tests). Parallel mode is a performance optimization, not a correctness change. Users/agents can opt in when wall-clock time matters.

### D4: Multi-Vendor Dispatch via MVRO

**Decision**: Reuse the existing MVRO dispatch infrastructure for agent-tier fix routing.

**Rationale**: MVRO already provides:
- `get_dispatch_configs()` — load vendor configs from `agent-dispatch-configs.yaml`
- `dispatch_review()` — route prompts to vendors with timeout handling
- Agent-dispatch-configs YAML schema with vendor capabilities

For fix-scrub, we add a new dispatch mode (`fix`) alongside the existing `review` mode. The dispatch config maps finding categories to preferred vendors:

```yaml
fix_dispatch:
  type_error:
    preferred_vendors: [claude, codex]
    fallback: claude
  code_marker:
    preferred_vendors: [codex, gemini]
    fallback: codex
  deferred_issue:
    preferred_vendors: [claude, gemini]
    fallback: claude
```

### D5: Parallel Verification

**Decision**: Run quality checks (pytest, mypy, ruff, openspec) concurrently in fix-scrub's verify phase.

**Rationale**: Each tool operates independently on the project directory. No shared state. Concurrent execution reduces verify wall-clock from ~20s (sequential) to ~8s (bounded by pytest).

### D6: Result Determinism

**Decision**: Parallel collectors return results in submission order (using `executor.map` or ordered `Future` collection), ensuring identical report output regardless of execution mode.

**Rationale**: Reports must be deterministic for diffing and regression detection. The aggregation phase sorts by severity/age anyway, but consistent ordering prevents spurious diff noise.

## Module Changes

### `skills/bug-scrub/scripts/parallel_runner.py` (new)

Encapsulates parallel execution logic:
```python
def run_collectors_parallel(
    collectors: dict[str, Callable],
    project_dir: str,
    max_workers: int = 8,
) -> list[SourceResult]:
    """Run collectors in parallel, return results in submission order."""
```

### `skills/bug-scrub/scripts/main.py` (modified)

- Add `--parallel` CLI flag
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
    original_failures: list[str] | None = None,
) -> VerificationResult:
    """Run quality checks concurrently."""
```

### `skills/fix-scrub/scripts/vendor_dispatch.py` (new)

```python
def dispatch_agent_fixes_multivendor(
    agent_prompts: list[dict],
    dispatch_config: dict,
) -> list[dict]:
    """Route agent-fix prompts to vendors based on finding category."""
```

### `skills/fix-scrub/scripts/main.py` (modified)

- Add `--parallel` and `--vendors` CLI flags
- Conditionally use parallel auto-fix, parallel verify, and multi-vendor dispatch

## Testing Strategy

- **Unit tests**: Each new module gets its own test file matching existing patterns (mocked subprocess, fixture data)
- **Equivalence tests**: Run both sequential and parallel modes on identical input, assert identical output
- **Vendor dispatch tests**: Mock MVRO dispatch, verify routing logic
- **Integration**: Covered by existing CI pipeline (ruff, mypy, pytest)

## File Inventory

| File | Action | Purpose |
|------|--------|---------|
| `skills/bug-scrub/scripts/parallel_runner.py` | Create | Parallel collector execution |
| `skills/bug-scrub/scripts/main.py` | Modify | Add `--parallel` flag, integrate parallel runner |
| `skills/bug-scrub/tests/test_parallel_runner.py` | Create | Tests for parallel collector execution |
| `skills/fix-scrub/scripts/parallel_auto.py` | Create | Parallel auto-fix execution |
| `skills/fix-scrub/scripts/parallel_verify.py` | Create | Parallel quality checks |
| `skills/fix-scrub/scripts/vendor_dispatch.py` | Create | Multi-vendor agent dispatch |
| `skills/fix-scrub/scripts/main.py` | Modify | Add `--parallel`, `--vendors` flags |
| `skills/fix-scrub/tests/test_parallel_auto.py` | Create | Tests for parallel auto-fix |
| `skills/fix-scrub/tests/test_parallel_verify.py` | Create | Tests for parallel verify |
| `skills/fix-scrub/tests/test_vendor_dispatch.py` | Create | Tests for vendor dispatch |
