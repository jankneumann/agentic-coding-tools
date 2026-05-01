# Session Log: add-engineering-methodology-skills

---

## Phase: Plan (2026-05-01)

**Agent**: claude-opus-4-7 (cloud harness) | **Session**: claude/review-external-skills-1Cuh7

### Decisions

1. **Single OpenSpec change covering 10 ADOPT + 8 ADAPT + 4 cross-cutting structural changes** — operator-confirmed up front. Keeps the convention introduction and its first wave of consumers in one atomic unit.

2. **Approach C (scaffold-then-content) selected at Gate 1** — Phase 0 ships the convention (references library, install.sh extension, content-invariant test framework, canonical tail-block template) so Phases 1 and 2 inherit it. Eliminates need for a final consistency sweep across the 21 skills affected by the tail-block convention.

3. **Coordinated tier with 9 work packages** — coordinator HTTP available with full capabilities. Phase 0 sequential (`wp-scaffold`); Phases 1+2 fan out to 7 parallel packages because their write-scopes are disjoint (Phase 1 owns NEW skill dirs; Phase 2 owns EXISTING skill dirs); Phase 3 (`wp-integration`) gates on all of Phase 1+2.

4. **Per-skill `user_invocable` heuristic locked**: 7 of 10 new skills are `user_invocable: true` (operator-triggered), 3 are `user_invocable: false` (orchestrator-loaded only: `context-engineering`, `source-driven-development`, `browser-testing-with-devtools`). Rule: if operators reasonably want a slash command, true; if it's a behavior orchestrators perform automatically, false.

5. **Tail-block convention scoped to user_invocable skills only** (operator confirmed at discovery): 21 skills (3 pilots + 10 new + 8 ADAPT). Infrastructure skills exempt.

6. **Test coverage: full content invariants** (operator confirmed at discovery): frontmatter parse + required keys + cross-reference resolution + tail-block presence + section ordering. Implemented as shared `skills/tests/_shared/conftest.py` helpers. Architectural lint, not just smoke test.

7. **Combined-edit pass for ADAPT targets** (D6): each ADAPT target receives extracted patterns AND the tail-block in the same commit, avoiding double-touches.

### Alternatives Considered

- **New `engineering-methodology` capability** — rejected; would orphan references library and tail-block convention into a third location. Kept everything under `skill-workflow`.
- **Approach B (parallel by phase, no template)** — rejected; risks stylistic drift across 21 skills; ~3–5 fewer Phase 0 tasks not worth the consistency cost.
- **Approach A (big-bang sequential)** — rejected; doesn't use the available coordinator parallelism; ~5–7 days wall-clock.
- **Standalone `spec-driven-development` skill** — explicitly skipped; OpenSpec covers it. Optional text-only lift of the `ASSUMPTIONS I'M MAKING:` template into the proposal template.
- **Standalone `ci-cd-and-automation` skill** — explicitly skipped; overlaps `validate-feature`. Pull only preview-deploy + dependabot config templates if/when CI authoring is needed.
- **CI lint rule for tail block** — deferred; content invariants in tests cover the convention.

### Trade-offs

- Accepted **larger Phase 0 (10 tasks) for guaranteed consistency** over smaller Phase 0 with a Phase 3 consistency sweep — cleaner final history.
- Accepted **two similar frontmatter keys (`requires:` and `related:`)** over a single weighted-dependency key — overloading `requires:` would force every methodology skill to declare hard deps on every kindred skill. Kept the semantic difference clean.
- Accepted **Phase 1 and Phase 2 running concurrently** (7 packages active simultaneously after Phase 0 lands) — parallel-zones validation confirmed disjoint write scopes; lock pressure analyzed and clean.
- Accepted **per-skill author judgment on Python example coverage** in ported skills — explicit "preserve JS/TS, add Python alongside" rule (operator decision); no rigid quota per skill.

### Open Questions

- [ ] Coordinator's `POST /features/register` endpoint reports `capability_unavailable` despite `CAN_FEATURE_REGISTRY=true` in `check_coordinator.py` output. Step 10 (register resource claims) was skipped non-fatally. Worth confirming during Phase 0 whether this affects work-package dispatch.
- [ ] `add-prototyping-stage` (0/41 tasks) is in flight and adds another new skill. No file overlap with this change, but if it merges first the install.sh test fixture may need a small adjustment. Captured as a Phase 3 smoke check.
- [ ] `conditional-worktree-generation` (21/23 tasks) modifies `worktree.py`. We don't touch that file, but plan-revision rebase may be needed at integration time.

### Context

