---
name: implement-feature
description: "Implement approved OpenSpec proposal with tiered execution (coordinated / local-parallel / sequential)"
category: Git Workflow
tags: [openspec, implementation, pr, parallel, dag, work-packages]
triggers:
  - "implement feature"
  - "build feature"
  - "start implementation"
  - "begin implementation"
  - "code feature"
  - "linear implement feature"
  - "parallel implement feature"
  - "parallel implement"
  - "parallel build feature"
---

# Implement Feature

Implement an approved OpenSpec proposal. Automatically selects execution tier based on coordinator availability and existing artifacts. Ends when PR is created and awaiting review.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal exists at `openspec/changes/<change-id>/`
- Run `/plan-feature` first if no proposal exists

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Steps

### 0. Detect Coordinator and Select Tier [all tiers]

Run the coordinator detection script:

```bash
python3 "<skill-base-dir>/../coordination-bridge/scripts/check_coordinator.py" --json
```

Parse JSON output and set capability flags. Then select tier:

```
If COORDINATOR_AVAILABLE and CAN_DISCOVER and CAN_QUEUE_WORK and CAN_LOCK:
  TIER = "coordinated"
Else if work-packages.yaml exists at openspec/changes/<change-id>/:
  TIER = "local-parallel"
Else if tasks.md has 3+ independent tasks with non-overlapping file scopes:
  TIER = "local-parallel"
Else:
  TIER = "sequential"
```

Emit tier notification:
```
Tier: <tier> -- <rationale>
```

If `CAN_HANDOFF=true`, read recent handoff context.

### 1. Verify Proposal Exists [all tiers]

```bash
openspec show <change-id>
cat openspec/changes/<change-id>/tasks.md
```

Confirm the proposal is approved before proceeding.

### 2. Setup Worktree for Feature Isolation [all tiers]

```bash
AGENT_FLAG=""
if [[ -n "${AGENT_ID:-}" ]]; then
  AGENT_FLAG="--agent-id ${AGENT_ID}"
fi

eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>" ${AGENT_FLAG})"
cd "$WORKTREE_PATH"

# Two distinct branches matter here:
#
#   WORKTREE_BRANCH — this worktree's branch, which for parallel work-package
#                     agents is <parent>--<agent-id>. Used for commits inside
#                     this worktree and for local branch verification.
#   FEATURE_BRANCH  — the PARENT feature branch that agent branches merge into
#                     and that gets pushed as the PR head. In the single-agent
#                     case it equals WORKTREE_BRANCH. In the parallel case it
#                     is the operator/default branch without the agent suffix.
#
# The parent branch is what plan-feature pushed and what the PR is opened
# against. Resolve it explicitly so the final push/PR target is stable.
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" resolve-branch "<change-id>" --parent)"
FEATURE_BRANCH="$BRANCH"
```

**Operator branch override**: If `OPENSPEC_BRANCH_OVERRIDE` was set at plan time, it MUST be set at implement time too — otherwise plan-feature and implement-feature will disagree on the branch and commits will diverge. The safest pattern is for the operator to set the env var for the entire session.

**Parallel disambiguation**: When `AGENT_ID` is set (parallel work-package agents), each agent gets `<FEATURE_BRANCH>--<agent-id>` as its `WORKTREE_BRANCH` so parallel agents don't clobber each other. The `wp-integration` package (or `merge_worktrees.py`) merges those sub-branches back into `$FEATURE_BRANCH` before the final push.

### 3. Verify Feature Branch [all tiers]

```bash
CURRENT_BRANCH="$(git branch --show-current)"
# In single-agent mode, WORKTREE_BRANCH == FEATURE_BRANCH.
# In parallel mode, WORKTREE_BRANCH is <FEATURE_BRANCH>--<agent-id>.
if [[ "$CURRENT_BRANCH" != "$WORKTREE_BRANCH" ]]; then
  echo "ERROR: worktree is on '$CURRENT_BRANCH' but expected '$WORKTREE_BRANCH'" >&2
  echo "Hint: if OPENSPEC_BRANCH_OVERRIDE is set, ensure it matches what plan-feature used" >&2
  exit 1
fi
```

