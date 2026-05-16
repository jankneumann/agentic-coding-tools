# IMPL_REVIEW Handoff — add-coordinator-task-status-renderer

**Handoff ID:** `impl-review-7d3e9f2a`
**Phase:** IMPL_REVIEW
**Tier:** single-vendor fallback (opus 4.7)
**Date:** 2026-05-15
**Outcome:** `converged`

## Limitation acknowledgment

This was a **single-vendor (opus 4.7) fallback IMPL_REVIEW**. The multi-vendor
CLI dispatcher failed all three vendors today:

- claude: timed out at 900s
- codex: returned no findings (vacuous)
- gemini: timed out

To compensate, this single pass deliberately covered angles a multi-vendor
review would have split: security, performance, edge cases, error handling,
race conditions, repo conventions. Vendor-diversity coverage was lost — flag
this in the merge log so future autopilot tuning can address dispatcher
flakes before relying on convergent multi-vendor IMPL_REVIEW.

## Findings table

| ID | Severity | File:Lines | Disposition | Rationale |
|---|---|---|---|---|
| F1 | HIGH | `skills/coordinator-task-status-renderer/scripts/render_tasks_status.py:208-212` | **fixed** | Markdown injection: coordinator-returned `title`/`assignee`/`close_reason` were written verbatim into the managed block. A malicious title containing `\n<!-- GENERATED: end coordinator:tasks-status -->\n## INJECTED` could close the block early and inject content into the hand-authored suffix. Fix: introduce `_sanitize_inline()` to collapse newlines and neutralize embedded marker tokens. |
| F2 | HIGH | `render_tasks_status.py:366` and `seed_tasks_from_md.py:245` | **fixed** | Path traversal: `change_id` was used directly in `Path(repo_root / "openspec" / "changes" / change_id / ...)` with no validation. `change_id="../../etc/passwd"` would resolve outside the intended directory. Fix: validate against `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` at entry to `render()` and `seed()`. |
| F3 | HIGH | `.gitignore` | **fixed** | Sidecar state file `openspec/changes/<id>/.tasks-status.state.json` was NOT in `.gitignore` despite contract README claiming it is "(gitignored)". An operator who commits during an outage would leak the sidecar to git history. Fix: add explicit entry under "Per-run autopilot phase-resolution cache". |
| F4 | MEDIUM | `render_tasks_status.py:284-306` | **dismiss** | The `signal.SIGALRM` timeout wrapper is POSIX-only and won't work on Windows. Out of scope for this change (the existing repo workflow is POSIX-only and there's no Windows CI). Documented for future cross-platform work. |
| F5 | MEDIUM | `render_tasks_status.py:262-268` | **dismiss** | Sidecar JSON corruption recovery is already handled — `_read_sidecar` catches `JSONDecodeError` and returns `{}`. Verified by code reading; no fix needed. |
| F6 | LOW | `render_tasks_status.py:329-330` | **defer** | `_resolve_repo_root` falls back to `Path.cwd()` on a `git` lookup failure; that can produce wrong-repo writes if the hook is somehow invoked outside a checkout. Low severity because hooks themselves resolve `REPO_ROOT` first and pass it via the file path; renderer's CLI parity for ad-hoc use is the only exposure. Defer: a `--require-git-root` flag could harden this if real misuse is observed. |
| F7 | LOW | `render_tasks_status.py:230-235` | **dismiss** | Tie-breaker uses `_extract_task_key(i) or ""` which would collide on multiple unkeyed issues. But the prior filter at L227 (`_render_issue_line` returns `None` and is skipped) means unkeyed issues never reach the sort. Verified by reading; no fix needed. |
| F8 | LOW | `.githooks/pre-commit:85-100` | **defer** | The `while IFS= read -r path` loop runs inside a subshell of a pipe, so any state set inside (e.g., counters) wouldn't propagate. Today nothing depends on that, but if the hook grows error-aggregation logic later, it'll bite. Defer with comment; >50 LOC to switch the loop pattern safely. |
| F9 | LOW | `render_tasks_status.py:391-399` | **dismiss** | Pagination cap-exceeded path (returns 1) is the explicit contract per PLAN_REVIEW contract #6 — NOT a finding. |
| F10 | LOW | `seed_tasks_from_md.py:300-312` | **dismiss** | Forward-ref dropping path is contract-specified ("Forward references … are logged and dropped — non-fatal"). |
| F11 | INFO | tests | **fixed (regression)** | Added 4 regression tests: path-traversal rejection (renderer + seeder), marker-injection sanitization, newline sanitization in assignee/close_reason. |

## Fixes applied

Single commit (to follow this handoff):

- **`fix(coordinator-task-status-renderer): IMPL_REVIEW — sanitize injection + path-traversal guard + gitignore sidecar`**
  - `render_tasks_status.py`: add `_CHANGE_ID_RE` validator and `_sanitize_inline()`; apply sanitizer to title/assignee/close_reason; reject invalid change-ids
  - `seed_tasks_from_md.py`: add same `_CHANGE_ID_RE` validator at entry to `seed()`
  - `.gitignore`: add `openspec/changes/*/.tasks-status.state.json`
  - tests: 4 new regression tests in `test_render_tasks_status.py` and `test_seed_tasks_from_md.py`

Total ~80 LOC added, ~5 LOC modified. Well under the ≤150 LOC budget.

## Findings deferred to follow-up

- **F6** (cwd fallback): defer until real misuse observed; the hook layer
  provides defense in depth today.
- **F8** (subshell counters in hook): defer; would require >50 LOC and
  no current dependency on cross-iteration state in the hook loop.

## Final test count

**47 passed** (up from 43):
- 32 in `skills/tests/coordinator-task-status-renderer/` (was 28)
- 5 in `skills/tests/githooks/`
- 1 in `skills/tests/plan-feature/`
- 2 in `skills/tests/integration/test_coord_task_status_e2e.py`
- (Plus shared fixture/helper tests counted by the suite)

Command:
```
skills/.venv/bin/python -m pytest skills/tests/coordinator-task-status-renderer/ \
  skills/tests/plan-feature/ skills/tests/githooks/ \
  skills/tests/integration/test_coord_task_status_e2e.py --tb=short -q
```

## Contracts re-verified (no re-litigation)

All 10 PLAN_REVIEW contracts confirmed still holding by reading the
implementation:

1. No `metadata` kwarg in seeder POST — confirmed (`payload` dict only has
   `title`, `issue_type`, `labels`, optional `depends_on`).
2. Cycle detection before any POST — confirmed (`_detect_cycles` runs before
   `_existing_issues_by_task_key`; test `test_seeder_exits_1_on_cycle_with_no_posts`
   asserts `fb.list_calls == []`).
3. Renderer 5s wall-clock timeout via `signal.alarm` — confirmed.
4. Two-tier stale-marker idempotency via sidecar — confirmed.
5. Seeder parses only hand-authored portion — confirmed (`_strip_managed_block`
   called by `_parse_tasks`).
6. 100-limit pagination ERROR — confirmed (exit 1, not stale).
7. Authoritative-source comment in managed block — confirmed.
8. Status vocabulary — confirmed (`pending|claimed|running|completed|failed|cancelled`).
9. Hooks NON-BLOCKING — confirmed (hook always `exit 0`).
10. Hermetic hook tests — confirmed (`tmp_path` + `core.hooksPath` + env stub).

## Recommendation

**Proceed to VALIDATE.** All HIGH findings fixed inline; tests green at
47/47; no contract regressions. Vendor-diversity loss noted above but
single-vendor pass covered the angles a multi-vendor split would have
checked.
