# Design: interactive-plan-feature

## Context

The `/plan-feature` skill is a 9-step pipeline that takes a feature description and produces OpenSpec proposal artifacts (proposal.md, specs, tasks.md, design.md, and optionally contracts + work-packages). The user's only interaction points are the initial invocation and a final binary approval gate. All design decisions between those points are made autonomously by Claude based on codebase context.

The `/iterate-on-plan` skill performs automated quality review across 7 finding types but does not identify or surface unstated assumptions.

## Goals / Non-Goals

**Goals:**
- Make planning interactive so users shape proposals from the start
- Ensure Claude explores multiple approaches before committing to one
- Surface implicit assumptions for explicit user decisions
- Preserve existing tier selection and parallel execution capabilities

**Non-Goals:**
- Changing the implementation or cleanup skills
- Adding new executable scripts or Python code
- Modifying the coordinator integration or lock mechanisms
- Changing the work-packages or contracts generation logic

## Decisions

### Decision 1: Three-stop interaction model

Insert interaction at three points: discovery (before artifacts), direction (after proposal, before specs/tasks), and approval (after all artifacts).

**Alternative considered**: Single enriched approval gate with revision options. Rejected because it still generates full artifacts before the user can redirect approach, wasting effort when the direction is wrong.

**Alternative considered**: Continuous interaction (ask after every artifact). Rejected because it would make planning excessively slow and interrupt flow for straightforward features.

### Decision 2: AskUserQuestion with output fallback

Use AskUserQuestion tool for structured interaction. Document a fallback to numbered lists in regular output for runtimes where the tool is unavailable.

**Alternative considered**: Only use regular output (no AskUserQuestion). Rejected because structured options provide a better UX and are more parseable.

### Decision 3: Mandatory Approaches section in proposal.md

Make "Approaches Considered" a required section in the proposal template rather than only in the optional design.md.

**Alternative considered**: Keep approaches in design.md only. Rejected because design.md is optional and only created for complex changes, but approach exploration benefits all features.

### Decision 4: Assumptions as a finding type in iterate-on-plan

Add "assumptions" alongside existing types (completeness, clarity, etc.) rather than creating a separate review pass.

**Alternative considered**: Separate "assumption review" step. Rejected because it duplicates the iteration infrastructure and assumptions are naturally discovered alongside other finding types.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|------|----------|------------|
| Longer planning sessions due to interaction | Medium | Default to 2-5 questions (not excessive); `--explore` opt-in for deeper exploration |
| AskUserQuestion not available in all runtimes | Low | Documented fallback to numbered-list output |
| Users may find questions annoying for simple features | Low | Questions reference specific discoveries, making them clearly relevant; can always approve defaults quickly |
| Step renumbering may confuse existing documentation | Low | Verified no external references to plan-feature step numbers |

## Migration Plan

No migration needed — this is a skill instruction change only. The modified skill files are synced to all runtime directories via `install.sh`. No database, API, or configuration changes. The proposal.md template change affects new proposals only; existing archived proposals are not modified.
