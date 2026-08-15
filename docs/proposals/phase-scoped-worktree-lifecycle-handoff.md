# Handoff: Phase-Scoped Worktree Lifecycle and Proposal-Only PRs

**Status:** Agreed direction; ready for OpenSpec planning and implementation  
**Date:** 2026-08-15  
**Suggested change ID:** `phase-scoped-worktree-lifecycle`  
**Recommended next command:**

```text
/autopilot "Implement phase-scoped worktree leases and proposal-only PR handling per docs/proposals/phase-scoped-worktree-lifecycle-handoff.md"
```

## Objective

Make local worktrees disposable execution environments rather than permanent
handoff state. A standalone planning session should be able to produce a
proposal-only PR, release all local activity, receive local multi-vendor review
at merge time, and later start implementation from the reviewed proposal on
`main`. Autopilot remains the deliberate exception: it may retain one continuous
worktree lease across planning, implementation, review, and validation, but must
release that lease before presenting the final human merge gate.

This should match the useful property of Claude Code web sessions: the durable
handoff is the pushed branch and PR, while the cloud container is disposable.

## Triggering Problem

The current lifecycle pins the parent feature worktree at the end of
`plan-feature`, when active planning has stopped. The Boolean pin never expires,
and the sync-point active-agent guard treats any pin as active regardless of its
heartbeat. This creates a deadlock:

1. `plan-feature` commits, pushes, and permanently pins the worktree.
2. A proposal or implementation PR waits for human review.
3. `merge-pull-requests` refuses to start because the idle worktree is pinned.
4. The cleanup that could remove the worktree occurs only after merge.

There are additional gaps:

- `implement-feature` documents unpinning only in its coordinated-tier teardown,
  although every tier can inherit the planning pin.
- Proposal-only PRs never enter implementation teardown.
- Interrupted runs can miss the final unpin command.
- Merge-driven `cleanup-feature --defer-commit` intentionally skips Step 8.5
  worktree removal.
- The registry's `pinned` flag conflates retention (protect from GC) with
  activity (block sync-point writers).
- All `openspec/*` PRs are currently treated as completed changes, so a merged
  proposal-only PR risks premature validation and archival.

## Agreed Decisions

### D1. Protection is phase-scoped

Standalone phases acquire protection when work begins and release it after their
output is durably pushed. A workflow must not return `awaiting review` while it
still owns an active local worktree lease.

The durable boundary is a remote branch and PR, not a local worktree.

### D2. Standalone planning produces a proposal-only PR

A directly invoked planning workflow should:

1. Create or adopt a managed planning worktree.
2. Acquire a phase-scoped lease and maintain a heartbeat.
3. Produce and validate proposal, design, specs, tasks, contracts, and work
   packages.
4. Commit, push, and open a proposal-only PR.
5. Release the lease and tear down the local planning worktree in a guaranteed
   completion/failure path.

Use a distinct proposal branch such as
`openspec/<change-id>--proposal`. Implementation later starts from reviewed
`main` on the normal `openspec/<change-id>` branch.

### D3. Implementation and validation own their worktrees independently

Standalone `implement-feature`, `iterate-on-implementation`, and
`validate-feature` should each create or adopt a phase-specific managed worktree,
acquire a lease, push their commits or reports to the implementation PR branch,
and release/teardown at the phase boundary. A later phase may recreate its
worktree from the remote branch.

This rule applies to sequential, local-parallel, and coordinated tiers. Package
worktrees remain isolated children and are torn down after integration or on
failure.

### D4. Autopilot owns one continuous lease

Autopilot may acquire an owner-scoped lease before PLAN and renew it through:

```text
PLAN -> PLAN_ITERATE -> PLAN_REVIEW -> IMPLEMENT -> IMPL_ITERATE
     -> IMPL_REVIEW -> VALIDATE -> optional VAL_REVIEW -> SUBMIT_PR
```

Nested phase skills must not release a lease owned by the parent autopilot run.
Autopilot releases and tears down before entering DONE and presenting the final
human merge gate. On failure or escalation it releases activity ownership after
persisting a recoverable checkpoint; preserving files must not leave a permanent
sync-point blocker.

