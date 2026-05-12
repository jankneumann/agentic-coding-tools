# Session Log - add-prototyping-stage

---

## Phase: Plan (2026-04-16)

**Agent**: claude-opus-4-6 | **Session**: claude/add-prototyping-stage-feYSr

### Decisions

1. Convergence via iterate-on-plan (D1). Extend existing /iterate-on-plan with a --prototype-context flag rather than creating a new /synthesize-prototypes skill. Reuses refinement loop, finding taxonomy, and commit conventions. User-chosen at Gate 1.
2. Default 3 variants (D2). Selected over N=2 (risks false dichotomy) and N=4 (Franken-merge risk). Configurable via --variants. User-chosen.
3. Best-effort vendor diversity with fallback (D3). Prefer distinct vendors when at least N reachable; fall back to single-vendor with temperature and seed variation. Never hard-block. User-chosen. Required because current harness sessions often have only one vendor reachable.
4. Branch retention until cleanup-feature (D4). Prototype branches persist through feature lifecycle for auditability. /cleanup-feature gets a new prototype-cleanup step. User-chosen.
5. Angle prompts, not personas (D5). Variants differentiated by design values (simplest, extensible, pragmatic) rather than fixed roles. Avoids caricature outputs.
6. Scoring via existing validation phases (D6). Reuse /validate-feature --phase smoke,spec. No new scoring infrastructure. Heavy phases (deploy, e2e, security) skipped as inappropriate for incomplete skeletons.
7. Pick-and-choose not pick-one-winner (D7). Human feedback selects elements per-aspect (data_model, api, tests, layout) across variants.
8. Opt-in gating with advisory signal (D8). /iterate-on-plan emits workflow.prototype-recommended when clarity plus feasibility high-criticality findings are at least 3. Never auto-triggers.

### Alternatives Considered

- Dedicated /synthesize-prototypes skill: rejected because it duplicates iterate-on-plan machinery; two skills drift apart over time.
- Inline synthesis in /prototype-feature: rejected because it mixes generation and refinement concerns; cannot re-synthesize after human feedback without re-dispatching.
- Strict vendor diversity (>=2 required): rejected because it is unrunnable in solo-vendor sessions.
- Single-vendor only: rejected because it loses the genuine multi-vendor benefit when multiple vendors are available.
- Immediate branch deletion after synthesis: rejected because it loses audit trail during the pattern early lifetime.

### Trade-offs

- Accepted 3x baseline cost per change (when stage runs) for divergent exploration benefit. Opt-in gating concentrates spend where it is valuable.
- Accepted N extra branches per change (until cleanup) for variant provenance. Revisit retention once pattern is mature.
- Accepted broader surface area for /iterate-on-plan (it now handles convergence mode) for single commit history across refinement paths.
- Accepted fallback to single-vendor with prompt-steering for operational runnability in solo-vendor environments, at the cost of weaker cross-vendor architectural divergence.

### Open Questions

- [ ] Should default angles be tuneable per-project via openspec/project.md? (Deferred to post-adoption observation.)
- [ ] What is the minimum proposal size below which prototyping adds no value? (Deferred; expect pattern to emerge from usage.)
- [ ] Should /prototype-feature support re-dispatching a single variant (--only v2) after human feedback? (Deferred; add if usage demands.)

### Context

Motivated by Uber AI prototyping blog post (three themes: greater exploration, faster alignment, unblocked execution). Our workflow already runs divergence on the review side (/parallel-review-*) but collapses to one approach on the generation side. This change adds divergent generation and synthesis between /plan-feature and /implement-feature, with convergence handled by an extended /iterate-on-plan. Tier selected: local-parallel (5+ architectural boundaries touched). Session operates on designated branch claude/add-prototyping-stage-feYSr in the shared checkout (no worktree setup because the session is configured with this branch as the working directory).

---

## Phase: Cleanup (2026-05-04)

**Agent**: claude-opus-4-7 | **Session**: N/A

### Decisions
1. **Rebase-merge over squash** — Per CLAUDE.md hybrid-merge policy, openspec PRs default to rebase. The 9 commits each encode a complete TDD cycle for one work-package phase (tests + implementation + runtime sync). Preserving them keeps git blame/bisect useful for future agents touching the prototype-feature surface.
2. **Override validation gate (--force)** — No validation-report.md exists. The change adds skill definitions, JSON schemas, docs, and Python helpers; no service deploys, no Docker runtime, no E2E surface. Smoke/security/E2E phases are categorically inapplicable. Established precedent: every prior skill-only archive (add-decision-index, phase-record-compaction, add-per-phase-archetype-resolution) used --force on the same gate.
3. **No tasks.md migration commit needed** — All 38 task checkboxes were already flipped on the feature branch by the per-phase implementation commits. tasks.md on main only LOOKS unchecked because the PR had not been merged yet.
4. **File coordination-bridge capability gap as follow-up** — validate-decision-index CI check fails because the previously-archived 2026-05-03-add-per-phase-archetype-resolution change references a coordination-bridge capability that was never registered under openspec/specs/. This pre-dates the prototyping branch and will fail every subsequent PR until fixed.

### Alternatives Considered
- Squash-merge into a single 'add /prototype-feature stage' commit: rejected because Loses per-phase TDD history; harder to bisect any future regression to a single work-package
- Block merge until validate-decision-index passes: rejected because The failure is pre-existing (introduced two merges ago) and unrelated to this branch content
- Land coordination-bridge capability spec inside this PR to fix CI: rejected because Scope creep — this PR adds the prototyping stage; the capability gap is its own concern

### Trade-offs
- Accepted Carry one failing CI check (validate-decision-index) into the merge over Blocking on pre-existing tech-debt with no relationship to this branch because Filed follow-up issue keeps the gap visible; merging unblocks the prototyping feature for use
- Accepted No deploy/smoke/security validation evidence over Synthetic validation report claiming phases passed when no deployable surface exists because --force is the documented escape hatch for skill-only changes; precedent established by prior archives

### Open Questions
- [ ] Should validate-decision-index warn rather than fail when an archived change references an unregistered capability?
- [ ] Should the validation gate auto-detect skill-only changes and skip deploy/smoke/security phases without --force?

### Completed Work
- Merged PR #138 via rebase-merge (preserves 9-commit history)
- Marked tasks.md complete (no-op — already complete on feature branch)
- Archived openspec/changes/add-prototyping-stage to openspec/changes/archive/
- Filed follow-up issue for coordination-bridge capability registration gap
- Cleaned up implementation + cleanup worktrees
- Pruned remote tracking branches

### Context
Merged PR #138 with rebase to preserve the 9-commit history (one per work-package phase). Validation gate overridden via --force because this is a skill-definition change with no Docker/E2E surface. Pre-existing validate-decision-index CI failure (coordination-bridge capability not registered) filed as a separate follow-up issue rather than blocking the merge.

