---

## Phase: Plan (2026-04-06)

**Agent**: codex | **Session**: N/A

### Decisions
1. **Extend existing workflow instead of adding a separate factory mode** — the repository already has the right building blocks in gen-eval, OpenSpec workflow artifacts, validation phases, and feature discovery.
2. **Treat public vs holdout as workflow-visible metadata** — visibility must be enforceable at validation and iteration gates, not just implied by directory names.
3. **Add process-analysis as a new optional artifact** — archive mining needs normalized process outcomes, not only prose and git history.

### Alternatives Considered
- **Standalone factory subsystem**: rejected because it would duplicate the existing workflow and confuse external adopters.
- **Docs-only guidance**: rejected because the goal is to productize software-factory capabilities for other projects, not just describe them.

### Trade-offs
- Accepted a larger, cross-cutting proposal over a smaller point feature because the user asked for capabilities that only make sense when scenario packs, DTUs, rework routing, and archive mining work together.
- Accepted a new capability spec (`software-factory-tooling`) in addition to delta specs on existing capabilities because archive intelligence is broader than a single gen-eval or workflow tweak.

### Open Questions
- [x] Whether holdout visibility needs an additional filesystem policy beyond manifest metadata → Resolved in iteration 1
- [x] Whether `process-analysis` should be generated in validation, cleanup, or both → Resolved in iteration 1
- [x] How strict the first DTU fidelity threshold should be before holdout promotion is allowed → Resolved in iteration 1

### Context
The planning goal was to convert a software-factory roadmap into a concrete OpenSpec change that can be reviewed and implemented in this repository. The resulting plan focuses on external-project value first, while also defining a dogfooding path for the repository’s own gen-eval and workflow assets.

---

## Phase: Plan Iteration 1 (2026-04-06)

**Agent**: claude-code | **Session**: N/A

### Decisions
1. **Holdout enforcement uses directory structure + manifest + skill filtering** — three reinforcing layers without filesystem-level exclusion policies. Directory split makes intent visible; manifest confirms metadata; skill logic enforces at runtime.
2. **Process-analysis generated in /validate-feature only** — single generation point with all convergence data. Cleanup and merge gates consume read-only.
3. **DTU bootstrap is docs-only; live probes optional** — keeps bootstrap fast and offline-capable. Low-fidelity DTUs eligible for public scenarios only.
4. **Split task 3.4 into 3.4a/3.4b/3.4c** — one subtask per consuming skill (iterate-on-implementation, cleanup-feature, merge-pull-requests) for single-commit granularity.
5. **Rescoped task 6.1** — cross-phase integration smoke test only, not re-running all phase test suites.
6. **Fixed task 1.3 spec refs** — removed incorrect `software-factory-tooling.3.1-3.2` (External Project Bootstrap), task correctly maps to `gen-eval-framework.4.1-4.3` (Multi-Source Scenario Bootstrap).

### Alternatives Considered
- Manifest-only holdout enforcement (no directory split): rejected because holdout status would be invisible in the filesystem.
- Process-analysis in both validate + cleanup: rejected because split generation adds complexity for marginal benefit.
- Required live probes for DTU bootstrap: rejected because it blocks bootstrap on live system availability.

### Trade-offs
- Accepted directory-based organization despite promotion friction (file moves required) because immediate visibility outweighs the minor overhead.
- Accepted single-point process-analysis generation despite losing incremental cleanup data because simplicity is more important for the first implementation.

### Open Questions
- None remaining — all 3 original open questions resolved.

### Context
10 findings identified (3 high, 6 medium, 1 low). All high and medium findings addressed: resolved 3 design open questions with user input, fixed task-to-spec ref mismatch, split oversized task, rescoped integration task, added failure scenarios for bootstrap flows, added success-path scenario for rework report, added incremental indexing requirement, improved testability of dogfood scenario, updated contracts README.
