# Design: add-engineering-methodology-skills

## Architectural Overview

This change adds a **horizontal methodology layer** to a previously vertical (lifecycle-oriented) skills system. The new layer is composed of:

1. Ten content-only skills under `skills/<name>/` that codify per-topic methodology (TDD, debugging, context engineering, etc.).
2. A shared `skills/references/` library that hosts checklists and templates cited by multiple skills, eliminating duplication.
3. A new optional frontmatter key `related:` for cross-skill discovery, following the existing `requires:` precedent.
4. A uniform tail-block convention (Common Rationalizations / Red Flags / Verification) on every user-invocable skill, enforced by content-invariant tests.
5. Adaptations to eight existing local skills that fold in the most reusable patterns from external skills, edited in a single pass that also adds the tail block.

The change does not introduce any runtime dependencies, network calls, schema migrations, or coordinator capability changes. It is, in a meaningful sense, a **documentation and convention change with tests**.

## Key Decisions

### D1 — Extend `skill-workflow` capability rather than create `engineering-methodology`

**Decision:** All new requirements land under the existing `skill-workflow` capability spec.

**Rationale:** The new skills are part of our skill ecosystem; their addition, the references library, and the tail-block convention are all workflow-level decisions. Creating a sibling capability would split related requirements across two spec files and complicate the archive at change-completion time. `skill-workflow` is already the home for skill conventions (e.g., `iterate-on-implementation`).

**Trade-off:** `skill-workflow/spec.md` grows by ~7 requirements (~250 lines). Acceptable — capabilities can be split later if the file grows unmanageable.

**Rejected alternative:** A new `engineering-methodology` capability. Rejected because it would orphan the references library and tail-block convention (which are not methodology-specific) into a third capability or back into `skill-workflow`, splitting the change unnaturally.

### D2 — Tail-block enforcement is content invariants now, CI lint deferred

**Decision:** Tail-block presence is verified by `assert_tail_block_present` in `skills/tests/_shared/conftest.py`, invoked from each user-invocable skill's `test_skill_md.py`. No CI lint rule, no pre-commit hook.

**Rationale:** Tests run in the existing pytest suite (already in CI via `make test` / `uv run pytest`). Adding a new lint pipeline doubles the enforcement surface. If a user-invocable skill is shipped without the tail block, the test suite fails — sufficient for this change.

**Trade-off:** A future contributor adding a new user-invocable skill must remember to also add `skills/tests/<new-skill>/test_skill_md.py`. Mitigation: the canonical tail-block template at `skills/references/skill-tail-template.md` includes a one-liner pointing to the test pattern.

**Deferred:** A pre-commit lint rule that scans every `user_invocable: true` SKILL.md for the three section headers. Pulled out into a follow-up if drift emerges.

### D3 — `references/` is a sibling library, not a skill

**Decision:** `skills/references/` is a top-level directory under `skills/`, alongside skill directories, but it does not contain a `SKILL.md` and is explicitly skipped by `install.sh`'s skill-discovery loop.

**Rationale:** The four checklist files (`security-checklist.md`, `performance-checklist.md`, `accessibility-checklist.md`, `testing-patterns.md`) plus the tail-block template are *resources*, not skills. They have no frontmatter, no triggers, no `user_invocable` semantics. Modeling them as a skill would require fake frontmatter and confuse the slash-command palette.

**Implementation:** `install.sh` adds an explicit branch: when iterating skill directories, if the directory name is `references` (or — more robustly — if it contains no `SKILL.md`), copy/rsync it as a flat directory rather than processing it as a skill.

**Trade-off:** Skills citing references must use a relative path (`references/security-checklist.md`) that resolves against the *parent* of the skill directory, not the skill itself. This is a minor cognitive load but matches how `install.sh` lays out the destination tree.

**Rejected alternative:** A "fake skill" with `user_invocable: false` and a stub SKILL.md that just lists the references. Rejected because it pollutes skill discovery with a non-skill.

### D4 — `related:` is advisory; `requires:` remains the only hard dependency

**Decision:** `related:` is a soft cross-reference key. A skill can declare `related: [test-driven-development]` to signal kinship without forcing the related skill to be installed before this one. `install.sh` warns on unknown targets but does not fail.