An explicit continuous/manual mode may use the same mechanism, but it must be an
opt-in lifecycle mode rather than the default for direct skill invocation.

### D5. Separate activity from retention

Replace the semantic overload of `pinned` with two concepts:

- **Activity lease:** owner-scoped, heartbeat-renewed, and expiring. It blocks
  sync-point operations while current.
- **Retention:** protects an idle worktree from garbage collection. It does not
  by itself mean an agent is writing and therefore does not block sync points.

Suggested registry fields:

```json
{
  "schema_version": 2,
  "retained": false,
  "retention_reason": null,
  "activity_lease": {
    "owner": "autopilot:<run-id>",
    "phase": "IMPLEMENT",
    "reason": "continuous-run",
    "acquired_at": "<timestamp>",
    "last_heartbeat": "<timestamp>",
    "expires_at": "<timestamp>"
  }
}
```

Exact field shape may change during OpenSpec design, but owner identity, expiry,
and the activity/retention separation are required.

### D6. Lease release must be crash-tolerant

Do not rely solely on a final Markdown instruction that an interrupted agent may
never execute. Use all of the following:

- owner-scoped acquire/renew/release operations;
- bounded expiry renewed by heartbeat;
- `finally`-style release in executable orchestration paths;
- session-end best-effort release when the owning identity is available;
- idempotent release and teardown;
- operator-visible inspection and recovery commands.

The existing `pin`/`unpin` commands can remain compatibility aliases during
migration, but ordinary workflow skills should move to lease operations.

### D7. OpenSpec PRs are classified by delivery stage

`merge-pull-requests` must distinguish:

| PR kind | Meaning | Merge-time behavior |
|---|---|---|
| `proposal` | Planning artifacts only; implementation has not begun | Review the plan, validate OpenSpec artifacts, merge without archive |
| `implementation` | Implements a proposal already present on `main` | Review proposal context plus code, run implementation validation, archive after merge |
| `mixed` | Proposal and implementation delivered together, normally by autopilot | Review both plan and code, run full validation, archive after merge |

Classification should primarily use the changed-file set and OpenSpec artifact
state, not branch naming alone. Branch naming and PR metadata may provide
additional evidence. Ambiguous cases must be reported rather than silently
treated as completed implementations.

### D8. Claude-authored PRs receive independent local vendor review

Preserve author identity separately from OpenSpec origin. For Claude-authored
PRs:

- Proposal PR: Codex, Grok, and Pi review the proposal, design, specifications,
  contracts, tasks, and work packages.
- Implementation PR: Codex, Grok, and Pi review both the governing OpenSpec
  artifacts and the implementation diff.
- Mixed/autopilot PR: Codex, Grok, and Pi review the complete plan and
  implementation.

Review consensus and blocking dispositions remain part of the merge decision.
Unavailable vendors are reported explicitly; they are not silently replaced by
a same-author review.

### D9. Proposal merges do not complete the OpenSpec change

For `proposal` PRs, merge-time processing must skip:

- deploy, smoke, security, and e2e implementation validation;
- holdout/rework gates that require an implementation;
- `cleanup-feature` post-merge archival;
- deletion of the active OpenSpec change directory.

It should still run strict OpenSpec validation and the once-per-pass main-context
convergence required after any merge. The merged proposal remains at
`openspec/changes/<change-id>/` on `main`, ready for implementation.

Implementation and mixed PRs retain the existing validation, cleanup, archive,
and convergence behavior.

## Target Workflows

### Standalone proposal workflow

```text
plan-feature starts
  -> create proposal worktree
  -> acquire plan lease + heartbeat
  -> generate/validate artifacts
  -> commit + push proposal branch
  -> create proposal-only PR
  -> release lease + teardown
  -> local merge triage dispatches Codex/Grok/Pi
  -> merge proposal
  -> skip archive; converge main context
```

### Standalone implementation workflow

```text
reviewed proposal is present on main
  -> create implementation branch/worktree from main
  -> acquire implementation lease + heartbeat
  -> implement + test + push implementation PR
  -> release implementation lease + teardown
  -> iteration/validation recreate isolated worktrees as needed
  -> each phase pushes, releases, and tears down
  -> merge triage reviews plan + code
  -> merge -> cleanup/archive -> context convergence
```

