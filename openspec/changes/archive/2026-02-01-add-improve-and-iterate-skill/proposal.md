# Change: Add improve-and-iterate skill for iterative refinement after implementation

## Why

After `/implement-feature` produces a working implementation and PR, there is no structured way to systematically improve it. In practice, asking "how can this be further improved?" 5+ times reveals bugs, missed edge cases, workflow issues, and performance/UX problems that the initial implementation missed. Currently this refinement is ad-hoc and undocumented. A dedicated skill codifies this pattern into a repeatable, auditable workflow where each iteration is a discrete commit with updated documentation.

## What Changes

- **New skill**: `improve-and-iterate/SKILL.md` in the `skills/` directory
- **New capability spec**: `skill-workflow` to document the skill lifecycle including the new iterative refinement stage
- The skill fits between `/implement-feature` and `/cleanup-feature` in the existing workflow:
  ```
  /plan-feature → /implement-feature → /improve-and-iterate → /cleanup-feature
  ```

### Skill Behavior

1. **Input**: Change-id (or detect from current branch), optional max iteration count (default: 5), optional criticality threshold (default: "medium")
2. **Per-iteration loop**:
   - Review proposal, design, tasks, and current implementation code
   - Produce a structured improvement analysis categorizing findings by type (bug, edge case, workflow, performance, UX) and criticality (critical, high, medium, low)
   - If only low-criticality findings remain and criticality threshold is "medium" or above, stop early
   - Otherwise, implement all identified improvements
   - Run quality checks (tests, lint, type checks)
   - Commit the iteration's changes with a descriptive message referencing the iteration number
   - Update CLAUDE.md, AGENTS.md, or docs/ with lessons learned from the iteration
   - Update relevant OpenSpec documents (proposal.md, design.md, spec deltas) when findings reveal spec drift, incorrect assumptions, or missing requirements
3. **Termination**: When max iterations reached OR only findings below the criticality threshold remain
4. **Output**: Summary of all iterations, total findings addressed, and final state

### Criticality Levels

- **Critical**: Security vulnerabilities, data loss, crashes, incorrect core behavior
- **High**: Unhandled error paths, missing validation at system boundaries, race conditions
- **Medium**: Missing edge cases, suboptimal error messages, incomplete logging
- **Low**: Code style, minor naming, documentation polish, minor performance

## Impact

- Affected specs: `skill-workflow` (new capability)
- Affected code: `skills/improve-and-iterate/SKILL.md` (new file)
- Affected docs: CLAUDE.md workflow section will reference the new 4-skill workflow
- Affected OpenSpec docs: proposal.md, design.md, and spec deltas for the current change are updated when iterations reveal spec drift
