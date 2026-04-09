---
name: plan-feature
description: "Create OpenSpec proposal with tiered execution (coordinated / local-parallel / sequential)"
category: Git Workflow
tags: [openspec, planning, proposal, contracts, work-packages]
triggers:
  - "plan feature"
  - "plan a feature"
  - "design feature"
  - "propose feature"
  - "start planning"
  - "linear plan feature"
  - "parallel plan feature"
  - "parallel plan"
  - "plan parallel feature"
---

# Plan Feature

Create an OpenSpec proposal for a new feature. Automatically selects execution tier based on coordinator availability and feature complexity. Uses interactive discovery questions and two-gate approval to ensure the plan reflects user intent before detailed artifacts are generated.

## Arguments

`$ARGUMENTS` - Feature description (e.g., "add user authentication")

Optional flags:
- `--explore` -- Deep-dive mode: more discovery questions (5-8 vs 2-5), more approaches (3-5 vs 2-3), web search for prior art when available

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Interactive Planning

This skill uses **AskUserQuestion** to gather user input at discovery and approval gates. If AskUserQuestion is unavailable in the current runtime, present questions as a numbered list in regular output and instruct the user to respond inline.

**Planning gates:**
- **Step 3**: Discovery questions -- gather scope, constraints, and preferences before any artifacts are created
- **Step 5**: Gate 1 (Direction) -- user selects an approach before detailed specs/tasks are generated
- **Step 12**: Gate 2 (Plan) -- user approves the complete plan before implementation begins

## Steps

### 0. Detect Coordinator, Select Tier, Parse Flags [all tiers]

Run the coordinator detection script:

```bash
python3 "<skill-base-dir>/../coordination-bridge/scripts/check_coordinator.py" --json
```

Parse JSON output and set capability flags. Then select tier:

```
If COORDINATOR_AVAILABLE and CAN_DISCOVER and CAN_QUEUE_WORK and CAN_LOCK:
  TIER = "coordinated"
Else if user invoked via "parallel plan" trigger OR feature touches 2+ architectural boundaries:
  TIER = "local-parallel"
Else:
  TIER = "sequential"
```

Parse optional flags from `$ARGUMENTS`:

```
EXPLORE_MODE=false
if [[ "$ARGUMENTS" == *"--explore"* ]]; then
  EXPLORE_MODE=true
fi

# Discovery question bounds
if [[ "$EXPLORE_MODE" == "true" ]]; then
  MIN_QUESTIONS=5; MAX_QUESTIONS=8
  MIN_APPROACHES=3; MAX_APPROACHES=5
else
  MIN_QUESTIONS=2; MAX_QUESTIONS=5
  MIN_APPROACHES=2; MAX_APPROACHES=3
fi
```

Emit tier notification:
```
Tier: <tier> -- <rationale>
Mode: <standard | explore>
```

If `CAN_HANDOFF=true`, read recent handoff context. If `CAN_MEMORY=true`, recall relevant memories.

### 1. Setup Planning Worktree [all tiers]

The shared checkout is **read-only** -- never commit or modify files there. All planning work happens in a feature-level worktree.

```bash
# plan-feature always runs single-agent, so WORKTREE_BRANCH == FEATURE_BRANCH here.
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>")"
cd "$WORKTREE_PATH"
FEATURE_BRANCH="$WORKTREE_BRANCH"

git rev-parse --show-toplevel     # Should match WORKTREE_PATH
git branch --show-current         # Should match $FEATURE_BRANCH
```

If the worktree already exists (e.g., from a previous session), reuse it. All subsequent steps happen **inside the worktree**.

**Operator branch override**: When `OPENSPEC_BRANCH_OVERRIDE` is set (e.g. by the Claude cloud harness with `claude/fix-branch-mismatch-9P9o1`), `worktree.py` uses that branch instead of `openspec/<change-id>`. Downstream push/PR steps must reference `$FEATURE_BRANCH` rather than hardcoding the openspec prefix. If `implement-feature` later dispatches parallel work-package agents, they will each branch off `$FEATURE_BRANCH` with `--<agent-id>` suffixes (e.g. `claude/fix-branch-mismatch-9P9o1--wp-backend`) and merge back into `$FEATURE_BRANCH` at integration time.