### Autopilot workflow

```text
autopilot starts
  -> create feature worktree
  -> acquire autopilot:<run-id> continuous lease
  -> plan + internal plan convergence
  -> implement + internal implementation convergence
  -> validate + optional validation review
  -> submit combined PR
  -> release continuous lease + teardown
  -> human merge gate
```

## Implementation Scope

The OpenSpec plan should inspect and, where necessary, change:

- `skills/worktree/scripts/worktree.py`
  - registry schema migration;
  - lease acquire/renew/release/status commands;
  - compatibility behavior for `pin`/`unpin`;
  - idempotent teardown and expired-lease handling.
- `skills/shared/active_agents.py`
  - block on live activity leases/heartbeats;
  - do not treat retention alone as active;
  - preserve safe handling of corrupt or legacy registries.
- `skills/plan-feature/SKILL.md`
  - direct versus continuous lifecycle mode;
  - proposal-only PR creation;
  - guaranteed all-tier release/teardown.
- `skills/implement-feature/SKILL.md`
  - phase lease at entry;
  - all-tier completion/failure teardown;
  - nested ownership under autopilot.
- `skills/iterate-on-plan/SKILL.md`,
  `skills/iterate-on-implementation/SKILL.md`, and
  `skills/validate-feature/SKILL.md`
  - phase-specific lease ownership and teardown.
- `skills/autopilot/SKILL.md` and `skills/autopilot/scripts/`
  - continuous owner lease across write-capable phases;
  - release before DONE/human merge;
  - resume and escalation behavior.
- `skills/merge-pull-requests/scripts/discover_prs.py`
  - PR-kind and author-vendor classification.
- `skills/merge-pull-requests/scripts/vendor_review.py` and merge workflow
  - proposal-specific review context;
  - Codex/Grok/Pi selection for Claude-authored PRs;
  - validation and cleanup routing by PR kind.
- `skills/merge-pull-requests/scripts/post_merge_cleanup.py`
  - exclude proposal-only merges.
- session bootstrap/end hooks
  - best-effort owner-scoped lease release.
- tests under `skills/tests/<skill-name>/` and shared worktree tests.
- canonical docs and installed runtime mirrors through `skills/install.sh`.

Inspect canonical `skills/` first and regenerate `.agents/skills/` and other
runtime mirrors; do not hand-maintain divergent copies.

## Suggested Work Packages

### WP1 — Registry and lease contract

- Define schema v2 and backward-compatible reads.
- Implement owner-scoped acquire, renew, release, expiry, and status.
- Separate retention from activity in GC and active-agent checks.
- Add deterministic time-based unit tests.

### WP2 — Phase lifecycle integration

- Update plan, implement, iteration, and validation skills.
- Ensure every tier has symmetric entry and exit behavior.
- Add direct versus continuous lifecycle mode.
- Add crash-safe/backstop release hooks.

### WP3 — Proposal-only PR orchestration

- Add proposal PR creation and metadata.
- Add `proposal|implementation|mixed` classification.
- Preserve author-vendor identity.
- Route reviews, validation, and cleanup based on PR kind.

### WP4 — Autopilot continuous ownership

- Acquire one run-owned lease before planning.
- Renew it across write-capable phase transitions and resumes.
- Prevent nested skills from releasing the parent lease.
- Release on DONE, failure, or escalation after checkpoint durability.

### WP5 — Migration, documentation, and end-to-end verification

- Document operator inspection/recovery.
- Sync runtime skill mirrors.
- Test standalone proposal, standalone implementation, continuous autopilot,
  interrupted execution, and proposal merge behavior.

WP1 can proceed independently of the PR classifier design. WP2 and WP4 depend on
WP1. WP3 depends on the workflow metadata decisions but can largely proceed in
parallel with WP2. WP5 integrates all packages.

## Backward Compatibility and Migration

- Continue reading registry schema v1.
- Interpret legacy `pinned=true` as retention for GC, not proof of current
  activity; heartbeat freshness remains the activity signal during migration.
- Provide a read-only migration/inspection report before rewriting registry
  entries.
