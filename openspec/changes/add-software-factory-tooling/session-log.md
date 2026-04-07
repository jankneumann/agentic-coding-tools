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
- [ ] Whether holdout visibility needs an additional filesystem policy beyond manifest metadata
- [ ] Whether `process-analysis` should be generated in validation, cleanup, or both
- [ ] How strict the first DTU fidelity threshold should be before holdout promotion is allowed

### Context
The planning goal was to convert a software-factory roadmap into a concrete OpenSpec change that can be reviewed and implemented in this repository. The resulting plan focuses on external-project value first, while also defining a dogfooding path for the repository’s own gen-eval and workflow assets.