### 2. Review Existing Context (Parallel Exploration) [all tiers]

Gather context from multiple sources concurrently using Task(Explore) agents:

```
Task(subagent_type="Explore", prompt="Read openspec/project.md and summarize the project purpose, tech stack, and conventions", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list --specs' and summarize existing specifications", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list' and identify in-progress changes that might conflict with: $ARGUMENTS", run_in_background=true)
Task(subagent_type="Explore", prompt="Search the codebase for existing implementations related to: $ARGUMENTS", run_in_background=true)
Task(subagent_type="Explore", prompt="Read docs/architecture-analysis/architecture.summary.json and parallel_zones.json for component inventory and safe parallel zones", run_in_background=true)
```

Wait for all results and synthesize into unified context summary.

Before creating artifacts, ensure architecture artifacts are current:

```bash
if [ ! -f docs/architecture-analysis/architecture.summary.json ] || \
   [ "$(git log -1 --format=%ct main)" -gt "$(stat -f %m docs/architecture-analysis/architecture.summary.json 2>/dev/null || echo 0)" ]; then
  make architecture
fi
```

### 3. Present Context and Discovery Questions [all tiers]

This step ensures the user has visibility into what was discovered and shapes the plan before any artifacts are generated.

#### 3a. Present Discovered Context

Format the Explore agent results from Step 2 as a structured summary and present it to the user via regular message output:

```
## What I Found

### Related Specs
- <spec-name>: <one-line summary of relevance>

### Related Code
- <file-path>: <what it does and how it relates to this feature>

### Potential Conflicts
- <in-progress change-id>: <what it touches that overlaps with this feature>
(or "None found" if no conflicts)

### Architectural Constraints
- <constraint from architecture analysis or parallel_zones.json>

### Prior Art (--explore mode only)
- <pattern, library, or approach found via web search>
(Skip this section if EXPLORE_MODE=false or web search is unavailable)
```

This gives the user the same information you have, enabling better answers to the questions that follow.

#### 3b. Discovery Questions

Ask MIN_QUESTIONS to MAX_QUESTIONS clarifying questions using the **AskUserQuestion tool**. Draw from these five categories, selecting the most relevant ones based on the discovered context:

1. **Scope boundaries** -- Use AskUserQuestion with preset options.
   Examples: "Should <related capability X> be included in scope?" Options: "Yes, include it" / "No, out of scope" / "Defer to a follow-up proposal"

2. **Trade-off preferences** -- Use AskUserQuestion with preset options presenting 2-3 positions.
   Examples: "I see a trade-off between <simplicity vs flexibility / speed vs correctness / etc>. Which direction?" Options describe each position.

3. **Constraint discovery** -- Use AskUserQuestion without preset options (open-ended).
   Examples: "Are there timeline, compatibility, or performance constraints I should know about?" / "Are there any rejected approaches or past attempts I should avoid?"

4. **Existing decisions** -- Use AskUserQuestion with preset options when specific decisions are discoverable from context.
   Examples: "The codebase currently uses <pattern X> for similar features. Should we follow this pattern or introduce a new one?" Options: "Follow existing pattern" / "New approach because <reason>"

5. **Success criteria** -- Use AskUserQuestion without preset options (open-ended).
   Examples: "What does success look like for this feature?" / "How will you know this feature is working correctly?"

**Rules for question generation:**
- Questions MUST reference specific discoveries from Step 3a (e.g., "I found spec X covers Y. Should this feature extend that spec or create a new one?")
- Skip categories that are already clearly answered by `$ARGUMENTS`
- If `EXPLORE_MODE=true`, add prior-art questions: "I found <pattern/library X> is commonly used for this. Should we adopt it, adapt it, or build custom?"
- Ask questions in batches of 2-4 via AskUserQuestion to avoid overwhelming the user
- Prioritize questions where the answer would significantly change the approach

**STOP -- Wait for the user to answer all discovery questions before proceeding to Step 4. Do NOT generate any artifacts until all answers are received.**