**Rationale:** The semantic of `requires:` is "this skill cannot function without that one" (e.g., `parallel-review-plan` requires `parallel-infrastructure`'s scripts). The semantic we need for graph rendering and discovery is "these are kindred topics," which is weaker. Conflating them by overloading `requires:` would force every methodology skill to declare hard deps on every other methodology skill, polluting the dependency graph.

**Trade-off:** Two similar keys. We mitigate by documenting them together in `docs/skills-workflow.md` and by validating both with the same install.sh subroutine.

**Rejected alternative:** A weighted dependency type (`requires-soft: [...]` or `requires: { hard: [...], soft: [...] }`). Rejected as over-engineering for what is currently an advisory metadata field.

### D5 — Per-skill `user_invocable` heuristic

**Decision:** A skill is `user_invocable: true` if (a) operators reasonably want to trigger it ad-hoc with a slash command, OR (b) it is also auto-loadable by orchestrators. A skill is `user_invocable: false` only if it is purely orchestrator-loaded and never directly executed by the operator.

This produces the 7 true / 3 false split documented in `proposal.md`. The three `false` skills (`context-engineering`, `source-driven-development`, `browser-testing-with-devtools`) share the property that they describe behaviors that orchestrators perform automatically rather than methodologies operators consciously invoke.

**Trade-off:** The line is not bright. `browser-testing-with-devtools` is borderline: an operator debugging UI bugs might want `/browser-testing` ad-hoc. We prefer a `false` default and let the operator override at Gate 1 or 2 if needed. Reversing later is a one-line frontmatter edit.

### D6 — Eight ADAPT edits combined with tail-block addition

**Decision:** When editing each of the 8 ADAPT-target skills to fold in extracted patterns, the tail block is added in the same edit pass.

**Rationale:** Each file is touched exactly once. Two separate edits would require two reviews, two commits, and risk merge conflicts between them. The same agent owns both edits per package.

**Trade-off:** Larger per-file diff. Mitigated by clear commit messages (`feat(simplify): add Chesterton's Fence + tail block`) that delineate the two changes.

### D7 — Tasks ordered TDD-first (test before implementation)

**Decision:** Within each phase, test tasks for a given skill precede the implementation task that they verify. Test tasks reference the spec scenario IDs they encode.

**Rationale:** Matches the pre-existing convention from `plan-feature/SKILL.md` Step 6 ("list test tasks before implementation tasks"). Forces RED before GREEN. For methodology skills (which are content), the "test" is the content-invariant assertion (frontmatter parses, tail block present, references resolve) — running it before the skill exists naturally fails RED, then passes GREEN once the skill is written.

### D8 — Cluster decomposition for parallel phases

**Decision:** Phase 1 (10 new skills) splits into 4 work packages by topic cluster:
- WP1.1 (testing/quality): `test-driven-development`, `debugging-and-error-recovery`, `browser-testing-with-devtools`
- WP1.2 (knowledge): `context-engineering`, `source-driven-development`
- WP1.3 (engineering practices): `api-and-interface-design`, `frontend-ui-engineering`, `performance-optimization`
- WP1.4 (lifecycle/governance): `deprecation-and-migration`, `documentation-and-adrs`

Phase 2 (8 ADAPT + 3 pilots) splits into 3 work packages by target-skill cluster:
- WP2.1 (lifecycle skills): `implement-feature`, `plan-feature`, `simplify` (also pilot)
- WP2.2 (review skills): `parallel-review-plan`, `parallel-review-implementation`, `security-review`, `bug-scrub` (pilot), `tech-debt-analysis` (pilot)
- WP2.3 (sync-points and meta): `cleanup-feature`, `merge-pull-requests`, `explore-feature` + `CLAUDE.md` light pull

**Rationale:** Each cluster's skills share enough thematic context that a single agent loading them all into context works well. Cluster boundaries align with our existing skill categories.

**Lock pressure:** Each Phase 1 cluster writes only to its own skill subdirs and to `skills/tests/<cluster-skills>/`. Each Phase 2 cluster writes to its skills' subdirs. No cluster overlaps with another. The shared `skills/pyproject.toml` and `skills/install.sh` are touched only in Phase 0 and Phase 3 (sequential phases) — no parallel writes to either.

## Cross-Cutting Patterns

### Lock-key namespaces

Each Phase 1 and Phase 2 work package locks:
- `file:skills/<skill-name>/**` for every skill it owns (write_allow scope)
- `file:skills/tests/<skill-name>/**` for tests
- Read-only access to `skills/references/**`

Phase 0 (sequential) locks `file:skills/install.sh`, `file:skills/pyproject.toml`, `file:skills/references/**`, `file:docs/skills-workflow.md`.

Phase 3 (sequential) re-locks the Phase 0 files for finalization plus runs read-only validation across all skill subdirs.

### Verification tier per package

- Phase 0 (`wp-scaffold`): **Tier A** — full validation (install.sh dry-run, schema validation, references library structure)
- Phase 1 packages (`wp-skills-*`): **Tier B** — pytest invariants pass for each skill in the cluster, plus `openspec validate`
- Phase 2 packages (`wp-adapt-*`): **Tier B** — pytest invariants pass plus diff review against extracted patterns checklist
- Phase 3 (`wp-integration`): **Tier A** — full pytest suite, full install.sh rsync, openspec validate --strict

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `conditional-worktree-generation` (21/23) merges first and changes a file we depend on | Medium | Low (we don't touch worktree.py) | None needed; rebase-only |
| Stylistic drift across the 21 tail-block additions | Low | Medium | Phase 0 ships canonical template; Phase 2 reviewer checks template adherence |
| `references/` rsync logic in install.sh introduces a bug for existing skills | Low | High | Phase 0 task includes adding install.sh test coverage for the rsync branch before edits |
| New methodology skill descriptions clash with existing skill triggers | Low | Low | Phase 1 task includes a trigger uniqueness check vs. existing triggers |
| `related:` graph contains cycles | Low | Low | Validation is advisory; cycles don't break runtime; documented as an enhancement opportunity |
| Test invariants too strict, fail on legitimate edge cases | Medium | Low | Each invariant has an explicit minimum threshold (≥3 rationalizations, ≥3 red flags, ≥3 verification items) |

## Out of Scope (Reaffirmed)

- Standalone `spec-driven-development` skill (OpenSpec covers it).
- Standalone `ci-cd-and-automation` skill (overlaps `validate-feature`).
- CI lint rule for tail block (deferred to follow-up; tests cover content).
- Skills graph rendering / visualization tool (deferred; data is captured via `related:`).
- Backfilling tail block on remaining ~17 skills not in scope (`autopilot`, `merge-pull-requests` itself, etc., except where they appear as ADAPT targets).
