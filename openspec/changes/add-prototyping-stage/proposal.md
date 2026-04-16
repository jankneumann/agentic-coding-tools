# Add Prototyping Stage

## Why

Uber's AI prototyping post (`https://www.uber.com/us/en/blog/ai-prototyping/`) documents three compounding wins when teams put **concrete, runnable artifacts** in front of stakeholders between "proposal approved" and "implementation starts":

- **Greater exploration of ideas** — 6 distinct concepts in ~20 minutes, replacing sequential iteration cycles with parallel divergence.
- **Faster alignment** — conversations move from "what is this?" to "is this the right approach?" because stakeholders interact with a working artifact rather than imagining one from a doc.
- **Unblocked execution** — scope, sequencing, and MVP questions surface **before** engineering commits, rather than at implementation kickoff.

Our current workflow inverts this pattern. We run divergence on **review** (N reviewers evaluate one artifact via `/parallel-review-plan`, `/parallel-review-implementation`) but convergence on **generation**: one proposal → one iteration → one implementation. Creative divergence happens only inside a single agent's head during `/plan-feature`, then collapses to a document before any working artifact exists. By the time we reach `/implement-feature`, the chosen approach is concrete but has never been stress-tested against alternatives.

Gap: **no stage where multiple agents build competing working skeletons from the same proposal and feed outcomes back into design refinement**. The "Approaches Considered" section in `proposal.md` is a text-only hypothetical comparison — persuasive on paper, untested in code.

This change adds that stage and wires it into the existing workflow via the refinement skill we already trust for plan evolution (`/iterate-on-plan`), rather than inventing a parallel convergence pipeline.

## What Changes

- **NEW**: `/prototype-feature <change-id> [--variants N] [--angles "a,b,c"]` (default `N=3`). Dispatches N parallel agents in isolated worktrees to build working skeletons from the approved `proposal.md`, each steered by a distinct **angle prompt** (default angles: `simplest`, `extensible`, `pragmatic`). Vendor-diverse best-effort with single-vendor fallback using prompt-steering + temperature/seed variation.
- **NEW**: `prototype-findings.md` artifact — records variant descriptors, automated scores (from `/validate-feature --phase smoke,spec`), and human pick-and-choose selections across variants.
- **EXTENDED**: `/iterate-on-plan` accepts a `--prototype-context <change-id>` flag. When present, the skill loads `prototype-findings.md`, variant diffs, and validation reports alongside existing proposal/design/tasks context, and performs **convergence-aware refinement** of `design.md` and `tasks.md`. Finding types expand to include `convergence.*` (e.g., `convergence.prefer-variant-X`, `convergence.merge-A-data-model-with-B-api`).
- **EXTENDED**: `skills/worktree/scripts/worktree.py` supports a `prototype/<change-id>/v<n>` branch prefix. Variants compose with the existing `--agent-id` suffix scheme (`--v1`, `--v2`, ...).
- **EXTENDED**: `skills/parallel-infrastructure/` consensus synthesizer schema gains a `VariantDescriptor` type (distinct from `ReviewFinding`) — captures `variant_id`, `angle`, `vendor`, automated scores, human pick metadata, and suggested synthesis hints.
- **EXTENDED**: `/cleanup-feature` deletes prototype branches (`prototype/<change-id>/v*`) alongside the feature branch.
- **OPT-IN GATING**: `/iterate-on-plan` MAY emit a `workflow.prototype-recommended` finding when clarity or feasibility findings exceed a threshold (default: ≥3 high-criticality in those dimensions). Never auto-triggers `/prototype-feature`. User invocation is always primary.
- **UPDATED**: `docs/skills-workflow.md` — documents the new optional stage and adds a design principle *"Divergence is first-class on both sides of the approval gate"*.
- **UPDATED**: `CLAUDE.md` — workflow diagram gains the optional `/prototype-feature` stage between `/plan-feature` and `/implement-feature`.

### Selected Approach

