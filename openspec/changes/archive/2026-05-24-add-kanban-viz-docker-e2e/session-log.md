# Session Log — add-kanban-viz-docker-e2e

This change was authored organically across one session, with the OpenSpec
proposal artifacts back-filled after the implementation landed. Phase
entries below describe the merged-and-archived outcome rather than a fresh
plan→implement→cleanup flow.

---

## Phase: Plan + Implementation (retrospective, 2026-05-23)

**Agent**: claude-opus-4-7 | **Session**: this session

### Context

Built two related deliverables in a single working session:

1. **Hermetic Docker e2e for kanban-viz** — completes task 8.1 of
   `add-coordinator-kanban-viz` (which previously shipped only sanity-ping
   tests, not the transition assertion the spec promised). Pieces: compose
   env-var plumbing for `COORDINATOR_SSE_SIGNING_KEY`; orchestrator
   `scripts/e2e_kanban.py` with local-Docker and remote-URL modes; seed
   script `scripts/seed_kanban_board.py` for 15-card demo data; real SSE
   transition test in `e2e.integration.test.tsx` plus response-shape fixes
   for two pre-existing broken sanity tests; Makefile wrappers.
2. **`/review-artifacts` skill** — VS Code-based proposal review helper,
   three discovery modes (`--change-id`, `--git-changes`, `--paths`),
   worktree-aware, defaults to `code -n` (new window) so existing operator
   windows stay untouched.

### Decisions
1. **Bundle both deliverables into one OpenSpec change** — they emerged
   from the same session and the review-artifacts skill was the tool that
   surfaced the issues in the kanban-viz e2e work.
2. **Path B over `/iterate-on-implementation`** — the session iterated
   organically (6 issues found and fixed across implementation + 2 in the
   skill). A formal iteration pass would produce paper trail, not new
   findings.
3. **Empty-default `${VAR:-}` for SSE signing key** — preserves
   fail-closed posture from add-coordinator-kanban-viz D11.
4. **Generate validation-report.md from organic execution** — rather than
   re-running `/validate-feature` for paper trail; `make e2e-kanban`
   already exercises the full deploy/smoke/e2e path.

### Alternatives Considered
- **Separate docker-compose.e2e.yml**: rejected (drift risk vs reusing
  `--profile api`).
- **Bash/Make-only orchestration**: rejected (signal-handling brittleness;
  project uses Python for other multi-step scripts).
- **Switch vitest environment to node**: rejected (drop AbortSignal + use
  `reader.cancel()` is less intrusive than per-file environment).
- **`--ignore-vuln` for PYSEC-2026-161 / CVE-2026-45409 / PYSEC-2026-141**:
  rejected (fix versions exist for all three; only ignore advisories
  without fixed versions).

### Trade-offs
- Accepted **regex-based YAML parsing in `open_artifacts.py`** over a
  PyYAML dependency to keep the script stdlib-only.
- Accepted **bundling pre-existing mirror drift** (iterate-on-plan,
  worktree) into the chore-sync commit rather than landing it separately
  on main first.
- Accepted **`fetch` + `ReadableStream` over `EventSource`** for the SSE
  test — different client class than production but same wire protocol.

### Open Questions
- [ ] Should `e2e_kanban.py` be generalized into a
      `live-service-testing`-compliant launcher? Wait for second consumer.
- [ ] Should CI run `make e2e-kanban` on every PR? Open: Docker build
      adds ~2 min runtime; trigger policy TBD.
- [ ] Should the seed script wire `claimed_by`/`claimed_at` via direct
      asyncpg writes for full vendor-swimlane fidelity? Currently
      documented as limitation in the script docstring.

### Completed Work
- Compose env-var plumbing (D6)
- e2e_kanban.py orchestrator (D1, D2, D5)
- seed_kanban_board.py demo data script
- Vitest transition test + response-shape fixes (D3, D4)
- Makefile targets `e2e-kanban` + `e2e-kanban-remote` + help-regex fix
- review-artifacts skill (canonical + tests + mirrors)
- OpenSpec proposal, design, tasks, spec delta, work-packages, contracts
- Validation report (back-filled from actual `make e2e-kanban` run)
- CVE bumps: starlette 0.52.1→1.1.0, idna 3.13→3.15, urllib3 2.6.3→2.7.0

---

## Phase: Cleanup (2026-05-23)

**Agent**: claude-opus-4-7 | **Session**: this session

### Decisions
1. **Rebase-merge strategy** — per CLAUDE.md hybrid-strategy policy:
   `openspec/*` PRs default to rebase-merge so the 8 commits appear
   individually on main, preserving `git blame` / `git bisect` signal.
2. **Pre-merge validation gate passed via back-filled validation-report.md**
   — the change is purely operational tooling so a separate
   `/validate-feature` invocation would re-execute the same Docker
   lifecycle for no new signal. Report reflects the actual `make e2e-kanban`
   run (7ms SSE latency, 8/8 tests, all CI green).
3. **No task migration** — all 27 tasks in `tasks.md` are checked
   (retrospective tasks describing work that was already done).

### Alternatives Considered
- **Squash-merge**: rejected (would lose granular history needed by future
  agents debugging this change).
- **Run `/validate-feature` for fresh validation-report.md**: rejected
  (Docker lifecycle would re-run for identical signal; back-fill is more
  honest about how the change was actually validated).

### Trade-offs
- Accepted **8-commit history on main** over a single squash, costing more
  vertical space in `git log` but giving precise diff anchors.

### Open Questions
None at archive time.

### Context

Merged PR #179 (rebase strategy, `gh pr merge 179 --rebase
--delete-branch`) at 2026-05-24T00:13:33Z. Merge commit `9647378`.
Main pulled (already up to date from the merge). Archive operation
moves `openspec/changes/add-kanban-viz-docker-e2e/` to
`openspec/changes/archive/2026-05-23-add-kanban-viz-docker-e2e/` and
syncs spec deltas into `openspec/specs/coordinator-kanban-viz/spec.md`
(extends the existing capability with 3 new requirements + 11 scenarios).