- Keep `pin`/`unpin` available initially, with documented compatibility
  semantics and a deprecation path if lease commands replace them.
- Do not delete dirty worktrees or unmerged branches automatically.
- Do not force past sync-point races.
- Existing implementation/mixed OpenSpec PRs must retain their current cleanup
  and archive behavior.

## Acceptance Criteria

1. A standalone planning run that creates a proposal PR leaves no active or
   permanently pinned local worktree.
2. A proposal-only PR can pass the active-agent guard and enter merge triage
   without `--force`.
3. Merging a proposal-only PR leaves its OpenSpec change active on `main` and
   does not invoke `cleanup-feature` archival.
4. Claude-authored proposal-only PRs are reviewed by configured Codex, Grok,
   and Pi reviewers using planning artifacts only.
5. Claude-authored implementation/mixed PRs give those reviewers both planning
   context and the implementation diff.
6. Sequential, local-parallel, and coordinated implementation paths all release
   their phase-owned leases after pushed completion or failure.
7. Autopilot retains one owner-scoped lease through validation and releases it
   before the human merge gate.
8. A crashed process cannot leave an activity lease blocking sync points
   indefinitely; expiry clears it without deleting dirty work.
9. Retained-but-idle worktrees survive GC as configured but do not block
   sync-point operations.
10. Proposal, implementation, and mixed PR classification is covered by unit
    tests and ambiguous classification fails safe with an operator-visible
    warning.
11. Existing registry entries and existing implementation PRs remain readable
    and safely processable.
12. Canonical skills and installed mirrors pass the repository drift checks.

## Verification Scenarios

- **Direct proposal:** plan -> proposal PR -> local worktree absent -> proposal
  merge -> OpenSpec change still active.
- **Reviewed implementation:** merged proposal on main -> implementation PR ->
  validation updates -> full merge cleanup/archive.
- **Autopilot:** one lease owner remains stable across all write phases and is
  gone before DONE.
- **Crash:** terminate after lease acquisition; advance the clock past expiry;
  guard no longer blocks and dirty worktree remains untouched.
- **Retention:** retain an idle worktree past the GC threshold; GC preserves it,
  active-agent guard ignores it.
- **Legacy registry:** load v1 pinned and unpinned entries without data loss;
  report migration interpretation.
- **Vendor routing:** Claude proposal PR dispatches Codex/Grok/Pi with no code
  review prompt; Claude implementation PR dispatches all three with plan and
  diff context.
- **Ambiguity:** OpenSpec-only changes with implementation-like task state do
  not silently archive; triage reports the evidence and requests a decision.

## Explicit Non-Goals

- Automatically merging PRs without the existing human gate.
- Treating a retained worktree as an active writer.
- Archiving an OpenSpec change when only its proposal has merged.
- Requiring local worktree persistence as the handoff between standalone
  phases.
- Replacing vendor-review consensus or validation gates.
- Force-deleting dirty, unmerged, or ambiguously owned worktrees.

## Risks and Design Questions for the Planning Phase

The direction above is agreed; OpenSpec planning should settle these bounded
details before implementation:

- Lease duration and heartbeat renewal interval.
- Whether lease operations extend `worktree.py` directly or use a small shared
  lifecycle helper consumed by skills and scripts.
- Exact direct/continuous flag names and how nested skills receive the parent
  lease owner token.
- The strongest deterministic PR-kind classifier that remains compatible with
  legacy OpenSpec PRs.
- Whether proposal-only PR metadata belongs in the PR body, a label, a checked-in
  manifest, or a combination.
- How session-end hooks discover and release all leases owned by a terminated
  session without releasing another run's lease.
- Whether an expired activity lease should be retained in history for audit or
  compacted during GC.

## Next-Session Instructions

1. Read this handoff and the repository `AGENTS.md`.
2. Invoke autopilot with the recommended command at the top of this document.
3. During PLAN, verify the OpenSpec artifacts explicitly cover D1-D9 and all
   twelve acceptance criteria.
4. Require multi-vendor plan convergence before implementation.
5. Preserve the current dirty/untracked state in the shared checkout; perform
   mutations only in managed worktrees.
6. Stop at the final merge gate and use `merge-pull-requests` for external PR
   review and merge handling.