Planning followed the `/plan-feature` skill end-to-end in coordinated tier. Discovery agent surfaced 3 in-progress changes (none with file conflict), confirmed `install.sh` auto-discovers any `SKILL.md`-bearing directory, confirmed the `requires:` precedent for adding `related:`, and confirmed `pyproject.toml` `testpaths` is explicit and must be updated for each new test dir. Two operator decisions at the discovery gate (tail-block scope = user-invocable-only; tests = full content invariants) shaped Phase 0 scope. Approach C selected at Gate 1. All planning artifacts validated: `openspec validate --strict` pass, `validate_work_packages.py` pass, `parallel_zones.py --validate-packages` confirmed scope and lock disjointness across the 7 parallel packages.

---

## Phase: Implementation (2026-05-01)

**Agent**: claude-opus-4-7 (cloud harness orchestrator + 7 parallel general-purpose sub-agents) | **Session**: claude/review-external-skills-1Cuh7

### Decisions

1. **Phase 0 executed directly by orchestrator** — references library, install.sh extension, content-invariant test framework, docs convention. ~1600 LoC across 17 files. Independent commit `d238378` to provide a clean checkpoint before fan-out.

2. **Phase 1+2 dispatched as 7 parallel sub-agents in a single message** — disjoint write scopes (verified by parallel_zones --validate-packages at plan time) made parallel-without-locks safe. Each sub-agent received a self-contained ~3000-token prompt with WRITE allow / DO NOT touch rules, source URL for porting, frontmatter schema, tail-block requirement, test pattern, and a hard "do not commit" rule.

3. **Single batched commit for Phase 1+2** — per-package atomic commits weren't viable when 7 sub-agents land concurrently. Commit `23ffe48` includes all Phase 1 (10 new skills) + Phase 2 (8 ADAPT edits + schema + CLAUDE.md). Per-package context is preserved in the commit body's structured breakdown.

4. **`--import-mode=importlib` added to pyproject.toml** — necessary fix for sibling test_skill_md.py basename collisions. 4 of 7 sub-agents independently surfaced this. Treated as Phase 0 infra correction (logically belonged there) rather than a separate change.

### Alternatives Considered

- **Per-package atomic commits**: Rejected. Sub-agent file landings interleave non-deterministically; staging by file-path glob would have raced with in-flight writes. Single batched commit + structured commit message preserves per-package traceability.
- **Wait for all 7 sub-agents before committing anything**: Rejected. Stop-hook fired after the first sub-agent returned; committing in a single push at the end risked losing all work if the session terminated mid-flight.
- **Author Phase 1+2 directly without sub-agents**: Rejected. Estimated ~5500 LoC of skill content; sequential authoring would have consumed many times the wall-clock and main-context budget.

### Trade-offs

- Accepted **larger-than-ideal commit (5500+ LoC)** for Phase 1+2 in exchange for parallel execution speed. Mitigated by structured commit message that lists each package's changes.
- Accepted **work-packages.yaml file-path drift** (review-findings.schema.json actually lives at openspec/schemas/, not skills/parallel-infrastructure/schemas/). Sub-agent found the real file and edited it; commit message documents the deviation.
- Accepted **simplify skill created from scratch** (didn't exist on disk despite being labeled a "tail-block pilot"). Sub-agent created a 98-line stub with Chesterton's Fence + Rule of 500 + pattern catalog + tail block — covers the spec scenario.

### Open Questions

- [ ] `related:` graph could be visualized — the `related:` frontmatter key is now populated across 18 skills but no rendering tool exists yet. Deferred per design D4.
- [ ] CI lint rule for tail-block enforcement — content invariants in `skills/tests/_shared/skill_invariants.py` cover the convention at test time, but a pre-commit hook or CI lint that checks every `user_invocable: true` SKILL.md would catch violations earlier. Deferred per design D2.
- [ ] Pre-existing `tests/merge-pull-requests/test_classify.py` collection error (ImportError on `check_clean_worktree` from `shared`). Worked around with `--ignore`. Not in scope of this change but worth filing as a follow-up.

### Context

7 sub-agents dispatched in parallel; all 7 completed successfully. Total output: 10 new SKILL.md files (~3500 LoC) + 8 ADAPT-target edits (~600 LoC of additions across existing skills) + schema extension + CLAUDE.md subsection + 19 new test files (~340 test cases). All 353 tests pass with `--import-mode=importlib`; 8 skip cleanly when rsync is unavailable. `openspec validate --strict` passes. `install.sh` integration dry-run produces 104 symlinks and zero `related:` warnings (all cross-references resolve). Branch `claude/review-external-skills-1Cuh7` ready for PR.
