# Session Log — conditional-worktree-generation

---

## Phase: Plan (2026-04-19)

**Agent**: claude_code (Opus 4.7) | **Session**: N/A (cloud harness)

### Decisions

1. Approach A chosen at Gate 1: in-place detection inside worktree.py, backed by a new `skills/shared/environment_profile.py` helper. Rationale: zero changes to SKILL.md call sites across plan-feature, implement-feature, cleanup-feature, autopilot, and the iterate-on-* skills; single source of truth; fully reversible via the AGENT_EXECUTION_ENV env var.
2. Detection precedence: env var first, then coordinator query, then container heuristic, then default to the legacy behavior. Explicit operator intent always wins; coordinator report beats brittle heuristics; heuristic fires only as a last resort before falling back to the safe default.
3. All worktree mutating operations become silent success when isolation_provided is true. Read-only operations (list, status, resolve-branch) continue to function. Same shape for merge_worktrees.py: exit zero with a guidance line pointing to PR-based integration.
4. OPENSPEC_BRANCH_OVERRIDE remains orthogonal to the new signal. The branch override and the isolation signal compose but neither implies the other. This matches the Gate 1 answer from the operator.
5. Parallel work-packages in cloud mode map one container per package. Each container sees isolation_provided as true and short-circuits worktree setup; branch composition with the parent and agent-id suffix still applies so PR-based integration is unchanged.
6. Coordinated tier selected because every capability reported by check_coordinator.py came back true (lock, discover, queue_work, guardrails, memory, handoff, policy, audit, feature_registry, merge_queue). Six work-packages generated; parallel-zones validation confirms four of them can execute concurrently after the env-profile foundation package completes.

### Alternatives Considered

- Approach B (thin wrapper plus edits to call sites): rejected because it forces updates to five or more SKILL.md files; high risk of missing one and leaving a silent regression.
- Approach C (strategy protocol with IsolationProvider): rejected as premature. Only two providers exist near-term. The extracted environment_profile helper gives us a clean escalation point if a third provider appears later.
- Unanimous-vote detection across all three layers: rejected because it would fail in the common cloud case where only the env var is set.
- Hard-error in cloud mode: rejected because it breaks skills that invoke worktree.py unconditionally and defeats the zero-call-site-churn goal.
- Subsuming OPENSPEC_BRANCH_OVERRIDE into the new signal: rejected at Gate 1 because it couples two orthogonal concepts and breaks operators who set the override manually to work on a review branch.
- Hostname-pattern heuristic: rejected because local devs run in named containers that match arbitrary patterns and would trigger false positives.

### Trade-offs

- Accepted mixing environment detection into a module that was previously pure git plumbing, in exchange for zero call-site churn. Mitigated by extracting the detector into a separate module under skills/shared so the concern is physically separate even when imported together.
- Accepted an optional isolation_provided field on coordinator agent registration (a new coupling between skills/worktree and agent-coordinator/discovery) in exchange for a more reliable detection signal than container heuristics. Mitigated by making the coordinator layer non-blocking: 500ms timeout, falls through to heuristic on error.
- Accepted a required-by-schema OpenAPI stub under contracts/openapi/v1.yaml with empty paths to satisfy work-packages.schema.json. This is a skill-internal change with no HTTP surface. The stub is documented in contracts/README.md under sub-type evaluation.

### Open Questions

- [ ] Should the new operator documentation cover non-Claude cloud harnesses as well? Phase 6 writer should consult current harness documentation at implementation time before writing.
- [ ] Does the coordinator agent-registration MCP tool exist today, or only the HTTP endpoint? Phase 5 should confirm before shipping the optional isolation_provided field.
- [ ] Coordinator resource claims with a zero TTL were skipped this session because the bridge CLI does not expose acquire_lock. The implement-feature skill will re-acquire at dispatch time, so this is not blocking.

### Context

Planned under a cloud Claude Code session running on a harness-mandated branch — exactly the condition the feature is designed to handle. Concrete live evidence: the worktree.py setup command failed with a collision error against the existing checkout before artifact generation began, confirming the bug this change fixes. Planning proceeded in place on the cloud-harness checkout.
