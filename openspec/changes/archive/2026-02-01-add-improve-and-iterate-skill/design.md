## Context

The existing 3-skill workflow (plan, implement, cleanup) produces working implementations but lacks a structured refinement phase. The user has observed that 5+ rounds of "how can this be improved?" consistently uncovers significant issues. This skill codifies that pattern.

## Goals / Non-Goals

- **Goals:**
  - Provide a repeatable iterative refinement workflow as a Claude Code skill
  - Each iteration produces a discrete commit on the feature branch
  - Structured analysis categorizes findings by type and criticality
  - Early termination when remaining findings are below threshold
  - Documentation is updated with learnings from each iteration
  - Integrates cleanly with existing OpenSpec workflow

- **Non-Goals:**
  - No automated tooling or scripts (this is a pure SKILL.md instruction file, like all other skills)
  - No changes to the OpenSpec CLI itself
  - Not replacing human code review (this runs before PR review, not instead of it)
  - Not parallelizing iterations (each iteration depends on the previous one's changes)

## Decisions

- **Pure skill file (no scripts)**: Consistent with plan-feature, implement-feature, and cleanup-feature. The skill is an instruction document that guides the AI assistant through the iterative process.
  - *Alternative*: Shell script that automates the loop. Rejected because iterations require judgment (analyzing code, deciding criticality) that only the AI can provide.

- **Structured analysis format over free-form**: Each finding has type, criticality, description, and proposed fix. This makes termination logic objective (count findings above threshold) and produces a useful audit trail.
  - *Alternative*: Free-form notes per iteration. Rejected because it makes early termination subjective and audit trail inconsistent.

- **Commit per iteration (not per finding)**: One commit per iteration keeps the git history clean and makes each iteration reviewable as a unit.
  - *Alternative*: Commit per finding. Rejected as too granular—a single iteration may fix 3-5 related issues.

- **Default max 5 iterations**: Based on the user's observation that 5+ rounds typically exhausts major issues. The user can override this.

- **Criticality threshold for early stop**: Default "medium" means iterations stop when only low-criticality findings remain. The user can set "low" to stop only when zero findings remain, or "high" to stop more aggressively.

- **OpenSpec documents updated alongside project docs**: Each iteration updates not just CLAUDE.md/AGENTS.md but also the OpenSpec proposal, design, and spec files when refinement reveals spec drift. This ensures the OpenSpec records remain the source of truth throughout iterative refinement.
  - *Alternative*: Only update project docs (CLAUDE.md, AGENTS.md, docs/). Rejected because OpenSpec is the development workflow, and stale specs undermine spec-driven development.

## Risks / Trade-offs

- **Risk**: Iterations may find issues that require design changes beyond the current proposal scope.
  - *Mitigation*: The skill should flag such findings as "out of scope" and recommend creating a new OpenSpec proposal for them.

- **Risk**: The AI may produce diminishing-value findings in later iterations (increasingly subjective style preferences).
  - *Mitigation*: The criticality classification provides an objective cut-off. The default threshold of "medium" filters out low-value findings.

- **Risk**: Documentation updates every iteration may create noisy diffs.
  - *Mitigation*: Only update docs when genuinely new patterns or lessons emerge, not for minor code tweaks.

## Open Questions

- None at this time. The skill is a single instruction file following established conventions.
