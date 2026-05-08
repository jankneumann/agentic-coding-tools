# Mental Models for the Software Factory

> A reading guide for `agentic-coding-tools`. Maps the skills, coordinator, validation phases, and metrics in this repo onto four pieces of literature so newcomers can understand *why* the design is shaped the way it is.

This document is **explanatory**, not normative. It does not introduce new behavior; it gives you vocabulary for the behavior that already exists. If a section says "this skill embodies amplification," that is a description of what the skill is doing, not a requirement for it.

## Sources we draw from

| Source | What it gives us |
|---|---|
| Kim & Spear, *Wiring the Winning Organization* (2023) | The three mechanisms — **slowification**, **simplification**, **amplification** — that move work from the danger zone (improvising under pressure) to the winning zone (problems surfaced and swarmed) |
| Kim & Yegge, *From Line Cook to Head Chef* (2025) | The **kitchen brigade** metaphor — head chef, sous chef, expediter, line cook, mise en place, the pass — for orchestrating multiple AI agents |
| Yegge & Kim, *Three Developer Loops of Vibe Coding* (Feb 2025) | The **inner / middle / outer loops** — three nested cadences with different scopes, signals, and definitions of "winning" |
| Kersten, *Output to Outcome* (2025) | The reminder that AI inflates **output** metrics (PRs, lines, tasks) without proving **outcome** (deployed value, defect rate, cycle time) — DORA stays relevant, but needs AI-aware adaptations |

> Citations in this doc are paraphrased from memory; the IT Revolution articles were not retrievable from the build environment when this was drafted. Where precision matters (mechanism definitions, loop boundaries), the wording stays close to the published articles. If you find a definition drifted, prefer the original.

## How the metaphors compose

The four sources answer different questions about the same system:

- **Factory** (existing repo metaphor — see [`software-factory-tooling.md`](software-factory-tooling.md)) — *what* the tooling produces and *how throughput is controlled*: scenario packs, validation gates, archive intelligence, rework reports.
- **Kitchen** (Kim & Yegge) — *who does what* and *how live orchestration works*: roles, tickets, the pass, mise en place.
- **Wiring** (Kim & Spear) — *why* the design is shaped the way it is: which mechanism each skill embodies (slowification / simplification / amplification).
- **Loops** (Yegge & Kim) — *at what cadence* feedback flows: inner (seconds), middle (minutes-hours), outer (hours-days).
- **Output → Outcome** (Kersten) — *what to measure*: outcome over output; DORA-adapted scorecard.

The factory metaphor was already in use in this repo. The kitchen, wiring, and loops metaphors are added here because they illuminate aspects the factory metaphor underemphasizes — specifically, the live orchestration of human + AI roles, the conscious choice of mechanism, and the cadence at which each feedback signal is read.

## Quick orientation

If you read nothing else, read this section.

- The **head chef** is `/autopilot` (or you, when you drive the workflow manually). The head chef plans service, sequences tickets, and owns the pass.
- A **ticket** is an OpenSpec change-id (`openspec/changes/<id>/`). Mise en place for that ticket is its `proposal.md`, `design.md`, `tasks.md`, and any contracts under `contracts/`.
- The **kitchen brigade** is the set of skills under `skills/`. Each skill is a station with a defined role.
- The **pass** is `/validate-feature` and `/cleanup-feature`. Nothing reaches the customer (main branch, then production) without crossing the pass. The hard-gate phases — *Smoke Tests, Security, E2E Tests* — are enumerated in `skills/validate-feature/scripts/gate_logic.py` (`REQUIRED_PHASES`); spec/evidence/deploy run as soft gates that do not block merge.
- **Slowification** lives in the planning skills (`/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/prototype-feature`, `/parallel-review-plan`).
- **Simplification** lives in the OpenSpec change → work-package decomposition, the worktree isolation model (`skills/worktree/scripts/worktree.py`), and the explicit list of sync-point skills.
- **Amplification** lives in vendor-diverse review, coordinator events (`agent-coordinator/src/coordination_api.py`), validation phase escalation (`skills/validate-feature/scripts/gate_logic.py`), and PR webhook subscriptions.
- The **outer loop** (where DORA metrics live) is the coordinator's view of completed roadmap items. The **middle loop** is the per-PR/per-change cycle. The **inner loop** is what happens inside one agent turn or `/quick-task`.

