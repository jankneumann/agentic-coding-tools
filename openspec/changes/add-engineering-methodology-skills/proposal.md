# Add Engineering Methodology Skills

## Why

Our skills repo is **vertical** — each skill orchestrates a phase of a multi-agent feature lifecycle (plan → implement → validate → cleanup). It is excellent at coordination but light on **horizontal** engineering methodology: there is no skill that codifies *how* to do TDD, *how* to debug, *how* to engineer context for an agent, *how* to design an API, *how* to ship a feature with staged rollout. When orchestrators dispatch work, agents fall back on training-data heuristics for these decisions, which produces inconsistent quality.

A 20-skill external library (`addyosmani/agent-skills`) provides exactly this missing horizontal layer: per-topic methodology with uniform `Common Rationalizations / Red Flags / Verification` tail blocks, shared reference checklists, and tight cross-references. After auditing all 20, ten fill clear methodology gaps in our framework, eight contain patterns that should be cross-pollinated into existing local skills, one (`spec-driven-development`) is already covered by OpenSpec and is skipped, and `ci-cd-and-automation` overlaps `validate-feature` enough that only its config templates are worth pulling on demand.

This change ships those ten new skills, extracts the eight high-value patterns into existing skills, introduces a shared `skills/references/` library, adds a `related:` frontmatter key for cross-skill graph rendering, and makes the *Common Rationalizations / Red Flags / Verification* tail block mandatory for all user-invocable skills.

The result: orchestrators can auto-load methodology when relevant (e.g., `implement-feature` loads `test-driven-development` when test tasks exist), operators can invoke methodology ad-hoc via slash commands when relevant, and every skill predicts its own failure modes via a uniform tail.

## What Changes

### New skills (10)

Ten net-new methodology skills under `skills/<name>/`, each ported from `addyosmani/agent-skills` with our richer frontmatter schema. Original JS/TS examples preserved; Python/pytest/our-stack examples added alongside. Each ships with the `Common Rationalizations / Red Flags / Verification` tail block built in from day one.

| # | Skill | `user_invocable` | Why this `user_invocable` value |
|---|---|---|---|
| 1 | `test-driven-development` | `true` | Operators trigger ad-hoc (`/tdd`) when writing tests; also auto-loaded by `implement-feature` when test tasks exist |
| 2 | `debugging-and-error-recovery` | `true` | Operator-triggered when debugging; auto-loaded by `fix-scrub` |
| 3 | `context-engineering` | `false` | Orchestrator-only concern (agents load it when packing context for sub-agents); not a slash-command |
| 4 | `source-driven-development` | `false` | Auto-loaded when agent encounters framework-specific code that may have drifted past its training cutoff |
| 5 | `performance-optimization` | `true` | Operator-triggered for explicit perf work |
| 6 | `frontend-ui-engineering` | `true` | Operator-triggered when working on UI |
| 7 | `api-and-interface-design` | `true` | Operator-triggered when designing/reviewing an API |
| 8 | `browser-testing-with-devtools` | `false` | Auto-loaded by `validate-feature` smoke phase; tightly bound to Chrome DevTools MCP |
| 9 | `deprecation-and-migration` | `true` | Operator-triggered workflow when removing legacy code |
| 10 | `documentation-and-adrs` | `true` | Operator-triggered for ADR authoring |

**Localization rule**: keep each external skill's existing JS/TS examples; *add* Python/pytest/FastAPI/pydantic equivalents alongside. Stripping examples would lose information for cross-stack readers.

### Adaptations to existing skills (8)

Specific patterns extracted from external skills into the named local skill. Each ADAPT touches only one or two existing files; the tail-block addition (cross-cutting change C below) is folded into the same edit pass to avoid double-touching files.

