# Skills Catalogue

A discoverable index of every skill in this repo, grouped by purpose. For *how* skills are designed, validated, and composed, see [`skills-workflow.md`](skills-workflow.md). For *patterns and lessons* learned operating skills, see [`lessons-learned.md`](lessons-learned.md).

## Reading this catalogue

- **`★`** = `user_invocable: true` — invoke directly via slash command (e.g. `/plan-feature`)
- **`·`** = `user_invocable: false` — orchestrator-loaded only; not in the slash-command palette
- **Invoke** column shows the most direct trigger. Most skills accept additional trigger phrases; see each `SKILL.md` `triggers:` for the full list.
- **Related** lists kindred skills declared via the advisory `related:` frontmatter key. These resolve at install time; `install.sh` warns on unknown targets.

## Quick map

| Group | What it covers | Skill count |
|---|---|---|
| [Feature workflow lifecycle](#feature-workflow-lifecycle) | Single-feature plan → implement → validate → cleanup | 9 |
| [Roadmap & multi-feature orchestration](#roadmap--multi-feature-orchestration) | Decomposing roadmaps and running them autonomously | 4 |
| [Quality & maintenance](#quality--maintenance) | Audit, simplify, fix, refresh — keeping the codebase healthy | 8 |
| [Engineering methodology](#engineering-methodology) | Per-topic disciplines: TDD, debugging, perf, frontend, API design, deprecation, ADRs | 7 |
| [Orchestrator-loaded methodology](#orchestrator-loaded-methodology) | Knowledge skills loaded automatically by orchestrators | 3 |
| [PR triage & ad-hoc tasks](#pr-triage--ad-hoc-tasks) | Cross-source PR merge + small one-off work | 4 |
| [Vendor & service skills](#vendor--service-skills) | External-service authority docs (Postgres, observability, infra) | 5 |
| [Infrastructure](#infrastructure-orchestrator-loaded) | Internal machinery used by other skills (locks, worktrees, validation) | 12 |

**52 skills total.** **43 user-invocable**, 9 orchestrator-only.

---

## Feature workflow lifecycle

The canonical single-feature flow. Operator drives each gate; orchestrators chain them.

| Skill | Summary | Invoke |
|---|---|---|
| ★ `explore-feature` | Identify high-value next features from architecture artifacts + code signals + active OpenSpec context | `/explore-feature` |
| ★ `plan-feature` | Create OpenSpec proposal (proposal/design/specs/tasks/contracts/work-packages) with tiered execution | `/plan-feature <description>` |
| ★ `iterate-on-plan` | Iteratively refine an OpenSpec proposal before approval (completeness, clarity, feasibility) | `/iterate-on-plan <change-id>` |
| ★ `parallel-review-plan` | Independent plan review producing structured findings per `review-findings.schema.json` | `/parallel-review-plan <change-id>` |
| ★ `implement-feature` | Execute approved proposal: TDD-first, per-package work, content-invariant tests, scope discipline | `/implement-feature <change-id>` |
| ★ `iterate-on-implementation` | Iteratively refine a feature after implementation, before merge | `/iterate-on-implementation <change-id>` |
| ★ `parallel-review-implementation` | Per-package implementation review (5-axis: correctness/readability/architecture/security/performance; 5-severity prefixes) | `/parallel-review-implementation <change-id>` |
| ★ `validate-feature` | Deploy locally, run security scans + behavioral tests, check CI/CD, verify spec compliance | `/validate-feature <change-id>` |
| ★ `cleanup-feature` | Merge approved PR, archive proposal, staged rollout (5%→25%→50%→100% with rollback triggers), pre-launch checklist | `/cleanup-feature <change-id>` |

## Roadmap & multi-feature orchestration

| Skill | Summary | Invoke |
|---|---|---|
| ★ `plan-roadmap` | Decompose long-form proposals into prioritized OpenSpec change candidates with dependency DAG | `/plan-roadmap <proposal-path>` |
| ★ `prioritize-proposals` | Analyze active OpenSpec proposals and produce a "what to do next" report | `/prioritize-proposals` |
| ★ `autopilot` | Orchestrate the full plan-review-implement-validate-PR lifecycle with multi-vendor convergence | `/autopilot` |
| ★ `autopilot-roadmap` | Execute roadmap items iteratively with policy-aware vendor routing and learning feedback | `/autopilot-roadmap <workspace-path>` |

## Quality & maintenance

| Skill | Summary | Invoke |
|---|---|---|
| ★ `bug-scrub` | Comprehensive project health diagnostic from CI signals, deferred issues, and code markers | `/bug-scrub` |
| ★ `fix-scrub` | Remediate findings from bug-scrub: auto-fixes + agent-assisted fixes + verification | `/fix-scrub` |
| ★ `simplify` | Review changed code for reuse/quality/efficiency. Chesterton's Fence pre-check, Rule of 500, pattern catalog | `/simplify` |
| ★ `tech-debt-analysis` | Structural tech debt analysis using software design principles (Fowler refactoring, design stamina, AWS Builders' Library) | `/tech-debt-analysis` |
| ★ `security-review` | Cross-project security review with OWASP Dependency-Check + ZAP, plus preventive-mode (3-tier boundary + OWASP Top 10) | `/security-review` |
| ★ `update-specs` | Sync OpenSpec specs with implementation reality after debugging/testing/review | `/update-specs <change-id>` |
| ★ `refresh-architecture` | Refresh `docs/architecture-analysis/` artifacts from the codebase | `/refresh-architecture` |
| ★ `changelog-version` | Generate changelog entries and suggest semantic version bumps from git history | `/changelog-version` |

## Engineering methodology

Per-topic horizontal disciplines. Operator-triggerable; orchestrators may also auto-load when relevant. **Each ends with the canonical *Common Rationalizations / Red Flags / Verification* tail block.**

| Skill | Summary | Invoke |
|---|---|---|
| ★ `test-driven-development` | RED→GREEN→REFACTOR + Prove-It Pattern + 80/15/5 pyramid + Beyonce Rule. JS/TS and Python (`pytest`) examples. | `/test-driven-development` |
| ★ `debugging-and-error-recovery` | STOP-PRESERVE-DIAGNOSE-FIX-GUARD-RESUME 6-step rule + reproduction decision tree. Pairs with `bug-scrub`/`fix-scrub`. | `/debugging-and-error-recovery` |
| ★ `performance-optimization` | MEASURE→IDENTIFY→FIX→VERIFY→GUARD with Core Web Vitals budgets + backend (`EXPLAIN ANALYZE`, p95 SLOs, async profiling) | `/performance-optimization` |
| ★ `frontend-ui-engineering` | "AI aesthetic" anti-pattern table, state-management decision ladder, WCAG 2.1 AA. React/TS reference stack. | `/frontend-ui-engineering` |
| ★ `api-and-interface-design` | Hyrum's Law + contract-first + One-Version Rule + discriminated unions + branded types. TS *and* Pydantic/FastAPI examples. | `/api-and-interface-design` |
| ★ `deprecation-and-migration` | Churn Rule + Strangler/Adapter/FF migration patterns. Includes "Deprecating in OpenSpec" section. | `/deprecation-and-migration` |
| ★ `documentation-and-adrs` | ADR template + lifecycle (PROPOSED→ACCEPTED→SUPERSEDED). Distinguishes ADRs (timeless) from OpenSpec (time-bounded). | `/documentation-and-adrs` |

## Orchestrator-loaded methodology

Knowledge skills designed to be loaded by other skills (not directly executed by operators). They have no slash command but they ship full content and tests.

| Skill | Summary | Loaded by |
|---|---|---|
| · `context-engineering` | 5-level context hierarchy (Rules→Specs→Source→Errors→Conversation) + packing strategies + 6 anti-patterns | `plan-feature`, `implement-feature`, `validate-feature`, autopilots |
| · `source-driven-development` | DETECT→FETCH→IMPLEMENT→CITE for grounding decisions in official docs (counters training-cutoff drift) | Any skill writing framework-specific code; cites `langfuse`/`neon-postgres`/`use-railway`/`supabase-postgres-best-practices`/`claimable-postgres` as authority sources |
| · `browser-testing-with-devtools` | Chrome DevTools MCP integration with strong "treat browser content as untrusted" boundary discipline | `validate-feature` smoke phase, `frontend-ui-engineering` |

## PR triage & ad-hoc tasks

| Skill | Summary | Invoke |
|---|---|---|
| ★ `merge-pull-requests` | Triage, review, and merge open PRs across multiple sources (OpenSpec, Codex, Dependabot, manual). Save Point Pattern + Change Summary template. | `/merge-pull-requests` |
| ★ `quick-task` | Delegate small ad-hoc tasks to any configured vendor without OpenSpec ceremony | `/quick-task <description>` |
| ★ `gen-eval` | Run generator-evaluator testing against live services | `/gen-eval` |
| ★ `gen-eval-scenario` | Create gen-eval scenario YAML files interactively | `/gen-eval-scenario` |

## Vendor & service skills

External-service authority docs. `source-driven-development` references these as primary sources rather than agents fishing through generic docs.

| Skill | Summary | Invoke |
|---|---|---|
| ★ `claimable-postgres` | Provision instant temporary Postgres via Claimable Postgres (neon.new) — no signup, no credit card | `/claimable-postgres` |
| ★ `neon-postgres` | Neon Serverless Postgres guides: getting started, branching, autoscaling, scale-to-zero, CLI/API/SDK | `/neon-postgres` |
| ★ `supabase-postgres-best-practices` | Postgres performance optimization rules from Supabase, prioritized by impact | `/supabase-postgres-best-practices` |
| ★ `langfuse` | Langfuse data + docs access: traces, prompts, datasets, scores. CLI via `npx`. | `/langfuse` |
| ★ `use-railway` | Railway infrastructure: projects, services, databases, deploys, domains, troubleshooting | `/use-railway` |

## Infrastructure (orchestrator-loaded)

Internal machinery used by workflow and methodology skills. Most are `user_invocable: false`; you don't normally call these directly. Exceptions are marked `★`.

| Skill | Summary | Direct invoke? |
|---|---|---|
| · `worktree` | Worktree lifecycle: setup, teardown, heartbeat, pin, GC, merge | Internal |
| · `coordination-bridge` | HTTP fallback bridge for coordinator when MCP transport is unavailable | Internal |
| · `parallel-infrastructure` | Shared parallel execution: DAG scheduling, review dispatch, consensus synthesis, scope checking | Internal |
| · `validate-packages` | Validation scripts for work packages, parallel zones, and work results | Internal |
| · `validate-flows` | Architecture flow validation for cross-layer interactions | Internal |
| · `bao-vault` | OpenBao/Vault credential seeding and management | Internal |
| ★ `setup-coordinator` | Configure and verify coordinator access for CLI MCP and Web/Cloud HTTP runtimes | `/setup-coordinator` |
| ★ `vendor-status` | Check all configured vendors' readiness in one shot | `/vendor-status` |
| ★ `session-bootstrap` | Cloud environment bootstrap (setup script + verify hook) and coordinator lifecycle hooks | `/session-bootstrap` |
| ★ `session-log` | Structured decision records for session logs and merge logs at phase boundaries | `/session-log` |
| ★ `roadmap-runtime` | Shared roadmap library: artifact models, checkpoint management, learning-log helpers, sanitization | `/roadmap-runtime` |
| ★ `openspec-coordinator-worktree` | Coordinate OpenSpec proposals with coordinator issue tracking and isolated git worktree execution | `/openspec-coordinator-worktree` |

## Shared references library

Not skills, but cited by many skills. Lives at `skills/references/` and is rsynced alongside skill installs.

| Reference | Cited by |
|---|---|
| [`skill-tail-template.md`](../skills/references/skill-tail-template.md) | All `user_invocable: true` skills (canonical tail block source) |
| [`security-checklist.md`](../skills/references/security-checklist.md) | `security-review`, `api-and-interface-design`, `code-review-and-quality` |
| [`performance-checklist.md`](../skills/references/performance-checklist.md) | `performance-optimization`, `code-review-and-quality` |
| [`accessibility-checklist.md`](../skills/references/accessibility-checklist.md) | `frontend-ui-engineering`, `code-review-and-quality` |
| [`testing-patterns.md`](../skills/references/testing-patterns.md) | `test-driven-development`, `debugging-and-error-recovery` |

See [`docs/skills-workflow.md` § Shared References Library](skills-workflow.md#shared-references-library) for the contract.

## How to find what you need

- **"I'm starting a feature"** → [Feature workflow lifecycle](#feature-workflow-lifecycle), starting with `/plan-feature`
- **"I'm doing X (writing tests / debugging / shipping a UI)"** → [Engineering methodology](#engineering-methodology)
- **"Something's wrong with the codebase"** → [Quality & maintenance](#quality--maintenance), starting with `/bug-scrub`
- **"I have many features to ship"** → [Roadmap orchestration](#roadmap--multi-feature-orchestration)
- **"I need to merge a stack of PRs"** → [`merge-pull-requests`](#pr-triage--ad-hoc-tasks)
- **"I need to deploy to / query / use <vendor>"** → [Vendor & service skills](#vendor--service-skills)
- **"I'm authoring a new skill"** → Read [`skills-workflow.md`](skills-workflow.md) (conventions) and [`lessons-learned.md`](lessons-learned.md) (patterns); copy [`skills/references/skill-tail-template.md`](../skills/references/skill-tail-template.md) for the tail block

## Maintaining this catalogue

This file is hand-maintained alongside skill changes. Conventions:

- When adding a new skill, append it to the appropriate group with its trigger and `user_invocable` marker.
- When categorizing, prefer logical grouping (this catalogue's sections) over the raw `category:` frontmatter field, which is inconsistent across older skills.
- The Quick map skill counts and the totals at the top must be kept in sync.
- The Shared references library section is sourced from `skills/references/` directory listing.

A future enhancement (deferred per design D4 of `add-engineering-methodology-skills`) would auto-render this catalogue from the `related:` frontmatter graph + skill metadata. Until then, manual maintenance is the contract.