The rest of this document expands each of these and grounds them in specific files.

---

# Part 1 — The kitchen you already work in

Yegge & Kim's "From Line Cook to Head Chef" reframes the AI-augmented developer as an orchestrator, not a producer. A line cook owns one ticket end-to-end: take the ticket, fire the protein, plate, hand to the expediter. A head chef does not cook. They sequence the rail, expedite the pass, decide which sauté goes when, and pull a ticket if a station is in the weeds.

This shift is the reason this repo exists. The single-developer-with-Copilot model is line-cook ergonomics. The moment you can fire N parallel agents — three vendors reviewing a plan, four work-packages running simultaneously, a security scanner, a smoke tester — you are running service. Service has a kitchen-OS underneath it, or it collapses.

## The brigade, mapped onto skills

| Kitchen role | Responsibility | Skill or file in this repo |
|---|---|---|
| Executive chef | Sets the menu (what "good" looks like). Doesn't work the line. | The human operator + `CLAUDE.md` + OpenSpec proposal templates |
| Head chef / chef de cuisine | Plans service, sequences tickets, owns outcomes | `/autopilot`, `/autopilot-roadmap`, `/plan-roadmap` |
| Sous chef | Runs the pass, holds the quality line, expedites tickets onto the wire | `/implement-feature` (drives validation gates), `/cleanup-feature` (drives merge gates) |
| Station chefs (sauté, pâtissier, garde manger, grill) | Specialists per technique | Vendor-diverse reviewers in `/parallel-review-plan` and `/parallel-review-implementation`; specialist skills like `/security-review`, `/gen-eval`, `/refresh-architecture` |
| Line cooks | Execute one ticket end-to-end at a station | Work-package agents in coordinated tier; sequential-tier agents |
| Prep cooks (mise en place) | Pre-stage everything before service | `/explore-feature`, `/plan-feature`, `/prototype-feature`, OpenSpec proposal artifacts, [`docs/architecture-artifacts.md`](architecture-artifacts.md) |
| Expediter | Final integration; calls "all day" and times the plates | `skills/worktree/scripts/merge_worktrees.py`, `/merge-pull-requests`, sync-point skills |
| Dishwasher | Resets stations between tickets | `skills/worktree/scripts/worktree.py` (`teardown`, `gc`), the cleanup half of `/cleanup-feature` |
| The pass | Last quality check; nothing leaves without crossing it | `/validate-feature` — soft gates (spec, evidence, deploy) run for signal; hard gates (Smoke / Security / E2E) enforced by `skills/validate-feature/scripts/gate_logic.py:REQUIRED_PHASES` |
| The ticket rail | Single source of truth for what's in flight | Coordinator claims/locks (`agent-coordinator/src/coordination_api.py` — `/work/*`, `/locks/*`, `/issues/*`), `.git-worktrees/.registry.json`, `openspec/changes/<id>/` |
| Andon cord | "Stop the line" signal | Validation-phase failures; `subscribe_pr_activity` webhook events; vendor-disagreement in parallel review |

> *Why this metaphor and not just "factory"?* The factory metaphor is excellent for throughput, scenario packs, and quality gates — and we use it (see [`software-factory-tooling.md`](software-factory-tooling.md)). But factories don't have customers waiting. Restaurants do. The kitchen vocabulary captures the live, latency-sensitive, "service tempo" character of running multiple agents against a deadline. Tickets do not stack indefinitely; the pass blocks if anyone is in the weeds. That tension is real in agent orchestration and the kitchen language names it.

## The ticket lifecycle, in brigade terms

A ticket flows through the brigade in stages that map cleanly onto your existing skills:

1. **Order is taken** — `/explore-feature` or operator request
2. **Mise en place** — `/plan-feature` produces proposal/design/tasks; optionally `/prototype-feature` produces variant skeletons; `/iterate-on-plan` and `/parallel-review-plan` sharpen the plan before any cook lights a burner
3. **Fire the ticket** — `/implement-feature` dispatches to work-package line cooks (or a single sequential-tier cook for simple tickets)
4. **Stations work in parallel** — coordinated tier runs the DAG; each station has its own worktree (`.git-worktrees/<change-id>/<agent-id>/`) so they don't collide
5. **Quality on the line** — `/iterate-on-implementation` and `/parallel-review-implementation` catch issues before they reach the pass
6. **The pass** — `/validate-feature` runs the phase ladder (spec, evidence, deploy, smoke, security, e2e). A failure at phase N stops phase N+1 (this is the andon)
7. **Plate and serve** — `/cleanup-feature` and `/merge-pull-requests` integrate to main; `/update-specs` reconciles spec drift
8. **Reset the station** — worktree teardown, branch cleanup, archive of `openspec/changes/<id>/` to `archive/`

