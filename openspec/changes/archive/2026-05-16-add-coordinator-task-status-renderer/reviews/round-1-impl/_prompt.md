# IMPL_REVIEW — multi-vendor implementation review

You are reviewing the IMPLEMENTATION of OpenSpec change `add-coordinator-task-status-renderer`. The plan went through 2 rounds of PLAN_REVIEW (12 → 6 → 0 blocking findings) and the implementation passed a self-review (IMPL_ITERATE). Now: independent multi-vendor critique against the actual code on disk.

## What changed

- New skill: `skills/coordinator-task-status-renderer/` (SKILL.md + scripts/render_tasks_status.py + scripts/seed_tasks_from_md.py)
- Tests: `skills/tests/coordinator-task-status-renderer/test_render_tasks_status.py` + `test_seed_tasks_from_md.py`
- Plan-feature integration: `skills/plan-feature/SKILL.md` Step 12 edit + `skills/tests/plan-feature/test_gate2_invokes_seeder.py`
- Git hooks: `.githooks/pre-commit` + `.githooks/post-merge` (detect tasks.md changes, invoke renderer)
- Hook tests: `skills/tests/githooks/`
- E2E test: `skills/tests/integration/test_coord_task_status_e2e.py`
- Catalogue: `docs/skills-catalogue.md` entry + `CLAUDE.md` workflow note

Commits to review: `0c243ed` (feat) + `97ef489` (drop unused import) + `2c4336c` (handoff doc).

## Hard contracts that MUST hold (came out of PLAN_REVIEW; CRITICAL if violated)

1. **No `metadata` kwarg in seeder POST**: identity is encoded via labels `["change:<id>", "task:<key>"]`. `IssueCreateRequest` has no metadata field.
2. **Cycle detection BEFORE any POST**: seeder must detect cycles in-memory, exit 1 with NO POSTs if cycle exists.
3. **Renderer 5s wall-clock timeout** via `signal.alarm` or equivalent — NOT relying on `try_issue_list` internal timeout.
4. **Two-tier stale-marker idempotency**: timestamp must come from sidecar `.tasks-status.state.json` (persisted across renders during outage), not `datetime.now()` inline.
5. **Seeder parses ONLY hand-authored portion of tasks.md**: split on managed-block markers before parsing checkbox lines.
6. **100-limit pagination guard**: `len(results) == 100` from `try_issue_list` is treated as ERROR (assume truncation), not stale.
7. **Authoritative-source comment in managed block**: `<!-- Informational projection — see openspec/changes/<id>/proposal.md "What Doesn't Change" -->`.
8. **Status vocabulary**: boxes ticked for `closed` issues with `close_reason` matching `completed|done` (NOT `status == "completed"` — that status doesn't exist).
9. **Hooks NON-BLOCKING on renderer failure**: pre-commit + post-merge exit 0 even if renderer fails (only WARN).
10. **Hermetic hook tests**: tmp_path git fixture + `COORDINATOR_TASK_STATUS_RENDERER` env var stub.

## Review focus areas

### Correctness
- Each of the 10 contracts above. Open the file, find the relevant code, verify the contract holds.
- Edge cases: empty tasks.md, tasks.md with only the managed block, tasks.md with multiple managed blocks (should ERROR or just operate on the FIRST?), missing dependencies file, coordinator returns malformed JSON.
- Race conditions: pre-commit hook re-stages tasks.md; what if the user simultaneously runs `git add` for tasks.md during render?
- Concurrency: two `/plan-feature` Gate-2 approvals racing → idempotency on `(change:<id>, task:<key>)` label tuple — does the seeder atomically check-before-create or is there a TOCTOU window?

### Security
- The renderer reads coordinator HTTP responses and inserts content into `tasks.md`. Any injection risk if a malicious issue title contains markdown syntax (e.g., closing the managed-block marker via `-->` in the body)?
- Hooks run on every commit. Any unbounded resource usage on a tasks.md with thousands of lines?
- Seeder POSTs to coordinator. Any leak of secrets (API tokens, paths containing $HOME)?

### Performance
- Renderer is invoked on every commit touching tasks.md and on every merge. Is the HTTP call bounded? Cached?
- `try_issue_list` pagination: if there are >100 issues, the contract says ERROR — but on a change with 41 tasks, this is moot. What happens for changes with 200+ tasks (future)?

### Adherence to repo conventions
- Skill frontmatter (user_invocable: false, name, description) per skills/SCHEMA conventions
- Test placement (`skills/tests/<skill>/` per CLAUDE.md)
- Python via skills/.venv
- No edits to `.claude/skills/` or `.agents/skills/` (canonical-only at `skills/`)
- Conventional commit format

### Test quality
- Are tests actually testing behavior or just smoke?
- Coverage: do tests exercise the 10 hard contracts directly?
- Hermetic: no real HTTP, no real coordinator?
- Negative paths: tests for FAILURE modes (coordinator down, cycle detected, pagination overflow, malformed input)?

## Output format

**STRICT RULE**: Your entire response MUST be a single JSON object with this exact shape, and NOTHING else (no markdown fences, no commentary, no prose before or after):

`{"findings": [<finding-object>, <finding-object>, ...]}`

Each finding object has these fields:

- `id`: string, format `"f<n>-short-slug"` (e.g. `"f1-cycle-detection-missing"`)
- `type`: one of `"correctness"`, `"security"`, `"performance"`, `"test-quality"`, `"convention"`, `"other"`
- `criticality`: one of `"critical"`, `"high"`, `"medium"`, `"low"`
- `description`: 2-3 sentence problem statement
- `file_path`: relative path from repo root (e.g. `"skills/coordinator-task-status-renderer/scripts/render_tasks_status.py"`)
- `line_range`: array of two integers (e.g. `[42, 58]`)
- `disposition`: one of `"fix"`, `"defer"`, `"accept"`, `"dismiss"`
- `suggestion`: specific fix to apply, OR rationale for accepting/dismissing

Example minimal valid response when nothing is wrong:

`{"findings": []}`

Example with one finding:

`{"findings": [{"id": "f1-example", "type": "correctness", "criticality": "high", "description": "Example finding for prompt format.", "file_path": "skills/foo/bar.py", "line_range": [10, 20], "disposition": "fix", "suggestion": "Do the thing."}]}`

If all 10 contracts hold and you find no real issues, return `{"findings": []}` — that is a legitimate response.

**NO MARKDOWN FENCES. NO PROSE. JUST THE JSON OBJECT.**

## Files to start reading

- `skills/coordinator-task-status-renderer/scripts/render_tasks_status.py`
- `skills/coordinator-task-status-renderer/scripts/seed_tasks_from_md.py`
- `skills/coordinator-task-status-renderer/SKILL.md`
- `.githooks/pre-commit` (look for the new section)
- `.githooks/post-merge`
- `skills/tests/coordinator-task-status-renderer/*.py`
- `skills/tests/githooks/*.py`
- `skills/tests/integration/test_coord_task_status_e2e.py`
- `openspec/changes/add-coordinator-task-status-renderer/contracts/README.md` (the contracts the impl is supposed to satisfy)
- `openspec/changes/add-coordinator-task-status-renderer/specs/coordinator-task-status-renderer/spec.md`
- `openspec/changes/add-coordinator-task-status-renderer/design.md` (D1-D11 decisions)
