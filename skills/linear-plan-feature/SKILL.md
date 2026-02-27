---
name: linear-plan-feature
description: Create OpenSpec proposal for a new feature and await approval
category: Git Workflow
tags: [openspec, planning, proposal, linear]
triggers:
  - "plan feature"
  - "plan a feature"
  - "design feature"
  - "propose feature"
  - "start planning"
  - "linear plan feature"
---

# Plan Feature

Create an OpenSpec proposal for a new feature. Ends when proposal is approved.

## Arguments

`$ARGUMENTS` - Feature description (e.g., "add user authentication")

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Coordinator Integration (Optional)

Use `docs/coordination-detection-template.md` as the shared detection preamble.

- Detect transport and capability flags at skill start
- Execute hooks only when the matching `CAN_*` flag is `true`
- If coordinator is unavailable, continue with standalone behavior

## Steps

### 0. Detect Coordinator, Read Handoff, Recall Memory

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_HANDOFF=true`, read recent handoff context:

- MCP path: `read_handoff`
- HTTP path: `scripts/coordination_bridge.py` `try_handoff_read(...)`

If `CAN_MEMORY=true`, recall relevant memories before planning:

- MCP path: `recall`
- HTTP path: `scripts/coordination_bridge.py` `try_recall(...)`

On handoff/memory failure, continue with standalone planning and log informationally.

### 1. Verify Clean State

```bash
# Pull latest from main
git pull origin main

# Ensure clean working directory
git status
```

Resolve any uncommitted changes before proceeding.

### 2. Review Existing Context (Parallel Exploration)

Gather context from multiple sources concurrently using Task(Explore) agents:

```
# Launch parallel exploration agents (single message, multiple Task calls)
Task(subagent_type="Explore", prompt="Read openspec/project.md and summarize the project purpose, tech stack, and conventions", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list --specs' and summarize existing specifications and their requirement counts", run_in_background=true)
Task(subagent_type="Explore", prompt="Run 'openspec list' and identify any in-progress changes that might conflict or relate to: $ARGUMENTS", run_in_background=true)
Task(subagent_type="Explore", prompt="Search the codebase for existing implementations related to: $ARGUMENTS. Identify relevant files, patterns, and potential integration points", run_in_background=true)
Task(subagent_type="Explore", prompt="Read docs/architecture-analysis/architecture.summary.json and identify cross-layer flows, components, services, and tables related to: $ARGUMENTS. Report which existing flows would be affected and what parallel modification zones are available from docs/architecture-analysis/parallel_zones.json", run_in_background=true)
```

**Context Synthesis:**
1. Wait for all TaskOutput results
2. Synthesize findings into a unified context summary:
   - Project constraints that apply
   - Related existing specs
   - Potential conflicts with in-progress work
   - Existing code patterns to follow
   - Architecture context: affected flows, components, and safe parallel zones from `docs/architecture-analysis/` artifacts
3. Use this context to inform the proposal

Understand the current state before proposing changes.

Before creating artifacts, ensure architecture artifacts are current:

```bash
# If architecture artifacts are missing or stale relative to main, refresh them
if [ ! -f docs/architecture-analysis/architecture.summary.json ] || \
   [ "$(git log -1 --format=%ct main)" -gt "$(stat -f %m docs/architecture-analysis/architecture.summary.json 2>/dev/null || echo 0)" ]; then
  make architecture
fi
```

### 3. Create OpenSpec Proposal

Preferred path:
- Use the runtime-native fast-forward/new workflow (`opsx:ff`/`opsx:new` equivalent for the active agent) to scaffold and create planning artifacts.

CLI fallback path:

```bash
# 1) Create change scaffold
openspec new change "<change-id>"

# 2) Inspect artifact readiness
openspec status --change "<change-id>"

# 3) Generate artifacts in dependency order
openspec instructions proposal --change "<change-id>"
openspec instructions specs --change "<change-id>"
openspec instructions tasks --change "<change-id>"
# Optional when complexity warrants it
openspec instructions design --change "<change-id>"
```

Expected artifacts:
- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/<capability>/spec.md`
- Optional `openspec/changes/<change-id>/design.md`

### 4. Validate Proposal

```bash
# Strict validation
openspec validate <change-id> --strict

# Review the proposal
openspec show <change-id>
```

Fix any validation errors before presenting for approval.

### 5. Present for Approval

Share the proposal with stakeholders:
- `openspec/changes/<change-id>/proposal.md` - What and why
- `openspec/changes/<change-id>/tasks.md` - Implementation plan
- `openspec/changes/<change-id>/design.md` - How (if applicable)

If `CAN_HANDOFF=true`, write a completion handoff containing:
- Completed planning artifacts
- Key decisions and assumptions
- Open questions and approval blockers
- Recommended next command (`/iterate-on-plan` or `/implement-feature` after approval)

**STOP HERE - Wait for approval before proceeding to implementation.**

## Output

- Validated OpenSpec proposal in `openspec/changes/<change-id>/`
- Change-id ready for `/implement-feature <change-id>`

## Next Step

After approval:
```
/implement-feature <change-id>
```