> **Why mise en place matters more for AI than for humans.** A line cook holds half the recipe in their head and improvises the rest. AI agents are radically *better* at executing within a well-described context and radically *worse* at improvising when context is missing. The OpenSpec proposal artifacts are not bureaucracy — they are the ingredients laid out cold next to the burner.

---

# Part 2 — Wiring the Winning Organization, where each mechanism lives

Kim & Spear argue that high-performing organizations win not through heroics but through three mechanisms that move problems out of the **danger zone** (improvising under pressure, problems hide and compound) and into the **winning zone** (problems surface fast, get swarmed, get solved structurally). Each mechanism has a sharp definition. We will take them in turn and point at where each one already exists in this repo.

## 2.1 Slowification — practice in low-stakes settings before performance

**Definition.** Move work out of real-time performance mode into planning, practice, or post-mortem mode. Pre-mortems, simulations, table-top exercises, deliberate rehearsal. The goal is to surface and solve problems where the cost of error is small, so performance time becomes execution rather than discovery.

**Where it lives:**

| Slowification artifact | What it rehearses |
|---|---|
| `/explore-feature` | Generates candidate features before commitment; cheap to discard |
| `/plan-feature` | Forces an explicit proposal/design/tasks decomposition before code |
| `/iterate-on-plan` | Sharpens the plan after parallel review; bounded refinement |
| `/prototype-feature` | Builds N parallel variant skeletons cheaply, scores them, lets the operator pick — explicit rehearsal of approach |
| `/parallel-review-plan` | Vendor-diverse second opinions on the plan; surfaces hidden assumptions |
| OpenSpec `proposal.md` / `design.md` / `tasks.md` | The rehearsal venue — designs the change in writing first |
| [`docs/lessons-learned.md`](lessons-learned.md) | Post-mortem capture |
| [`docs/decisions/`](decisions/) | Tagged architectural decisions, indexed per-capability — institutional memory of *why* past calls were made |
| Archive intelligence (`docs/factory-intelligence/exemplars.json`) | Reuses successful patterns from completed changes; planning gets cheaper over time |

**The danger-zone behavior this prevents:** going straight from "I want X" to `/implement-feature` and discovering, four hours and forty agent turns later, that the plan was wrong.

**The winning-zone signature:** a 30-minute plan review catches a structural mistake that would have cost a 3-hour implementation rewrite.

## 2.2 Simplification — decompose into smaller, more reversible, more independent pieces

**Definition.** Reduce coupling and cognitive load through modularity, encapsulation, linearization, and chunk-size reduction. Simplification is not "make it pretty" — it is "make problems containable." A 500-line PR is a danger-zone artifact because a single bug forces you to revert all 500 lines. Ten 50-line PRs with explicit interfaces is a winning-zone artifact because problems stay local.

**Where it lives:**

| Simplification artifact | What it isolates |
|---|---|
| OpenSpec change → work-packages | One feature is decomposed into a DAG of packages with declared contracts |
| Tier selection (Coordinated / Local-parallel / Sequential) | Match the decomposition cost to the work — don't pay coordinator overhead for a one-line fix |
| Worktree-per-package isolation (`.git-worktrees/<change-id>/<agent-id>/`) | No shared mutable state between agents on the same change |
| Branch naming with `--` separator (`openspec/<change-id>--<agent-id>`) | Avoids git ref storage collisions; small but real isolation |
| Sync-point skills (the named three: `/merge-pull-requests`, `/update-specs`, `/cleanup-feature`) | Names the *only* places that touch main; everything else is forbidden from doing so |
| Phase isolation (sub-agents for IMPLEMENT, IMPL_REVIEW, VALIDATE per [`docs/decisions/software-factory-tooling.md`](decisions/software-factory-tooling.md)) | Heavy phases run in their own conversation; driver receives only `(outcome, handoff_id)` |
| Public vs holdout scenario visibility (per [`software-factory-tooling.md`](software-factory-tooling.md)) | Manifest fields (`visibility: public\|holdout`) are documented; for *this* repo, scenarios live flat under `agent-coordinator/evaluation/gen_eval/scenarios/` and the directory split is aspirational guidance for adopters (see also gap G11) |
| `EnvironmentProfile.isolation_provided` (`skills/shared/environment_profile.py`) | Cloud harness vs local — the substrate provides isolation in cloud; the skill semantics stay identical |