### 4. Create Proposal with Approaches [all tiers]

Preferred path: Use runtime-native fast-forward/new workflow.

CLI fallback path:

```bash
openspec new change "<change-id>"
openspec instructions proposal --change "<change-id>"
```

Generate ONLY `proposal.md` at this stage. Incorporate user answers from Step 3b into the Why and What Changes sections.

**Mandatory: Approaches Considered section.** Generate MIN_APPROACHES to MAX_APPROACHES genuinely distinct approaches. For each approach, include:
- **Name**: Short descriptive name
- **Description**: 1-2 sentences on how it works
- **Pros**: Bullet list
- **Cons**: Bullet list
- **Effort**: S / M / L

Mark one approach as **Recommended** with a rationale that references specific pros/cons.

If `EXPLORE_MODE=true`, reference prior art discoveries in approach descriptions where relevant.

Expected artifact (this step only):
- `openspec/changes/<change-id>/proposal.md`

### 5. Gate 1: Direction Approval [all tiers]

Present `proposal.md` to the user and ask them to select an approach.

Use **AskUserQuestion** with these options:
- One option per approach: "Proceed with Approach N: <name>" (description: brief summary of what this means)
- "Modify approaches" (description: "I'll revise the approaches based on your feedback")
- "Need more detail before deciding" (description: "I'll research further and ask follow-up questions")

**STOP -- Wait for the user to select an approach.**

After selection:
- If "Modify approaches": gather feedback, loop back to Step 4
- If "Need more detail": ask follow-up questions, loop back to Step 4
- If an approach is selected: update `proposal.md` with a `### Selected Approach` subsection recording the choice and any modifications the user requested. Demote unselected approaches to brief entries under the Recommended subsection.

### 6. Generate Specs, Tasks, and Design [all tiers]

Now that the direction is confirmed, generate the remaining planning artifacts.

CLI fallback path:

```bash
openspec instructions specs --change "<change-id>"
openspec instructions tasks --change "<change-id>"
openspec instructions design --change "<change-id>"  # When complexity warrants it
```

**Critical**: The selected approach from Gate 1 MUST drive all artifact content. Tasks must implement the selected approach specifically, not a generic solution. Specs must reflect the chosen approach's behavior.

**Spec format — strict delta headers**: The `openspec validate` CI check will reject specs that don't follow this exact format. Every spec file MUST use:
- `## ADDED Requirements` (or `MODIFIED`/`REMOVED`/`RENAMED`) as the top-level section — NOT `## Requirements`
- `### Requirement: <Name>` for each requirement block — NOT `### REQ-ID:` or other heading styles
- `#### Scenario: <name>` with WHEN/THEN/AND structure under each requirement — at least one per requirement
- `SHALL` or `MUST` language for normative statements

Verify after generating: `openspec validate <change-id>`. If it fails, fix the spec before proceeding.

**Task ordering — TDD test-first**: Within each phase of `tasks.md`, list test
tasks *before* the implementation tasks they verify. Each implementation task
should declare a dependency on its corresponding test task. This ensures
`/implement-feature` writes tests (RED) before writing code to make them pass
(GREEN).

**Test tasks must reference the artifacts they validate**:
- **Spec scenarios**: Each test task lists the spec scenario IDs (e.g., `agent-coordinator.3`) it encodes. Every SHALL/MUST scenario in specs must be covered by at least one test task.
- **Contracts**: If contracts exist (local-parallel+ tiers), test tasks reference the contract files they assert against — OpenAPI endpoint schemas, DB schema constraints, event payload JSON schemas. This ensures tests validate the contracted interface, not just internal behavior.
- **Design decisions**: If `design.md` exists, test tasks reference the decision IDs (e.g., `D3`) they verify. This catches cases where the implementation accidentally uses an approach that was explicitly rejected.

Example:
```markdown
- [ ] 1.1 Write tests for EventBusService — callback dispatch, reconnection
  **Spec scenarios**: agent-coordinator.1 (event delivery), agent-coordinator.2 (reconnection)
  **Contracts**: contracts/events/coordinator.schema.json
  **Design decisions**: D3 (pg_notify over polling)
  **Dependencies**: None
- [ ] 1.2 Create event_bus.py — EventBusService with on_event() registration
  **Dependencies**: 1.1
```

