# Enforce Local Worktree Mutation Boundary

## Why

Local CLI sessions do not provide filesystem isolation by default. When planning,
exploration, autopilot refinement, quick fixes, validation, or artifact generation
write directly in the shared checkout, main can accumulate unreviewed planning
artifacts, generated files, or partial fixes outside the PR flow. That conflicts
with the repo's intended model: the shared checkout is an orchestration surface,
and main should receive work only through reviewed PRs and explicit sync-point
skills.

The current documentation states part of this rule, but enforcement is uneven:
`AGENTS.md` still references `/iterate-on-plan` commits to local main,
`explore-feature` can write discovery artifacts without entering a worktree,
`autopilot` only treats IMPLEMENT as worktree-isolated, and `quick-task` explicitly
allows read-write execution without a worktree.

## What Changes

- Add a shared checkout mutation policy helper that classifies the current
  environment as isolated harness, local worktree, approved sync-point, or blocked
  shared checkout.
- Require mutating local CLI skill phases to enter or verify a managed worktree
  before writing project files, generated artifacts, commits, branches, or remote
  state.
- Update skill instructions for planning, exploration, autopilot, roadmap,
  validation, quick tasks, and artifact-producing workflows so the invariant is
  explicit and testable.
- Update operator documentation to remove local-main planning language and define
  the local CLI variant of the worktree rule.
- Add tests that fail when high-risk mutating skills omit the policy guard or
  advertise read-write shared-checkout behavior.

## Out of Scope

- Rewriting the full worktree lifecycle implementation.
- Changing cloud harness behavior when `EnvironmentProfile.detect()` reports
  `isolation_provided=true`.
- Changing merge strategy or PR review policy.
- Implementing every possible third-party tool sandbox. This change governs repo
  mutation boundaries for this codebase's skills and scripts.

## Approaches Considered

### Approach 1: Documentation-Only Clarification

Clarify `AGENTS.md`, `docs/cloud-vs-local-execution.md`, and affected SKILL.md
files without adding code-level guardrails.

Pros:
- Smallest implementation.
- Low risk of breaking existing workflows.

Cons:
- Does not prevent future regressions.
- Leaves scripts and generated skills dependent on humans remembering the rule.

Effort: S

### Approach 2: Shared Policy Helper with Targeted Skill Wiring (Recommended)

Add a shared checkout policy helper and CLI, then wire high-risk mutating skills
and tests to require that helper or an explicit worktree setup step.

Pros:
- Converts the invariant from prose into executable behavior.
- Reuses the existing `EnvironmentProfile.detect()` cloud/local distinction.
- Keeps changes scoped to skill infrastructure and documentation.
- Allows sync-point exceptions to remain explicit and auditable.

Cons:
- Requires touching multiple skill instructions.
- Needs careful tests to avoid over-constraining genuinely read-only skills.

Effort: M

### Approach 3: Git Hook Blocks All Shared Checkout Writes

Install pre-commit and pre-push hooks that reject commits or pushes from the
shared checkout unless the command is a known sync-point operation.

Pros:
- Strong protection against accidental commits.
- Catches manual mistakes outside skill execution.

Cons:
- Too late for artifact pollution; files can still be written before commit.
- Hard to distinguish intentional operator maintenance from skill misuse.
- Risky for contributors who are not using the agent workflow.

Effort: M

## Selected Approach

Proceed with Approach 2. The implementation should make policy enforcement
available as reusable code first, then update mutating skill instructions and
tests to consume it. Hook-level enforcement can be reconsidered later if the
shared helper and invariant tests still leave gaps.

## Impact

- Affected specs: `skill-workflow`, `worktree`
- Affected docs: `AGENTS.md`, `docs/cloud-vs-local-execution.md`, potentially
  `docs/lessons-learned.md`
- Affected skills: `explore-feature`, `iterate-on-plan`, `autopilot`,
  `autopilot-roadmap`, `plan-roadmap`, `quick-task`, `validate-feature`,
  `refresh-architecture`, and invariant tests for skill metadata
- New shared helper: `skills/shared/checkout_policy.py`