> **The strongest simplification artifact in this repo is the explicit naming of sync-point skills.** Most agentic systems pretend all skills are equal; this one calls out the three places where convergence happens (`/merge-pull-requests`, `/update-specs`, `/cleanup-feature`) and constrains everything else to worktrees. That is how Toyota runs thousands of parallel stations without explosion — the andon and the takt time are *named* convergence rules.

## 2.3 Amplification — make problems loud, visible, fast

**Definition.** Andon cord. Stop-the-line authority. Surface signals so they reach the people who can act *before* they cascade. The opposite of "see-and-solve alone" — amplification triggers swarming.

**Where it lives:**

| Amplification artifact | What it surfaces |
|---|---|
| `/parallel-review-plan` and `/parallel-review-implementation` | Vendor-diverse second opinions; disagreement between vendors is high-signal |
| Coordinator events / heartbeats | Failed or stalled agents are visible in `.git-worktrees/.registry.json` and via `agent-coordinator/src/coordination_api.py` (`/audit`, `/work/get`), not hidden in transcripts |
| `/validate-feature` hard-gate ladder | `skills/validate-feature/scripts/gate_logic.py` enumerates `REQUIRED_PHASES` (Smoke / Security / E2E); a `fail` status in `validation-report.md` halts `pre_merge_gate` |
| `subscribe_pr_activity` | Webhook events wake the session on CI failure or review comment |
| `gen-eval` scenarios under `agent-coordinator/evaluation/gen_eval/scenarios/` | Failures rehearse production behavior at the validation gate (lock-lifecycle, audit-trail, work-queue, handoffs, etc.) |
| `rework-report.json` (emitted by `skills/validate-feature/scripts/rework_report.py`) | Maps failed scenarios to owners and recommended actions (`iterate` / `revise-spec` / `defer` / `block-cleanup`) |
| Token instrumentation (`phase_token_pre/post` audit-trail entries — emitted in `skills/autopilot/scripts/autopilot.py`, see [`docs/decisions/observability.md`](decisions/observability.md)) | Cost spikes become visible at phase boundaries |
| `docs/lock-key-namespaces.md`, `coordination-bridge` skill | Lock contention is named, not hidden |

**The danger-zone behavior this prevents:** a single agent silently retrying a failing tool call eight times while burning tokens; a CI failure landing on main because no human noticed; one vendor's hallucination shipping because no second opinion was asked.

**The winning-zone signature:** a problem at the smoke-test phase triggers `block-cleanup`, surfaces the failure with an `implicated_files` list, and the operator can swarm the fix with full context — instead of debugging from a stack trace alone.

---

# Part 3 — The Three Developer Loops of Vibe Coding

Yegge & Kim describe three nested cadences. Each loop has its own scope, its own feedback signal, and its own definition of "winning." The pathology they call out is loops bleeding into each other — debugging in the inner loop a problem that is actually outer-loop, or trying to drive outer-loop outcomes with inner-loop signals (e.g., celebrating PR count instead of deploy frequency).

## 3.1 The three loops, mapped onto tiers

| Loop | Cadence | Scope | Feedback signal | Tier in this repo |
|---|---|---|---|---|
| **Inner** | seconds–minutes | One prompt, one function, one tool call | "Did this turn produce something that compiles / type-checks / looks right?" | Sequential tier; in-IDE prompt iteration; `/quick-task` |
| **Middle** | minutes–hours | One change / one PR | CI green, review pass, validation phases | Local-parallel tier; `/implement-feature`, `/iterate-on-implementation`, `/validate-feature` |
| **Outer** | hours–days | Integration, deploy, business outcome | Production telemetry, user behavior, DORA metrics | Coordinated tier + `/cleanup-feature` + `/merge-pull-requests` + `/autopilot-roadmap` learning log + roadmap-runtime checkpoints |