| External skill | Local target | Patterns extracted |
|---|---|---|
| `incremental-implementation` | `implement-feature/SKILL.md` | Rules 0–5 framing (Simplicity / Scope Discipline / One Thing / Compilable / Feature Flags / Safe Defaults / Rollback); `NOTICED BUT NOT TOUCHING:` template injected into work-package execution prompts |
| `code-review-and-quality` | `parallel-review-plan/SKILL.md`, `parallel-review-implementation/SKILL.md`, `parallel-infrastructure/schemas/review-findings.schema.json` | 5-axis review schema (Correctness / Readability / Architecture / Security / Performance); 5 severity prefixes (Critical / Nit / Optional / FYI / none) — schema fields become required |
| `code-simplification` | `simplify/SKILL.md` | Chesterton's Fence pre-check; "Rule of 500" (>500 lines → automate); pattern catalog (deep nesting, long functions, nested ternaries, boolean flags, generic names, premature abstractions) |
| `security-and-hardening` | `security-review/SKILL.md` (extends, doesn't replace runner) | Three-tier boundary system (Always / Ask first / Never); OWASP Top 10 prevention rules — added as "preventive mode" alongside existing Dependency-Check + ZAP runner |
| `planning-and-task-breakdown` | `plan-feature/SKILL.md` | XS/S/M/L/XL task sizing; "title contains 'and' → split signal"; explicit checkpoint cadence (every 2–3 tasks) |
| `shipping-and-launch` | `cleanup-feature/SKILL.md` | 5%→25%→50%→100% staged rollout; rollback triggers (errors >2× baseline, p95 +50%, integrity, security); pre-launch checklist phase |
| `git-workflow-and-versioning` | `merge-pull-requests/SKILL.md`, `CLAUDE.md` (light pull) | Save Point Pattern; Change Summary template (CHANGES MADE / DIDN'T TOUCH / CONCERNS) |
| `idea-refine` | `explore-feature/SKILL.md`, `openspec-explore` | "How Might We" reframing prompt; 8 ideation lenses; explicit `NOT DOING:` list as a discovery output |

### Cross-cutting structural changes (4)

**A. Shared `skills/references/` library.** New top-level directory containing `security-checklist.md`, `performance-checklist.md`, `accessibility-checklist.md`, `testing-patterns.md`. Multiple skills cite these instead of duplicating checklists. `install.sh` extended to rsync `references/` alongside skill directories.

**B. `related:` frontmatter key.** Net-new YAML list field following the `requires:` precedent. Any skill can declare related skills for cross-reference. `install.sh` validates that `related:` entries point to skills that exist; the rendered skills graph (future enhancement) consumes this field.

**C. Uniform tail block convention.** Every user-invocable skill must end with three sub-sections in this order:
- *Common Rationalizations* — table of "I'll skip X because Y" → "actually do X because Z"
- *Red Flags* — bullet list of observable signals the skill is being violated
- *Verification* — numbered checklist a reviewer/agent runs to confirm the skill was applied

Applied in this change to **21 skills**: 3 pilots (`simplify`, `bug-scrub`, `tech-debt-analysis`) + 10 new methodology skills (built in from day one) + 8 ADAPT targets (folded into adaptation edit pass). Infrastructure skills (`user_invocable: false`) exempt — they're loaded by other skills, not directly executed by agents.

**D. Frontmatter schema preserved.** Our existing schema (`name`, `description`, `category`, `tags`, `triggers`, `requires`, `user_invocable`) is kept verbatim — `addyosmani/agent-skills`'s minimal `name + description` form would lose `triggers` (skill discovery), `requires` (coordinator gating), and `user_invocable` (auto vs explicit). Adopt their content, keep our schema.

### Test infrastructure

Each new and edited skill gets a test directory under `skills/tests/<skill-name>/` with three layers:

1. **Frontmatter parse**: YAML loads cleanly; required keys present.
2. **Cross-reference resolution**: every `references/<file>.md` and every `related:` target referenced by the SKILL.md exists.
3. **Content invariants**: every user-invocable skill has the three tail-block sections; every claim of "see references/X" resolves; the tail-block sections appear in correct order.

`skills/pyproject.toml` `testpaths` updated to enumerate the new test dirs.

### Explicit non-goals

- **`spec-driven-development` as a standalone skill** — OpenSpec covers it. Optional: lift `ASSUMPTIONS I'M MAKING:` template + three-tier scope boundary framing into the proposal template as text only. Not a new skill.
- **`ci-cd-and-automation` as a full skill** — overlaps `validate-feature`. Pull only preview-deploy + dependabot config templates if/when we author CI from a skill. Out of scope here.
- **CI lint rule for tail block** — deferred to a follow-up. The test-layer invariants in this change cover the *content*; CI enforcement of the *convention* on new skills authored after this change can be a small follow-up.
- **Skills graph rendering** — `related:` frontmatter is added now; a CLI/HTML renderer that visualizes the graph is deferred.

## Approaches Considered

### Approach A: Big-bang sequential

One agent walks the full work in a single linear sequence: scaffold (`references/`, `install.sh`, `related:`, `pyproject.toml`) → 10 new skills → 8 adaptations + tail block in same pass → 3 pilot tail-block backfills → tests → docs. One worktree, one branch, one PR.

**Pros:**
- Simplest mental model; no work-package coordination
- Single PR review surface
- No risk of inter-package conflicts

**Cons:**
- Slowest (~5–7 days single-agent execution)
- Doesn't use the coordinator's parallel capabilities, which are explicitly available here
- A failure mid-sequence forces a long replay
- Long single review cycle compounds reviewer fatigue

**Effort: L**

### Approach B: Parallel by phase, fan-out per phase

One OpenSpec change with four explicit phases as work-package strata. Phase boundaries are sequential gates; within a phase, packages run in parallel.

- **Phase 0 — Scaffold (sequential, 1 agent):** `skills/references/` + 4 checklist files + `install.sh` extension for `references/` rsync + `related:` frontmatter validation + tail-block convention doc in `skills-workflow.md` + `pyproject.toml` testpaths placeholder for new skills.
- **Phase 1 — New skills (parallel, ~4 agents, 10 skills):** topical clusters (testing/quality, knowledge, engineering practices, lifecycle/governance). Each cluster owns ~2–3 SKILL.md files, written WITH tail block built in, plus their `skills/tests/<name>/` dirs.
- **Phase 2 — Adaptations + tail block (parallel, ~3 agents, 8 ADAPT targets + 3 pilots):** clustered by target type (lifecycle skills / review skills / sync-points & meta). Each agent edits its assigned skills once: applies the extracted patterns AND the tail block in the same pass.
- **Phase 3 — Test invariants & integration (sequential, 1 agent):** content-invariant test framework added under `skills/tests/_shared/`, `pyproject.toml` finalization, full `install.sh --mode rsync` dry run, `openspec validate --strict`, docs update.

**Pros:**
- Maximizes coordinator-tier parallelism (3–4× wall-clock speedup over A)
- Phase gates create natural review checkpoints
- Fault-isolated: a Phase 1 cluster failing doesn't block other clusters
- Each ADAPT target touched exactly once (adaptation + tail block in one pass)

**Cons:**
- Most work-package YAML to author (~9 packages including `wp-contracts` stub and `wp-integration`)
- Parallel agents need coordinated lock keys on the shared `references/` and `pyproject.toml` files
- Phase gates add some scheduling overhead

**Effort: L**

### Approach C: Scaffold-then-content (recommended)

Same artifacts as Approach B, but with an explicit ordering invariant: **the convention must exist before the skills that follow it.** Phase 0 ships the convention (tail-block template, `references/` library, `related:` frontmatter, content-invariant test framework). Every subsequent phase inherits the convention rather than backfilling it.

- **Phase 0 — Convention (sequential, 1 agent):** Phase 0 of Approach B PLUS the content-invariant test framework + `skills-workflow.md` "tail block" canonical doc + a tail-block template under `skills/references/skill-tail-template.md` that new skills include via copy-paste.
- **Phase 1 — New skills (parallel, ~4 agents, 10 skills):** identical to Approach B Phase 1, but each new skill is born with the canonical tail-block. No backfill needed for these.
- **Phase 2 — Adaptations + tail block (parallel, ~3 agents, 8 ADAPT + 3 pilots):** identical to Approach B Phase 2, but the canonical tail-block template is copy-pasted in (consistency).
- **Phase 3 — Integration (sequential, 1 agent):** identical to Approach B Phase 3.

**Pros:**
- Strongest consistency guarantee — every skill written or edited in Phases 1–2 has access to the canonical tail-block template, so all 21 skills get *byte-identical* tail-block scaffolding (only content differs)
- Content-invariant tests exist before content lands → red/green discipline (Phase 1+2 packages explicitly produce passing tests)
- Same parallelism as Approach B

**Cons:**
- Phase 0 grows by ~3–5 tasks vs. Approach B (template authoring, test framework)
- Phase 1+2 agents have a hard dependency on Phase 0 completion (true for Approach B too, but more visible here)

**Effort: L**

## Selected Approach

**Approach C — scaffold-then-content** (operator-confirmed at Gate 1).

Phase 0 is sequential and ships the convention before any content lands:
- `skills/references/` library with the four checklist files
- `skills/install.sh` extension to rsync `references/` and validate `related:` frontmatter
- `skills/references/skill-tail-template.md` — canonical copy-paste template for the Common Rationalizations / Red Flags / Verification block
- `skills/tests/_shared/conftest.py` — the content-invariant test framework (frontmatter parse, cross-reference resolution, tail-block presence)
- `skills/pyproject.toml` `testpaths` updated with placeholders for all 10 new skill test dirs
- `docs/skills-workflow.md` updated with the canonical tail-block convention

Phases 1 and 2 fan out in parallel work packages and inherit the convention. Phase 3 is integration: full `install.sh` dry-run, `openspec validate --strict`, docs sync.

No modifications to the proposal scope from operator: SINGLE OpenSpec change, per-skill `user_invocable` decisions as listed in the table above (3 false / 7 true), JS/TS examples preserved with Python equivalents added, frontmatter schema preserved.

### Approach B and Approach A (not selected)

- **Approach B (parallel by phase, no template)** — same parallelism as C, but tail-block content is authored individually by each Phase 1+2 agent. Higher risk of stylistic drift across the 21 skills; needs a Phase 3 consistency sweep. C wins by ~3–5 Phase 0 tasks for guaranteed consistency.
- **Approach A (big-bang sequential)** — single agent walks all work end-to-end. Simplest but doesn't use the available coordinator parallelism; ~5–7 days wall-clock. Rejected because the coordinator is fully available and parallelism is essentially free here.