Expected artifacts:
- `openspec/changes/<change-id>/specs/<capability>/spec.md`
- `openspec/changes/<change-id>/tasks.md`
- Optional `openspec/changes/<change-id>/design.md`

### 7. Generate Contracts [all tiers]

For sequential-tier plans, include only contract sub-types applicable to the feature:
- OpenAPI contracts if the feature introduces or modifies API endpoints
- Database contracts if the feature introduces or modifies database schemas
- Event contracts if the feature introduces or modifies events
- Type generation stubs derived from the contracts above

If no contract sub-types are applicable (e.g., pure documentation or skill-definition changes), create `contracts/README.md` with a stub documenting which sub-types were evaluated and why none apply. Consuming skills treat a `contracts/` directory containing only `README.md` as "no contracts applicable".

Produce machine-readable interface definitions in `contracts/`. Contracts become the coordination boundary between parallel agents.

#### 7a. OpenAPI Contracts

For API features, generate from `openspec/schemas/feature-workflow/templates/openapi-stub.yaml`:

```yaml
contracts/openapi/v1.yaml    # OpenAPI 3.1.0 spec with paths, schemas, examples
```

Requirements: every endpoint has request/response schemas with `example` fields, discriminator fields for polymorphic responses, error response schemas following RFC 7807.

#### 7b. Database Contracts

```yaml
contracts/db/schema.sql      # CREATE TABLE / ALTER TABLE statements
contracts/db/seed.sql         # Test fixture data
```

#### 7c. Event Contracts

```yaml
contracts/events/user.created.schema.json   # JSON Schema for event payload
```

#### 7d. Type Generation Stubs

```yaml
contracts/generated/models.py    # Pydantic models from OpenAPI schemas
contracts/generated/types.ts     # TypeScript interfaces from OpenAPI schemas
```

### 8. Generate Work Packages [all tiers]

For sequential-tier plans, generate a single `wp-main` package encompassing the full feature scope:

```yaml
packages:
  - id: wp-main
    name: "<feature-name> — full scope"
    description: "<feature description>"
    tasks: [all task IDs from tasks.md]
    priority: 1
    dependencies: []
    scope:
      write_allow: ["**"]
      read_allow: ["**"]
    verification: tier_b
```

This provides a uniform artifact format across all tiers. The `wp-main` package can later be split into parallel packages if the feature is upgraded to local-parallel tier.

For local-parallel and coordinated tiers, decompose tasks into agent-scoped work packages as described below.

Decompose tasks into agent-scoped work packages in `work-packages.yaml`. Follow the schema at `openspec/schemas/work-packages.schema.json`.

#### 8a. Package Decomposition

Group tasks by architectural boundary:
- `wp-contracts` -- Generate/validate contracts (always first, priority 1)
- `wp-<backend-module>` -- Backend implementation per bounded context
- `wp-<frontend-module>` -- Frontend implementation per component group
- `wp-integration` -- Merge worktrees and run full test suite (always last)

#### 8b. Scope Assignment

For each package, declare explicit file scope:

```yaml
scope:
  write_allow:
    - "src/api/**"
  read_allow:
    - "src/**"
    - "contracts/**"
  deny:
    - "src/frontend/**"
```

**Rule**: Parallel packages MUST have non-overlapping `write_allow` scopes.

#### 8c. Lock Declaration

```yaml
locks:
  files:
    - "src/api/users.py"
  keys:
    - "api:GET /v1/users"
    - "db:schema:users"
    - "event:user.created"
  ttl_minutes: 120
  reason: "Backend API implementation"
```

Follow canonicalization rules from `docs/lock-key-namespaces.md`.

#### 8d. Dependency DAG

- `wp-contracts` has no dependencies (root)
- Implementation packages depend on `wp-contracts`
- `wp-integration` depends on all implementation packages

#### 8e. Verification Steps

Assign verification tier per package: Tier A (full), Tier B (CI), Tier C (static).