## Implementation Rules (0–5)

These rules govern every line of code written under this skill. They apply to all tiers and to every sub-agent dispatched in Step 3b. When in doubt, re-read this section.

- **Rule 0 — Simplicity First.** Prefer the smallest change that solves the problem. Three similar lines beat a premature abstraction. Before writing any code, ask: *"What is the simplest thing that could work?"* — then do that.
- **Rule 0.5 — Scope Discipline.** Touch only what the work package's `write_allow` requires. Do not opportunistically clean up adjacent code, refactor unrelated imports, or add features that weren't asked for. When you spot something genuinely broken outside scope, log it with the **Scope discipline template** below — do not silently fix it.
- **Rule 1 — One Thing at a Time.** Each commit is one logical change. No mixing concerns. A commit that says `feat(auth): add login AND fix unrelated typo` is two commits pretending to be one.
- **Rule 2 — Keep It Compilable.** Every commit on the feature branch must build and pass existing tests. No "broken middle" commits — even mid-feature, the tip of the branch is always green. If you must land partial work, hide it behind a feature flag (Rule 3).
- **Rule 3 — Feature Flags for Risky Changes.** If a feature is incomplete, uncertain, or potentially destabilizing, gate it behind a flag that defaults OFF. This lets the work merge without risking production callers.
- **Rule 4 — Safe Defaults.** New config keys, env vars, and parameters MUST default to the **current** behavior. Adding a config that changes behavior unless explicitly set is a silent breaking change.
- **Rule 5 — Rollback-Friendly.** Every change should have an obvious revert path: a single revertable commit, an OFF-by-default flag, or a documented rollback procedure. If reverting requires a manual data migration, call that out in the PR description.

### Scope discipline template

When a sub-agent (or you) notices an issue outside the current work package's scope, do NOT fix it. Log it with this exact template at the bottom of the work-package result and file a follow-up:

```
NOTICED BUT NOT TOUCHING:
- <file or area>: <what's wrong> — out of scope for this work package, file follow-up.
```

