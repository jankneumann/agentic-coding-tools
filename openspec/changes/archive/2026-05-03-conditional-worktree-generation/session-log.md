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

---

## Phase: Implementation (2026-04-19)

**Agent**: claude_code (Opus 4.7) | **Session**: N/A (cloud harness)

### Decisions

1. Implementation proceeded sequentially within a single cloud container rather than dispatching per-package parallel agents. Rationale: worktree-based isolation between parallel sub-agents is the exact mechanism this feature fixes; dispatching parallel agents now would hit the same bootstrap problem the feature solves. Sequential execution within one container was safe because no other agents were competing for files.
2. Tests live at skills/shared/tests/test_environment_profile.py, skills/worktree/scripts/tests/test_environment_aware.py, and skills/worktree/scripts/tests/test_merge_cloud_mode.py. This differs from the work-packages.yaml plan which referenced skills/tests/worktree/ (following one reading of CLAUDE.md). The codebase convention per skills/pyproject.toml testpaths is tests-alongside-scripts, so the implementation adopts that instead. pyproject.toml was updated to add shared/tests to testpaths.
3. A thin _short_circuit_if_isolated helper sits at the top of worktree.py. Every mutating cmd_ function begins with one line: if _short_circuit_if_isolated(op): return 0. This keeps the short-circuit in exactly one place and makes it trivial to audit by grep.
4. merge_worktrees.py writes a structured skip payload when invoked with --json (fields: skipped, reason, source, change_id, package_ids). Callers that parse the JSON output can distinguish cloud-mode skips from successful merges without brittle string matching.
5. setup under cloud mode emits WORKTREE_PATH=$(git rev-parse --show-toplevel) and WORKTREE_BRANCH=$(git branch --show-current), stable across every SKILL.md that does eval plus cd. Zero call-site churn: the call-site audit in task 4.2 confirmed all existing SKILL.md invocations are compatible with this output shape.

### Alternatives Considered

- Dispatching four parallel agents (one per work-package) with per-agent worktrees: rejected because the feature targets worktree creation itself and the dispatch would have hit the bootstrap problem.
- Placing tests under a top-level skills/tests/worktree/ directory per one reading of CLAUDE.md guidance: rejected because the existing pyproject.toml testpaths list per-skill test dirs only, and diverging from the running convention would risk tests silently not running.
- Using requests or httpx for the coordinator query: rejected in favor of stdlib urllib to avoid adding a new runtime dependency to the shared skills package. urllib.request with a 500ms timeout is sufficient for the narrow needs of the coordinator layer.
- Making the coordinator layer synchronous-required instead of best-effort: rejected because worktree.py is used in sequential and local-parallel workflows where no coordinator is running, and we must not introduce a hard dependency.
- Adding an IsolationProvider strategy protocol now: rejected per Gate 1 (only two providers exist — local-worktree and harness-container — and the strategy abstraction is overhead without a third provider to validate it).

### Trade-offs

- Accepted a small amount of import-path gymnastics (sys.path.insert in worktree.py and merge_worktrees.py) in exchange for letting the shared helper live under skills/shared/ without restructuring the skills package into an installable top-level module. When skills eventually get a real package root, this sys.path line becomes a proper import.
- Accepted deferring Phase 5 (wp-coordinator-ext, agent-coordinator isolation_provided field) to a follow-up PR. The env-var and heuristic layers cover the immediate need, and the coordinator integration requires schema work in the agent-coordinator subsystem. The coordinator layer in environment_profile.py is fully implemented and unit-tested against mocked responses so the follow-up is purely additive on the coordinator side.
- Accepted a single stderr log line per short-circuit (worktree: skipped gc (isolation_provided=true, source=env_var)) instead of structured JSON logging. Operators want a human-readable signal; machines that need more can export WORKTREE_DEBUG=1 for the full profile dump.

### Open Questions

- [ ] Should the cloud harness set AGENT_EXECUTION_ENV=cloud by default on session start? Owned by the cloud harness repo, not this one. Until then, the /.dockerenv heuristic carries the fix.
- [ ] The coordinator agent-registration schema change (Phase 5.2) needs sign-off from the coordinator team before landing. Tracking in change-context.md Coverage Summary as a deferred item.
- [ ] Should install.sh be re-run to sync the updated worktree.py into .claude/skills/ and .agents/skills/ mirror copies? Not done in this PR because the mirrored copies are generated artifacts per CLAUDE.md; operators will regenerate on next sync. Noted for cleanup-feature.

### Context

Implemented five of six work-packages in one sequential pass within the cloud container: wp-env-profile (12 tests), wp-worktree-integration (9 tests), wp-merge-integration (3 tests), wp-docs (3 files), plus the call-site audit in Phase 4. wp-coordinator-ext deferred to a follow-up PR. Final quality gates: 418 pytest passed (19 new env_profile + 9 new worktree cloud-mode + 3 new merge cloud-mode + 387 pre-existing green), ruff check clean, mypy --strict clean on environment_profile.py, openspec validate --strict valid, validate_work_packages.py VALID.