### 9. Validate All Artifacts [all tiers]

**All tiers:**
```bash
openspec validate <change-id> --strict
```

**Local-parallel+ tiers** (additionally):
```bash
skills/.venv/bin/python "<skill-base-dir>/../validate-packages/scripts/validate_work_packages.py" \
  openspec/changes/<change-id>/work-packages.yaml

skills/.venv/bin/python "<skill-base-dir>/../refresh-architecture/scripts/parallel_zones.py" \
  --validate-packages openspec/changes/<change-id>/work-packages.yaml --json
```

Fix any validation errors before proceeding.

### 10. Register Resource Claims [coordinated only]

**Skip unless TIER is "coordinated" and CAN_LOCK=true.**

Pre-register resource claims with the coordinator:

```
For each package in work-packages.yaml:
  For each lock key in package.locks.keys:
    acquire_lock(file_path=key, reason="planned: <feature-id>/<package-id>", ttl_minutes=0)
```

Use `ttl_minutes=0` for planning claims -- they signal intent without expiring.

### 11. Commit, Push, and Pin Worktree [all tiers]

```bash
git add openspec/changes/<change-id>/
git commit -m "plan: <change-id> -- proposal, design, specs, tasks, contracts, work-packages"
# Push to the branch resolved by worktree.py setup (honors OPENSPEC_BRANCH_OVERRIDE)
git push -u origin "$FEATURE_BRANCH"

python3 "<skill-base-dir>/../worktree/scripts/worktree.py" pin "<change-id>"
```

### 11.5. Append Session Log [all tiers]

Append a `Plan` phase entry to the session log, capturing architecture decisions, scope choices, and tier selection rationale from this planning session.

Write the following to `openspec/changes/<change-id>/session-log.md` (the `git add` in Step 11 already covers this file):

**Phase entry template:**

```markdown
---

## Phase: Plan (<YYYY-MM-DD>)

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
<2-3 sentences: what was the planning goal, what was decided>
```

**Focus on**: Architecture decisions, scope boundaries, tier selection rationale, key trade-offs made during planning.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip session log and proceed.

### 12. Gate 2: Plan Approval [all tiers]

Present the complete plan to the user:
- `proposal.md` -- What, why, and selected approach
- `design.md` -- How (if applicable)
- `tasks.md` -- Implementation plan

**All tiers (including sequential):**
- `contracts/` -- Machine-readable interfaces (or README stub if no interfaces apply)
- `work-packages.yaml` -- Execution plan (single `wp-main` for sequential, DAG for parallel)

Highlight any assumptions made during artifact generation that were not explicitly confirmed by the user.

Use **AskUserQuestion** to request final approval with these options:
- "Approve -- proceed to implementation" (description: "Plan is ready. Next step: /implement-feature <change-id>")
- "Revise tasks" (description: "Keep the approach but adjust the implementation plan")
- "Revise approach" (description: "Go back to approach selection with different options")
- "Reject -- start over" (description: "Discard this proposal and start fresh")

If `CAN_HANDOFF=true`, write completion handoff.

**STOP HERE -- Wait for approval before proceeding to implementation.**

- If "Revise tasks": gather feedback, loop back to Step 6
- If "Revise approach": loop back to Step 4
- If "Reject": teardown worktree and exit

## Output

- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/**/spec.md`
- `openspec/changes/<change-id>/contracts/`
- `openspec/changes/<change-id>/work-packages.yaml`

## Context Slicing for Implementation

When `/implement-feature` dispatches work packages, each agent receives only the context it needs:

| Package Type | Context Slice |
|-------------|---------------|
| `wp-contracts` | `proposal.md` + spec deltas + contract templates |
| Backend packages | `design.md` (backend section) + `contracts/openapi/` + package scope |
| Frontend packages | `design.md` (frontend section) + `contracts/generated/types.ts` + package scope |
| `wp-integration` | Full `work-packages.yaml` + all contract artifacts |
| `wp-main` (sequential) | `proposal.md` + `design.md` (if exists) + `contracts/` + full task list |

## Next Step

After approval:
```
/implement-feature <change-id>
```