**Approach 2: Iterate-on-plan as convergence** (user-selected, confirmed at Gate 1).

`/iterate-on-plan` already loads proposal artifacts, applies structured finding detection, iterates to fixed point, and commits refinements. Extending its context-loading to also consume prototype outcomes reuses the iteration loop, finding types, and commit conventions rather than duplicating them in a separate skill. Convergence becomes a **mode** of iterate-on-plan, not a new skill.

### Approaches Considered

**Approach 1: Dedicated `/synthesize-prototypes` skill**
- **Description**: New skill independent of iterate-on-plan. Reads `prototype-findings.md` + variant diffs and directly rewrites `design.md` + `tasks.md`.
- **Pros**: Clear single-responsibility boundary; prototype-specific logic stays localized; easier to deprecate if the pattern doesn't prove out.
- **Cons**: Duplicates iterate-on-plan's finding-detection, commit-convention, and iteration-loop machinery. Two skills doing structurally similar work drift apart over time. Two separate `git log` trails for design refinement.
- **Effort**: M

**Approach 2: Iterate-on-plan as convergence** — **SELECTED**
- **Description**: Existing `/iterate-on-plan` gains `--prototype-context <change-id>` flag. When present, it loads prototype outcomes as additional context and performs convergence-aware refinement.
- **Pros**: Reuses proven refinement loop; prototype outcomes become a natural context slot alongside review findings; single commit history for design refinement regardless of input source; minimal new surface area.
- **Cons**: Modest context-loading change in iterate-on-plan; slightly broader responsibility for a single skill.
- **Effort**: S

**Approach 3: Inline synthesis inside `/prototype-feature`**
- **Description**: The skill that generates variants also synthesizes them.
- **Pros**: Single invocation; fewer moving parts.
- **Cons**: Mixes generation and refinement concerns — different creative activities with different failure modes. Re-synthesizing after human feedback requires re-dispatching variants. Violates the workflow's established "creative vs mechanical" separation.
- **Effort**: M

**Recommended**: Approach 2 (selected). Matches user's explicit request and preserves iterate-on-plan's established role as the "improve-a-plan" skill.

## Impact

- **Affected specs**: `skill-workflow` (new ADDED requirements for prototyping stage; MODIFIED requirements for iterate-on-plan convergence mode)
- **Affected code**:
  - **NEW**: `skills/prototype-feature/SKILL.md`, `skills/prototype-feature/scripts/dispatch_variants.py`, `skills/prototype-feature/scripts/collect_outcomes.py`
  - **MODIFIED**: `skills/iterate-on-plan/SKILL.md` (convergence mode step), `skills/iterate-on-plan/scripts/` (prototype context loader)
  - **MODIFIED**: `skills/worktree/scripts/worktree.py` (prototype branch prefix)
  - **MODIFIED**: `skills/parallel-infrastructure/` (VariantDescriptor schema, consensus synthesizer support)
  - **MODIFIED**: `skills/cleanup-feature/SKILL.md` (prototype branch cleanup step)
  - **MODIFIED**: `docs/skills-workflow.md`, `CLAUDE.md`
- **Operational defaults**:
  - Default variant count: **3** (configurable via `--variants`)
  - Vendor policy: **best-effort diversity with single-vendor fallback** (prompt-steered + temperature/seed variation)
  - Branch retention: **kept until `/cleanup-feature`**
- **Cost model**: Opt-in only. N variants × skeleton size = additional LLM spend per change that runs the stage. Cheap-validation phases only (smoke, spec-compliance) keep scoring cost bounded.
- **Non-goals** (out of scope for this change):
  - Non-engineer (PM, sales, ops) self-service invocation — Uber's "opened up beyond product teams" requires runnable deployment artifacts, not PR diffs. Deferred to a future proposal.
  - Runnable deployment of variants (Preview URLs per variant). Deferred.
  - Automatic prototype-stage triggering. Always user-invoked or gated by an iterate-on-plan suggestion finding.