"Vibe coding" — describing intent, accepting AI output, iterating by feel — is fast and fluid in the inner loop. The trap is using vibe-coding cadence for middle- and outer-loop decisions, where signal latency is much longer and the cost of wrong decisions is much higher. You can vibe a function. You cannot vibe an architecture.

## 3.2 The signals each loop reads

| Loop | Read these signals | Do **not** make this loop's decisions on |
|---|---|---|
| Inner | Type-checker, single test, "did the agent produce code I'd accept" | Whether the design is right (that is a middle-loop concern) |
| Middle | CI status, validation phase pass/fail, vendor-review divergence, gen-eval scenario results, `rework-report.json` action | Whether the *feature* is delivering value (that is outer-loop) |
| Outer | Deploy frequency, change failure rate, MTTR, roadmap lead time, learning-log entries, business telemetry, cost per merged feature | Whether *one PR* was good (that is middle-loop) |

> **The classic AI-coding failure mode:** the inner loop accelerates 10×, the middle loop stays roughly the same, and the outer loop slows down because integration and review become the new bottleneck. This is what Kersten calls the "output to outcome" gap. AI generates fast; the old organization-OS cannot absorb the output. The article ["Unclogging the Value Stream"](https://itrevolution.com/articles/unclogging-the-value-stream-how-to-make-ai-code-generation-actually-deliver-business-value/) names this directly.

## 3.3 Why "tier" and "loop" are not the same axis

Tiers (Coordinated / Local-parallel / Sequential) are a *decomposition* axis — how many agents work in parallel on one change. Loops (Inner / Middle / Outer) are a *cadence* axis — how often you read a feedback signal.

A coordinated-tier change still has all three loops running inside it. The tier choice determines how many cooks are at the stations; the loop awareness determines what each cook is reading and how often. The CLAUDE.md "tier auto-selects at startup" rule is a simplification choice; the loop awareness is a slowification choice (you decide *before* service which signals each role will trust).

---

# Part 4 — Reading the metrics: AI-DORA

Classical DORA (Forsgren / Kim / Humble) measures four outcomes:

1. **Lead time for changes** — commit to production
2. **Deployment frequency**
3. **Change failure rate**
4. **MTTR**

Kersten's *Output to Outcome* argues that AI inflates output metrics (PRs opened, lines generated, tasks completed) without proving outcome. So a vibe-coding-aware metric set keeps DORA and adds AI-specific metrics. This is the rationale for [`scripts/ai_dora_snapshot.py`](../scripts/ai_dora_snapshot.py) (a skeleton — see Part 5 below).

The proposed scorecard, slotted by loop:

| Loop | Classical DORA | AI-coding-specific addition | Source events in this repo |
|---|---|---|---|
| **Inner** | (intentionally none — too noisy at this cadence) | Prompt-to-accepted-edit ratio; turns per accepted patch; tool-call retry rate within a turn | Agent transcripts; coordinator `/audit` |
| **Middle** | Lead time per PR; CI pass rate | Validation-phase pass rate by phase; review-cycle count to merge; vendor-diverse review divergence (signal-of-disagreement); rework-report action distribution; iteration count to merge | `validation-report.md` parsed by `gate_logic.py`; `rework-report.json` from `rework_report.py`; PR review history; gen-eval results |
| **Outer** | Deploy frequency; change failure rate; MTTR | Roadmap-item lead time; rollback rate by AI-authored vs human-authored; defect escape rate from `/validate-feature` to production; cost per merged feature (tokens × agent-hours); tier-selection accuracy (did simple-tiered work actually need coordinated?) | `roadmap-runtime` learning log; coordinator `/audit` (token + phase events), `/work/get`, `/issues/list`; merge strategy history; `phase_token_pre/post` audit-trail entries |

A few specific notes for this codebase:

- **You already have the substrate.** `roadmap-runtime` checkpoints, the coordinator's heartbeat/claim data, and `phase_token_pre/post` instrumentation are the raw events. What is mostly missing is the *aggregation layer*. The skeleton script in `scripts/ai_dora_snapshot.py` is that layer.
- **Vendor-diversity gives you a metric most teams do not have.** When two vendors agree, the signal is low; when they disagree, the signal is high. Tracking review divergence over time tells you whether your spec quality is improving — independently of whether any single review caught anything.
- **Output-as-vanity is the trap.** "100 PRs merged this week" is a danger-zone metric. "100 PRs merged, 12 reverted within 24 hours" is the winning-zone version of the same observation. The scorecard treats output and outcome as a *pair*, never separately.

---

# Part 5 — The AI-DORA scorecard skeleton

A starter implementation lives at [`scripts/ai_dora_snapshot.py`](../scripts/ai_dora_snapshot.py). It is intentionally a skeleton: it defines the metric shape, the source contract, and the output format, with stub data fetchers marked `TODO(source: …)`. You wire each fetcher to the real data source (coordinator HTTP API, learning-log files, GitHub, etc.) as you prefer.

What the skeleton commits to:

- **One module, one CLI.** `python scripts/ai_dora_snapshot.py --window 30d --output md` prints a markdown table; `--output json` prints structured data.
- **Three source adapters** (`CoordinatorSource`, `RegistrySource`, `RepoSource`) with explicit interfaces. Adding a new source means adding one class.
- **Loop-bucketed metrics.** The output groups metrics under *Inner / Middle / Outer* so readers cannot accidentally compare across cadences.
- **No silent zeros.** When a source is unavailable, the metric is reported as `unavailable: <reason>` rather than `0`. Avoids the "looks great because the pipe is broken" failure mode.

What the skeleton intentionally does *not* commit to:

- The exact data store (Postgres? jsonl files? GitHub Actions outputs?). The fetcher interface is enough to defer that decision.
- A dashboard. The script outputs markdown and JSON; if you want a Grafana panel later, that is a separate concern.

---

# Part 6 — Where the metaphors strain (honest limits)

Metaphors are scaffolding, not load-bearing structure. Each one helps until it doesn't. This section names where each metaphor breaks down in this repo, framed as gaps the design has not yet closed. The framing is deliberately adversarial — easier to fix what you can see.

### G1. Swarming vs retry — the andon-cord half-promise

WTWO's amplification is meaningless without **swarming**: when the line stops, multiple people converge on the problem. In this repo, `/iterate-on-plan` and `/iterate-on-implementation` exist, but they are predominantly *retry* loops — the same agent (or class of agent) tries again with refined input. Vendor-diverse review is real swarming, but it only fires at the *plan* and *implementation* boundaries, not when the line actually stops at a validation phase.

**The gap to close:** when `/validate-feature --phase smoke` fails, does the system trigger additional reviewers, a different vendor, or a fresh perspective? Or does the same agent retry? A retry without perspective change is a danger-zone tell.

### G2. The expediter is not staffed

The kitchen brigade has a dedicated expediter — the person at the pass who calls "all day," times the plates, and refuses outgoing work that is not right. In this repo, the expediter role is *split* across `/cleanup-feature` (which does merge + worktree GC + spec update + branch cleanup — four jobs) and `/merge-pull-requests` (sync-point skill). The closest thing to a pure expediter primitive is `pre_merge_gate()` in `skills/validate-feature/scripts/gate_logic.py`, which inspects `validation-report.md` and returns `('continue', ...)` or `('halt', reason)` — but it is a function, not a staffed station with its own skill.

**The gap to close:** if you wanted to add a `/expedite` skill that only inspects readiness — does the rework-report block? are there pending vendor disagreements? — and refuses to call merge until the answer is clean, where would it live? The role is implicit today, not first-class.

### G3. Output metrics are absent — but so is the explicit guard

Nothing in this codebase celebrates "PR count" or "lines generated." But nothing explicitly *forbids* it either. CLAUDE.md is silent on output-as-vanity; no skill rejects merging a 2,000-line PR on quality grounds; no dashboard refuses to display PR-count without revert-rate beside it. The trap is unprotected.

**The gap to close:** the AI-DORA scorecard in Part 5 is the start. The harder cultural artifact would be a CLAUDE.md addition explicitly listing "metrics we will not optimize for."

### G4. Mid-implementation plan drift bypasses the slowification venue

`/iterate-on-plan` can run *during* implementation. That is a useful escape hatch — sometimes you discover a planning mistake mid-cook. But it is also a back-channel that bypasses the original slowification gate (proposal approval). A plan refined mid-implementation can drift further from the original intent than anyone notices, because the original `proposal.md` no longer matches the design.

**The gap to close:** there is no automatic check that says "the proposal has been edited since `/implement-feature` started — do you want a re-review?" The drift is silent.

### G5. The ticket rail is fragmented

The kitchen has *one* ticket rail. This repo has at least four representations of in-flight work, and the coordinator API alone exposes three of them as separate endpoint families: `/work/*` (claims), `/issues/*` (the issue tracker, which is itself a ticket rail), and `/locks/*` (which gates the others). Add `.git-worktrees/.registry.json`, `openspec/changes/<id>/`, and GitHub PRs and you have at least six surfaces to consult to know what is in flight. The `coordination-bridge` skill exists exactly because this fragmentation is real.

**The gap to close:** a single `make tickets` (or equivalent) command that joins all sources into one view does not exist as a top-level affordance. The data is there; the union is not.

### G6. Andon-cord latency is unmeasured

`subscribe_pr_activity` wakes the session on CI failure. But the median time from "phase failed" → "agent or human acted on it" is unmeasured. If it is hours, that is a danger-zone signal hiding in the andon-zone vocabulary.

**The gap to close:** add the metric to the AI-DORA scorecard. The data exists in coordinator events and PR webhook timestamps.

### G7. Tier-selection is tier-1 simplification but tier-N risk

Auto-selecting Coordinated / Local-parallel / Sequential is a simplification primitive. But if feature complexity is mis-estimated, you run sequential where coordinated was needed, or vice-versa. There is no retrospective on tier-choice quality — no "of the last 30 sequential-tier features, how many had to be re-run as coordinated?"

**The gap to close:** tier-selection accuracy is one of the AI-coding-specific outer-loop metrics in Part 4's table. It is also the gap most likely to *teach* the auto-selector.

### G8. No rehearsed failure modes for the AI substrate

Slowification artifacts in this repo all rehearse *forward* design — what to build. None rehearse *what happens when the substrate fails*: agent goes rogue, coordinator disconnects, vendor returns garbage, token budget blows up, network partition during a 4-agent DAG. The `coordination-bridge` skill is a partial answer (HTTP fallback when MCP transport fails). But there is no chaos-drill skill, no game day.

**The gap to close:** a `/chaos-drill` that simulates a coordinator outage, an agent crash, or a vendor returning corrupt JSON would be a slowification artifact for substrate failure modes — currently absent.

### G9. The kitchen metaphor implies a closing time; the system has none

A real kitchen has a service end. Stations break down, the pass closes, dishwashers reset. This system runs continuously. The "service tempo" intuition that makes the kitchen metaphor useful for orchestration breaks down for *capacity planning* — there is no "we are at full coverage and cannot accept new tickets" state. Worktree GC and pinning are a partial answer, but not a capacity ceiling.

**The gap to close:** the metaphor is a *guide*, not a contract. Where it implies behavior the system does not implement, the doc should note it. This section is that note.

### G10. The sync-point active-agent guard — closed

**Original gap.** `CLAUDE.md` asserted a contract for sync-point skills:

> **Exclusive access**: Must not run while other agents hold active worktrees. Use `shared.check_no_active_agents()` to verify before proceeding.

Searching the repo for that function (or any close variant — `active_agent`, `no_active`, `registry stale`) found it nowhere in `skills/`. The function the contract named did not exist; sync-point skills honored the contract by convention only.

**Close.** Three pieces landed together:

1. **Implementation.** `skills/shared/active_agents.py` exports `check_no_active_agents()` returning `(clear, list[ActiveAgent])` against the actual `.git-worktrees/.registry.json` schema. An entry is "active" when `pinned=true` OR `last_heartbeat` is within a 1-hour stale threshold. It exposes a CLI for skills that shell out from markdown instructions (exit `0` clear, `1` blocked, `--force` override, `--json` machine-readable).
2. **Tests.** `skills/shared/tests/test_active_agents.py` (19 cases) covers the active/stale/pinned matrix, threshold edge cases, corrupt-registry fail-open, and CLI exit-code behavior.
3. **Wiring.** The three sync-point skills — `/cleanup-feature`, `/merge-pull-requests`, `/update-specs` — each now have an `## Active-Agent Guard (Sync-Point Skill)` subsection placed immediately before `## Steps`, instructing the agent to invoke `python skills/shared/active_agents.py` as the first action and to stop on exit `1` unless the operator passes `--force`.

The contract is now both implemented and enforced. A sync-point skill that does not call the guard is now visibly broken (the SKILL.md prose tells it to), rather than invisibly broken (no symbol exists). The remaining residual risk is the runtime-mirror sync: `.claude/skills/` and `.agents/skills/` need `skills/install.sh` to pick up the new guard text — this is a separate operator-driven step.

### G11. Public/holdout scenario visibility is documented as the design but not implemented in this repo

`docs/software-factory-tooling.md` describes a three-layer enforcement of public/holdout visibility:

1. directory structure (`public/` and `holdout/` subdirs),
2. manifest metadata (`visibility: public|holdout`),
3. runtime filtering.

In *this* repo, the gen-eval scenarios at `agent-coordinator/evaluation/gen_eval/scenarios/` are flat — no `public/` or `holdout/` subdirectories exist. Either the visibility is enforced purely through manifest metadata + runtime filtering (layers 2 and 3 only) or it is not enforced at all. The amplification table in Part 2.3 originally claimed the directory split provides isolation; that claim is incorrect for this repo. The layered enforcement described in `software-factory-tooling.md` is **prescriptive guidance for adopters**, not a description of this repo's state.

**The gap to close:** either implement the directory split here (cheap; mostly a `git mv` + manifest update) or change the amplification claim to "scenarios are flagged via manifest metadata; filesystem-level isolation is recommended for adopting projects."

---

# Part 7 — Glossary cross-walk

Quick lookup. Read across the row to translate between vocabularies.

| Kitchen | Factory | WTWO mechanism | Vibe-Coding loop | Skill / file |
|---|---|---|---|---|
| Head chef | Plant manager | (orchestration) | All three (decides which to read) | `/autopilot`, `/autopilot-roadmap` |
| Sous chef | Line supervisor | Amplification (calls swarms) | Middle | `/implement-feature`, `/cleanup-feature` |
| Expediter | QA at outbound | Amplification + Simplification | Middle → Outer | (split: `/cleanup-feature` + `/merge-pull-requests`) |
| Mise en place | Pre-staged scenario pack | Slowification | Middle (informs) | OpenSpec proposal artifacts; `/plan-feature`; archive intelligence |
| Ticket | Work order | (carrier) | All three | OpenSpec change-id |
| The pass | Outbound QA gate | Amplification (stop the line) | Middle | `/validate-feature` |
| Service tempo | Throughput | (constraint) | Outer | DORA + AI-DORA scorecard |
| Andon cord | Andon cord | Amplification | Middle (fires), Outer (escalates) | Phase failure, vendor disagreement, `subscribe_pr_activity` |
| Mise en place check | Public-scenario pre-check | Slowification | Middle | `/parallel-review-plan`, `/iterate-on-plan` |
| Surprise inspection | Holdout scenario | Amplification | Middle (gate) | `gen-eval` holdout, `/validate-feature` |
| Recipe book | Spec / contract | Simplification | All three | `openspec/specs/<capability>/` |
| Post-mortem | Decision index | Slowification | Outer | `docs/decisions/`, `docs/lessons-learned.md` |
| Reset between tickets | Worktree teardown | Simplification | Inner / Middle | `worktree.py teardown`, `gc` |

---

# Part 8 — How to extend this document

This is a living artifact. As skills are added, retire, or change role, update the relevant tables. The five places to keep in sync:

1. **Brigade table** in Part 1 — add new skills as kitchen roles.
2. **Mechanism tables** in Part 2 — slot each new skill under slowification, simplification, or amplification. If it does not fit, ask whether the skill is doing too much.
3. **Loop signals** in Part 3 — if a new skill produces a new feedback signal, name which loop it belongs to.
4. **Scorecard sources** in Part 4 + the script — wire the new event into `scripts/ai_dora_snapshot.py`.
5. **Glossary** in Part 7 — add the row.

When in doubt: a skill that introduces a new vocabulary word is probably introducing a new mental concept. Ask whether the existing metaphors cover it. If not, name the new metaphor and add it to "Sources we draw from."

---

## See also

- [`docs/parallel-agentic-development.md`](parallel-agentic-development.md) — the implementation reference for tiered execution
- [`docs/software-factory-tooling.md`](software-factory-tooling.md) — the factory-side companion to this document
- [`docs/skills-workflow.md`](skills-workflow.md) — stage-by-stage workflow walkthrough
- [`docs/agent-coordinator.md`](agent-coordinator.md) — coordinator architecture
- [`docs/lessons-learned.md`](lessons-learned.md) — patterns and post-mortems
- [`docs/decisions/README.md`](decisions/README.md) — architectural decisions per capability
