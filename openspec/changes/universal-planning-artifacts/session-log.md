# Session Log: universal-planning-artifacts

---

## Phase: Plan (2026-04-03)

**Agent**: claude-opus-4-6 | **Session**: N/A

### Decisions
1. **Universal artifact generation** — Always generate contracts and work-packages during planning, even for sequential tier. Sequential features get a single `wp-main` package covering full scope.
2. **Full-fidelity contracts at all tiers** — No lightweight stubs; same OpenAPI/DB/event schema artifacts regardless of tier.
3. **Whole-branch review fallback** — When work-packages are missing (legacy PRs, external contributions), treat entire diff as single review unit rather than skipping or auto-generating packages.
4. **Always consume contracts in implementation** — implement-feature reads contracts at all tiers for interface validation, not just parallel+.

### Alternatives Considered
- Lazy generation (on-demand in consuming skills): rejected because duplicated logic, late-generated artifacts lack planning context, race conditions
- Tier-aware optional consumption (with/without code paths): rejected because ongoing maintenance burden across 4+ skills, doesn't solve constraint value problem
- Lightweight stubs for sequential: rejected in favor of full-fidelity for consistency
- Skip structured review when packages missing: rejected because it loses review coverage for legacy PRs
- Auto-generate packages from diff at review time: rejected because inferred packages lack planning intent

### Trade-offs
- Accepted slightly longer planning time for sequential features over the risk of missing constraint validation
- Accepted a degenerate `wp-main` package (no parallelization benefit) over having no work-package at all, to unify the artifact format

### Open Questions
- [ ] The `validate_work_packages.py` script expects `package_id` but existing work-packages use `id` — schema/validator mismatch to resolve separately

### Context
Planning session to make contracts and work-packages universal across all execution tiers. The goal is to ensure that later stages (review, implementation, validation) can always rely on these artifacts existing, eliminating conditional paths and enabling richer reviews for all PRs regardless of how they were planned.