This template is **mandatory** for any out-of-scope observation. It surfaces the issue (so it isn't lost) without polluting the current diff.

### 3a. Generate Change Context & Test Plan (Phase 1 -- TDD RED) [all tiers]

Before implementing, create the traceability skeleton and write failing tests:

1. Read spec delta files from `openspec/changes/<change-id>/specs/`. For each SHALL/MUST clause, create a row in the Requirement Traceability Matrix.
2. For each row, populate the **Contract Ref** column:
   - If `contracts/` exists and contains machine-readable artifacts (not just `README.md`): map the requirement to the contract file it validates (e.g., `contracts/openapi/v1.yaml#/paths/~1users`, `contracts/events/coordinator.schema.json`). Use `---` if no contract applies to this specific requirement.
   - If `contracts/` exists but contains only `README.md` (no applicable interfaces): use `---` for all contract refs.
   - If `contracts/` does not exist (legacy change predating universal artifacts): log a warning that contract-based validation was skipped. Use `---` for all contract refs.
   - If a contract file exists but cannot be parsed (invalid YAML/JSON): log an error identifying the malformed file, skip validation for that contract sub-type, and use `---` for affected contract refs. Do not block implementation on parse failures.
3. For each row, populate the **Design Decision** column: link to the decision from `design.md` (e.g., `D3`) that this requirement validates. Use `---` if none applies. If `design.md` exists, also populate the Design Decision Trace section.
4. Write failing tests (RED) for each row in the matrix. Tests MUST assert against contract schemas and design decisions where referenced — not just internal behavior. For partial contracts (e.g., OpenAPI exists but no DB schema), validate only against the sub-types present.

Use template from `openspec/schemas/feature-workflow/templates/change-context.md`. Write to `openspec/changes/<change-id>/change-context.md`.

### 3b. Implement Tasks (Phase 2 -- TDD GREEN)

Implementation strategy depends on the selected tier:

---

#### Sequential Tier [sequential]

Work through tasks sequentially from `tasks.md`. Use the runtime-native apply workflow or CLI fallback:

```bash
openspec instructions apply --change "<change-id>" --json
openspec status --change "<change-id>"
```

##### Archetype Resolution (Phase 2)

Before dispatching implementation agents, resolve the archetype model. This enables
complexity-based escalation from Sonnet to Opus for large work packages:

```python
from src.agents_config import load_archetypes_config, resolve_model, compose_prompt

archetypes = load_archetypes_config()  # cached singleton — no repeated file I/O
implementer = archetypes.get("implementer")
runner = archetypes.get("runner")

# For each package, resolve implementer model based on complexity signals
package_metadata = {
    "write_allow": <from work-packages.yaml scope.write_allow>,
    "dependencies": <from work-packages.yaml depends_on>,
    "loc_estimate": <from work-packages.yaml metadata.loc_estimate>,
    "complexity": <from work-packages.yaml metadata.complexity or None>,
}
impl_model = resolve_model(implementer, package_metadata) if implementer else "sonnet"
runner_model = resolve_model(runner, {}) if runner else "haiku"
```

Thresholds are configurable in `agent-coordinator/archetypes.yaml` — no code changes needed.

##### Parallel Implementation (for independent tasks)

When tasks.md contains 3+ **independent tasks** (no shared files), implement concurrently:

```
Task(
  subagent_type="general-purpose",
  model=impl_model,  # archetype: implementer (sonnet, or opus if escalated)
  description="Implement task N: <brief>",
  prompt="You are implementing OpenSpec <change-id>, Task N.
**Your Task**
<TASK_DESCRIPTION>
**File Scope (CRITICAL)**
You MAY modify: <list specific files>
You must NOT modify any other files.
**Context**
- Read openspec/changes/<change-id>/proposal.md
- Read openspec/changes/<change-id>/design.md
Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)
```

**When to parallelize:** 3+ independent tasks with no file overlap.
**When NOT to:** Tasks that share files/state or have logical dependencies.

---

#### Local Parallel Tier [local-parallel]

Uses `work-packages.yaml` for structured DAG execution within a **single feature worktree**.

**A. Parse and validate work-packages.yaml:**

```bash
skills/.venv/bin/python "<skill-base-dir>/../parallel-infrastructure/scripts/dag_scheduler.py" \
  --validate openspec/changes/<change-id>/work-packages.yaml
```

Compute topological order from `packages[].depends_on`.

**B. Execute root packages sequentially:**

For each root package (depends_on == []), implement within the feature worktree.

**C. Dispatch independent packages in parallel:**

For each package whose dependencies are satisfied, dispatch via Agent tool:

```
Task(
  subagent_type="general-purpose",
  model=impl_model,  # archetype: implementer (sonnet, or opus if escalated)
  description="Implement <package-id>",
  prompt="You are implementing work package <package-id> for OpenSpec <change-id>.

**File Scope (CRITICAL)**
write_allow: <from work-packages.yaml>
read_allow: <from work-packages.yaml>
deny: <from work-packages.yaml>

**Context**
<context slice from Context Slicing table below>

**Verification**
After implementation, run:
<verification steps from work-packages.yaml>

**Scope Discipline**
Follow Implementation Rules 0–5 (see `skills/implement-feature/SKILL.md`).
If you notice issues outside this package's `write_allow`, do NOT fix them.
Append to your result using the literal `NOTICED BUT NOT TOUCHING:` template
documented in the parent skill, so they're filed as follow-ups instead of
silently widening this PR.

Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)
```

**D. Collect results and verify scope:**

```bash
skills/.venv/bin/python "<skill-base-dir>/../parallel-infrastructure/scripts/scope_checker.py" \
  --packages openspec/changes/<change-id>/work-packages.yaml \
  --diff <git diff output>
```

**E. Update change-context.md:**

- Fill Files Changed column from `git diff --name-only main..HEAD`
- Update Design Decision Trace if design.md exists
- Update Coverage Summary counts

---

#### Coordinated Tier [coordinated]

Full multi-agent DAG execution with coordinator integration. Each work package runs in its own worktree with explicit lock claims.

##### Phase A: Feature-Level Preflight (Orchestrator)

```
A1. Parse and validate work-packages.yaml against schema
A2. Validate contracts exist
A3. Compute DAG order (topological sort, cycle detection)
A3.5. Generate Change Context with relevant rows per package
A4. Create or reuse feature branch
A5. Implement root packages (sequentially, each in own worktree)
A6. Setup worktrees for parallel packages (branch from feature branch)
A7. Dispatch parallel agents with WORKTREE_PATH, BRANCH, CHANGE_ID, PACKAGE_ID
A8. Begin monitoring loop (discover_agents, get_task polling)
```

##### Phase B: Package Execution Protocol (Every Worker Agent)

Each worker agent follows steps B1-B11: session registration, pause-lock check, deadlock-safe lock acquisition (lexicographic order), code generation within scope, deterministic scope check via git diff, verification steps, structured result publication.

Workers MUST call heartbeat every 30 minutes:
```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" heartbeat "${CHANGE_ID}" --agent-id "${PACKAGE_ID}"
```

##### Phase C: Review + Integration Sequencing

```
C1. Result validation against work-queue-result.schema.json
C2. Escalation processing
C3. Per-package multi-vendor review (via /parallel-review-implementation)
    - Self-review + vendor dispatch via parallel-infrastructure/scripts/review_dispatcher.py
    - Consensus synthesis via parallel-infrastructure/scripts/consensus_synthesizer.py
C4. Integration gate (consensus-aware)
C5. Integration merge (wp-integration package, merge_worktrees.py)
C5.5. Finalize Change Context (Files Changed, Design Decision Trace, Review Findings Summary)
C6. Execution summary generation
```

**Teardown** (after PR creation or on failure):
```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" unpin "<change-id>"
for pkg in <package-ids> integrator; do
    python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "<change-id>" --agent-id "$pkg"
done
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" gc
```

---

### 4. Track Progress [all tiers]

Use TodoWrite for in-session state tracking. Additionally, `tasks.md` is the canonical post-session record of what's done — keep it in sync **commit-by-commit, not batched at the end**.

**Per-task checkbox discipline (REQUIRED)**:

For each task you complete, flip its `- [ ]` to `- [x]` in `openspec/changes/<change-id>/tasks.md` **in the same commit that implements the task**. Do NOT defer checkbox updates into a trailing "mark tasks complete" commit.

- When committing task N.N: stage both the implementation files AND `tasks.md`, then commit together
- Commit message pattern: `feat(<scope>): <task summary> (<change-id> task N.N)`
- If you notice an unchecked task whose code has already landed in an earlier commit, flip it in your next commit (do not batch-flip at the end)

**Why this discipline matters**: When PRs auto-merge via review-queue automation, a trailing "mark tasks complete" commit is often skipped, lost during rebase, or bundled into an unrelated squash. Coupling the checkbox flip to the implementation commit means the bookkeeping travels with the code, and archive-time drift (tasks.md showing 0/N while implementation is 100% landed) becomes structurally impossible. Past incident: `specialized-workflow-agents` (archived 2026-04-22) shipped all 29 tasks of code to main with 0/29 checkboxes flipped, requiring retroactive reconciliation via `/openspec-verify-change` before archive.

### 5. Verify All Tasks Complete [all tiers]

This is a **last-line-of-defense** check after per-task discipline. If Step 4 was followed, this should pass trivially.

```bash
grep -E "^\s*- \[ \]" openspec/changes/<change-id>/tasks.md
# Should return nothing (all boxes checked)
```

**If it returns any lines, STOP and reconcile before proceeding**:
- If the task was implemented: flip its checkbox in a new commit (`chore(openspec): reconcile task N.N checkbox`) — do NOT amend implementation commits already on main
- If the task is genuinely deferred: move it to `openspec/changes/<change-id>/deferred-tasks.md` with a short rationale, and remove it from tasks.md

Do NOT run quality checks (Step 6) or `/validate-feature` (Step 6.5) while tasks.md has unchecked boxes — the spec-compliance phase will fail the task-drift gate.

### 6. Quality Checks (Parallel Execution) [all tiers]

Run all environment-safe checks. These must pass in both cloud and local environments:

```
Task(subagent_type="Bash", model=runner_model, prompt="Run pytest and report pass/fail", run_in_background=true)
Task(subagent_type="Bash", model=runner_model, prompt="Run mypy src/ and report type errors", run_in_background=true)
Task(subagent_type="Bash", model=runner_model, prompt="Run ruff check . and report linting issues", run_in_background=true)
Task(subagent_type="Bash", model=runner_model, prompt="Run openspec validate <change-id> --strict", run_in_background=true)
Task(subagent_type="Bash", model=runner_model, prompt="Run validate_flows.py --diff main...HEAD", run_in_background=true)
```

Fix all failures before proceeding.

### 6.4. Live Service Smoke Tests (Soft Gate) [all tiers]

Run live service smoke tests if a test environment is available:

```bash
python3 skills/validate-feature/scripts/phase_deploy.py --env docker --timeout 120
python3 skills/validate-feature/scripts/phase_smoke.py
python3 skills/validate-feature/scripts/stack_launcher.py teardown
```

If Docker/Neon is unavailable, log a WARNING and continue with smoke status "skipped" in validation-report.md. This is a **soft gate** — implementation proceeds regardless.

### 6.5. Artifact Validation [local-parallel+]

**Skip if TIER is "sequential".**

Delegate to `/validate-feature` for environment-safe validation phases:

```
/validate-feature <change-id> --phase spec,evidence
```

This runs the canonical validation skill targeting:
- **Spec compliance** (`spec` phase): Audits `change-context.md` Requirement Traceability Matrix — verifies no `---` entries in Files Changed, updates Coverage Summary counts, and checks each requirement against the implementation.
- **Evidence completeness** (`evidence` phase): Validates work-package results against `work-queue-result.schema.json`, checks revision consistency, scope compliance, and cross-package consistency. Populates the Evidence column in `change-context.md`.

These phases are environment-safe and run in both cloud and local. Docker-dependent phases (deploy, smoke, security, E2E) are deferred to the merge-time validation gate in `/cleanup-feature` or `/merge-pull-requests`.

### 7. Document Lessons Learned [all tiers]

Document patterns, gotchas, and design changes in CLAUDE.md and AGENTS.md.

### 7.5. Append Session Log [all tiers]

Append an `Implementation` phase entry to the session log, capturing the implementation approach, deviations from plan, and issues encountered.

**Phase entry template:**

```markdown
---

## Phase: Implementation (<YYYY-MM-DD>)

**Agent**: <agent-type> | **Session**: <session-id-or-N/A>

### Decisions
1. **<Decision title>** — <rationale>

### Alternatives Considered
- <Alternative>: rejected because <reason>

### Trade-offs
- Accepted <X> over <Y> because <reason>

### Open Questions
- [ ] <unresolved question>

### Context
<2-3 sentences: what was implemented, any deviations from plan>
```

**Focus on**: Implementation approach, deviations from the plan, technical issues encountered, patterns chosen.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip session log and proceed.

The session-log.md is included in `git add .` in Step 8.

### 8. Commit Changes [all tiers]

**Commit quality matters**: OpenSpec PRs use rebase-merge by default, so every commit appears individually on main. Structure commits as logical, self-contained units:

- **One commit per task** (or per logical sub-task) — not one giant commit, not WIP fragments
- **Conventional commit format**: `feat(scope):`, `fix(scope):`, `test(scope):`, `docs(scope):`
- **No WIP/fixup commits**: If you need to iterate, amend or fixup before pushing
- **Reference the change-id** in the commit body for traceability

```bash
git add .
git commit -m "$(cat <<'EOF'
feat(<scope>): <description>

Implements OpenSpec: <change-id>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### 9. Push and Create PR [all tiers]

```bash
# Push to the resolved feature branch (honors OPENSPEC_BRANCH_OVERRIDE)
git push -u origin "$FEATURE_BRANCH"
gh pr create --title "feat(<scope>): <title>" --body "..."
```

If `CAN_HANDOFF=true`, write a completion handoff.

**STOP HERE -- Wait for PR approval before proceeding to cleanup.**

## Context Slicing for Implementation

When dispatching work packages, each agent receives only the context it needs:

| Package Type | Context Slice |
|-------------|---------------|
| `wp-contracts` | `proposal.md` + spec deltas + contract templates |
| Backend packages | `design.md` (backend section) + `contracts/openapi/` + package scope |
| Frontend packages | `design.md` (frontend section) + `contracts/generated/types.ts` + package scope |
| `wp-integration` | Full `work-packages.yaml` + all contract artifacts |

## Output

- Feature branch: `$FEATURE_BRANCH` (default `openspec/<change-id>`, or whatever `OPENSPEC_BRANCH_OVERRIDE` resolved to)
- All tests passing
- PR created and awaiting review

## Next Step

After PR is approved:
```
/cleanup-feature <change-id>
```

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "While I'm in this file I'll fix the unrelated bug too" | Violates Rule 0.5 (Scope Discipline). The fix may pass review on its own merit but it bloats the diff, hides the real change, and couples your PR's fate to an unrelated risk. Use the `NOTICED BUT NOT TOUCHING:` template instead. |
| "This commit is broken but the next one fixes it — squash will hide it" | Violates Rule 2. Rebase-merge means every commit lands on main individually; a broken middle commit breaks `git bisect` for the next person to chase a regression. |
| "Adding the new flag and flipping the default in one go is cleaner" | Violates Rule 4 (Safe Defaults). Default-flip changes behavior for every existing caller silently. Land the flag OFF, ship it, then change the default in a separate, revertable commit. |
| "I'll skip the per-task checkbox flip and batch them at the end" | The trailing "mark tasks complete" commit is routinely lost in rebase/squash. Past incident: 0/29 checkboxes flipped while 100% of code was on main. Couple the bookkeeping to the implementation commit. |

## Red Flags

- A commit message containing the word "and" describing two distinct changes (Rule 1 violation).
- A diff that touches files outside the package's `write_allow` without a recorded `NOTICED BUT NOT TOUCHING:` justification (Rule 0.5 violation).
- A new config key whose default value changes behavior for existing deployments (Rule 4 violation).
- `tasks.md` shows unchecked boxes after Step 5 (per-task checkbox discipline violation).
- A "WIP" or "fixup" commit on the feature branch at PR-creation time (Rule 2 violation).
- The PR description has no obvious rollback path — no flag, no single revert commit, no migration plan (Rule 5 violation).

## Verification

1. Cite the Implementation Rules section that informed each non-trivial design choice (e.g., "Rule 3: gated behind `FEATURE_X_ENABLED`, default OFF").
2. Show that every commit on the branch builds and passes tests in isolation: `git log --oneline main..HEAD` followed by spot-checking ≥1 mid-branch commit.
3. Confirm the diff contains zero touches outside `write_allow` from `work-packages.yaml`, OR every such touch is documented under `NOTICED BUT NOT TOUCHING:`.
4. Confirm `grep -E "^\s*- \[ \]" openspec/changes/<change-id>/tasks.md` returns nothing (per-task checkbox discipline applied).
5. Confirm the PR description names the rollback path (flag name to flip, single commit to revert, or migration to run).
