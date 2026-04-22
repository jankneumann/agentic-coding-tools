# Change: interactive-plan-feature

## Why

The `/plan-feature` skill generates full proposal artifacts without any user interaction between invocation and the final approval gate. This means Claude autonomously decides scope boundaries, trade-off preferences, and implementation approach — then presents a fait accompli for binary approve/reject. When the plan misses the user's intent, the only recourse is to reject and start over, or manually request revisions. This wastes effort and produces plans that don't reflect the user's domain knowledge and preferences.

Making planning interactive ensures the user shapes the plan from the start, resulting in higher-quality proposals that match intent on the first pass.

## What Changes

- Add a **discovery questions phase** (Step 3) where Claude presents discovered context and asks 2-5 clarifying questions before generating any artifacts
- Add **mandatory "Approaches Considered" section** to `proposal.md` template with 2-3 distinct approaches including pros/cons/effort
- Split single approval gate into **two gates**: Gate 1 (direction/approach selection) and Gate 2 (full plan approval)
- Add **`--explore` flag** for deep-dive mode with more questions (5-8), more approaches (3-5), and prior art research
- Add **"assumptions" finding type** to `/iterate-on-plan` that surfaces implicit decisions to the user via AskUserQuestion
- Add **AskUserQuestion fallback** documentation for runtimes where the tool is unavailable

## Approaches Considered

### Approach 1: Interactive gates with AskUserQuestion

Add structured interaction points using the AskUserQuestion tool at discovery, direction, and approval phases. Questions are context-aware, referencing specific discoveries from the exploration step.

- **Pros**: Uses existing tooling, provides structured options, works across all tiers
- **Cons**: Adds session length, requires AskUserQuestion availability
- **Effort**: M

### Approach 2: Conversation-based interaction (no structured tool)

Use regular output to ask questions and wait for freeform user responses.

- **Pros**: Works in all runtimes without tool dependency
- **Cons**: No structured options, harder to parse responses, less consistent experience
- **Effort**: S

### Recommended

Approach 1, with Approach 2 as documented fallback when AskUserQuestion is unavailable. This gives the best experience where possible while degrading gracefully.

### Selected Approach

Approach 1 (Interactive gates with AskUserQuestion) selected. Fallback to numbered-list output when AskUserQuestion is unavailable in the runtime.

## Impact

- **Affected specs**: `skill-workflow` (plan-feature and iterate-on-plan requirements)
- **Files modified**:
  - `skills/plan-feature/SKILL.md` — Major restructuring (10 steps → 13 steps)
  - `skills/iterate-on-plan/SKILL.md` — Add assumptions type
  - `openspec/schemas/feature-workflow/templates/proposal.md` — Add Approaches section
  - `openspec/schemas/feature-workflow/schema.yaml` — Update artifact instructions
- **Sync**: All runtime directories (`.claude/`, `.agents/`, `.codex/`, `.gemini/`) via `install.sh`
