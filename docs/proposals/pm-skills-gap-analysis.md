# Gap Analysis: Product-Management Skills (`phuryn/pm-skills`)

**Status:** Proposal input · **Date:** 2026-07-04
**Companion OpenSpec change:** [`add-product-management-skills`](../../openspec/changes/add-product-management-skills/proposal.md)

## Summary

`phuryn/pm-skills` is a marketplace of 68 product-management skills across 9 plugins
(discovery, strategy, execution, market research, data/analytics, go-to-market, marketing,
toolkit, ai-shipping). Our repo is the opposite shape: it is dense **downstream of the
decision to build** — `explore-feature → plan-roadmap / plan-feature → implement-feature →
validate-feature → cleanup-feature` — and its multi-vendor review/convergence machinery is
mature. What it lacks is a **product-discovery front end**: the structured *why / who /
what-outcome* reasoning that decides which change is worth an OpenSpec proposal in the first
place.

Today that front end is a free-text field. `plan-roadmap` decomposes a `proposal.md` whose
`Motivation` section is written by operator reasoning or expanded from a one-line pitch
(`--draft`). `explore-feature` picks "what to build next" from **architecture artifacts and
code signals** — never from customer input, assumptions, or a desired outcome. The PM skills
that complement us are precisely the ones that *emit an artifact an existing skill already
consumes*. The ones that don't (pricing, Porter's Five Forces, NDAs, résumé review) have no
seam here and are explicit non-goals.

This document identifies **six seams** where a curated subset of PM skills plugs into the
existing pipeline, names the exact skills per seam, and states the integration contract for
each. The companion OpenSpec change plans the implementation.

## Method

We audited all 68 PM skills against every user-invocable skill in `skills/`. A PM skill
"complements" us only if it satisfies a **seam test**: its output is consumed by, or its input
is produced by, an existing skill — so adopting it changes an artifact that already flows
through the pipeline rather than adding an island. 12 skills pass the seam test across six
seams; the rest are catalogued as non-goals at the end.

This mirrors the precedent set by the archived `add-engineering-methodology-skills` change,
which ported a *horizontal* methodology layer (`test-driven-development`, `debugging-and-error-recovery`,
`api-and-interface-design`, …) into our *vertical* orchestration layer. That change filled the
**"how to build"** gap. This one fills the **"what/why to build"** gap immediately upstream of it.

## The six seams

### Seam 1 — Feed the proposal's "why" (upstream of `plan-roadmap` / `plan-feature`)

**Problem.** `plan-roadmap` is explicitly built to decompose a long-form `proposal.md` into a
prioritized change DAG, but the proposal's `Motivation` / `Why` is unstructured. When no
proposal exists, `--draft` asks an LLM to invent one from a pitch — discovery theater, not
discovery.

**PM skills:** `create-prd`, `opportunity-solution-tree`

**Integration contract.**
- `create-prd` emits an 8-section PRD that *is* a fillable `proposal.md` — it replaces the
  thin `--draft` expansion with a real discovery artifact carrying problem, users, success
  metrics, and scope.
- `opportunity-solution-tree` (Teresa Torres) maps a desired **outcome → opportunities →
  solutions → experiments**. Its solution nodes are exactly the candidate changes
  `plan-roadmap` decomposes, and its outcome node supplies the `Why`.

**Consumed by:** `plan-roadmap` (proposal input), `plan-feature` (discovery step 3),
`openspec-new-change`.

### Seam 2 — Prioritization with a customer-value axis (`prioritize-proposals`, `explore-feature`)

**Problem.** `prioritize-proposals` ranks active OpenSpec proposals and `explore-feature` ranks
next features, but both rank on **code/architecture signals** (coupling, debt, active OpenSpec
context). There is no impact / effort / confidence / customer-value axis and no explicit
risk-of-being-wrong axis.

**PM skills:** `prioritize-features`, `identify-assumptions`

**Integration contract.**
- `prioritize-features` adds an impact × effort × risk × alignment scoring pass that composes
  with the existing code-signal ranking rather than replacing it — a second lens on the same
  candidate set.
- `identify-assumptions` classifies each candidate's riskiest assumptions (value / usability /
  viability / feasibility). High-risk-unvalidated candidates get flagged for a cheap experiment
  *before* they consume a full plan→implement cycle.
- `prioritization-frameworks` (RICE, WSJF, Kano, MoSCoW, …) ships as a **shared reference doc**
  under `skills/references/`, cited by both prioritization skills — not as its own skill (it is
  reference material, following the `references/` library precedent).

**Consumed by:** `prioritize-proposals`, `explore-feature`, `plan-roadmap` (priority seeding).

### Seam 3 — Adversarial review at the *strategy* layer (`parallel-review-plan`, `iterate-on-plan`)

**Problem.** Our review culture is a signature strength — `parallel-review-plan`,
`iterate-on-plan`, multi-vendor convergence — but it reviews the **plan's code and specs**, not
the **plan's assumptions**. A well-formed proposal built on a false premise passes review.

**PM skills:** `strategy-red-team`, `pre-mortem`

**Integration contract.**
- `strategy-red-team` is our own convergence ethos aimed one level up: adversarially stress-test
  the proposal's assumptions before Gate 1 approval in `plan-feature`. It emits findings in the
  same shape `iterate-on-plan` already iterates on.
- `pre-mortem` runs a severity-classified "assume this shipped and failed — why?" pass before
  `implement-feature` dispatches work packages, surfacing risks the code-level reviewers can't see.

**Consumed by:** `plan-feature` (Gate 1), `iterate-on-plan`, `implement-feature` (pre-dispatch).

### Seam 4 — Spec-scenario authoring (OpenSpec specs, `playwright-validator`)

**Problem.** OpenSpec specs use WHEN/THEN scenarios and `playwright-validator` drives a
deployed frontend from them, but scenario *authoring* is ad-hoc. There is no skill that turns a
requirement into well-formed acceptance scenarios and edge cases.

**PM skills:** `user-stories`, `test-scenarios`

**Integration contract.**
- `user-stories` produces Three-C / job-story / WWAS-format stories whose acceptance criteria
  map directly onto OpenSpec `#### Scenario:` WHEN/THEN blocks.
- `test-scenarios` enumerates happy-path + edge cases, feeding both the spec deltas and
  `validate-feature` / `test-driven-development`.

**Consumed by:** `plan-feature` (spec generation), `playwright-validator`, `validate-feature`,
`test-driven-development`.

### Seam 5 — AI-shipping verification (`openspec-verify-change`, `validate-feature`, `documentation-and-adrs`)

**Problem.** We verify *spec compliance* (`openspec-verify-change`, `validate-feature`) but from
the engineering side only. There is no product-side gap analysis between *what was documented as
intended* and *what actually shipped*, and no reviewability artifact set for AI-built changes.

**PM skills:** `intended-vs-implemented`, `shipping-artifacts`

**Integration contract.**
- `intended-vs-implemented` performs a documented-behavior-vs-actual-behavior diff — near-identical
  intent to `openspec-verify-change`, but expressed as a product artifact. It becomes a
  complementary check in the verify step, catching drift the spec-compliance check misses.
- `shipping-artifacts` produces the reviewability doc set (what the change does, how to review it,
  what was deliberately skipped) — a natural extension of `documentation-and-adrs`.

**Consumed by:** `openspec-verify-change`, `validate-feature`, `documentation-and-adrs`,
`cleanup-feature`.

### Seam 6 — Outcome framing for roadmaps (`plan-roadmap`, `autopilot-roadmap`)

**Problem.** Our roadmap is a **dependency DAG of changes** (`roadmap.yaml`). It has no
representation of the **outcome or goal** each change moves — items are engineering deliverables,
not measurable results.

**PM skills:** `outcome-roadmap`, `brainstorm-okrs`

**Integration contract.**
- `outcome-roadmap` reframes a feature list as outcome→feature mapping, supplying the goal layer
  `roadmap.yaml` lacks (acceptance outcomes already exist per item; this adds the outcome the
  items *serve*).
- `brainstorm-okrs` defines objective + key results that `autopilot-roadmap`'s learning-feedback
  loop can measure progress against, turning "items done" into "outcome moved".

**Consumed by:** `plan-roadmap`, `autopilot-roadmap`, `roadmap-runtime`.

## Seam summary

| Seam | PM skills (new) | Consumed by (existing) |
|---|---|---|
| 1 · Proposal "why" | `create-prd`, `opportunity-solution-tree` | `plan-roadmap`, `plan-feature`, `openspec-new-change` |
| 2 · Prioritization | `prioritize-features`, `identify-assumptions` | `prioritize-proposals`, `explore-feature` |
| 3 · Strategy red-team | `strategy-red-team`, `pre-mortem` | `plan-feature`, `iterate-on-plan`, `implement-feature` |
| 4 · Spec scenarios | `user-stories`, `test-scenarios` | `playwright-validator`, `validate-feature`, `test-driven-development` |
| 5 · Shipping verification | `intended-vs-implemented`, `shipping-artifacts` | `openspec-verify-change`, `validate-feature`, `documentation-and-adrs` |
| 6 · Outcome roadmaps | `outcome-roadmap`, `brainstorm-okrs` | `plan-roadmap`, `autopilot-roadmap` |

**12 new skills** (2 per seam) + 1 shared reference doc (`prioritization-frameworks`), each
localized to our OpenSpec / agent-coordination context, each carrying our full frontmatter schema
and the mandatory tail-block convention for user-invocable skills.

## Adaptations to existing skills (where the seams are actually wired)

Porting skills is only half the work; the value is realized when existing skills *consume* them.
The companion change edits these seams:

| Existing skill / artifact | Adaptation |
|---|---|
| `openspec/schemas/feature-workflow/templates/proposal.md` | Optional PM-artifact sections (PRD linkage, assumptions, outcome) so `create-prd` / `opportunity-solution-tree` output slots in |
| `explore-feature` | Consume opportunity-solution-tree output; add outcome framing to "what next" |
| `prioritize-proposals` | Add the `prioritize-features` scoring axes alongside code-signal ranking |
| `plan-feature` | Gate-1 discovery incorporates `identify-assumptions` + `strategy-red-team` findings |
| `openspec-verify-change` / `validate-feature` | Add `intended-vs-implemented` as a complementary drift check |
| `plan-roadmap` / `roadmap.yaml` schema | Optional outcome/OKR fields per roadmap item |

## Overlaps to manage (adopt with care)

- **`release-notes`** overlaps our existing `changelog-version` — **skip** (redundant).
- **`metrics-dashboard` / `north-star-metric`** overlap `agent-metrics` *conceptually* but target
  a different domain (product metrics vs. agent throughput). Additive, but they share no plumbing —
  adopt only if a product-metrics use case appears; **deferred**, not in scope.
- **`summarize-meeting` / `summarize-interview` / `interview-script`** are strong discovery skills
  but have no current pipeline seam (we ingest transcripts via `collect-transcripts`, which is
  agent-session-focused). **Deferred** pending a customer-research use case.

## Explicit non-goals

No seam exists in an agent-coordination/engineering repo for these, so they are **not** ported:
`pricing-strategy`, `monetization-strategy`, `pestle-analysis`, `porters-five-forces`,
`ansoff-matrix`, `swot-analysis`, `business-model`, `lean-canvas`, `startup-canvas`,
`competitive-battlecard`, `gtm-strategy`, `growth-loops`, `product-name`, `marketing-ideas`,
`positioning-ideas`, `draft-nda`, `privacy-policy`, `review-resume`, `grammar-check`,
`sql-queries`, `cohort-analysis`, `ab-test-analysis`. Also deferred: `product-strategy` /
`product-vision` (valuable north-star input for `explore-feature`, but adds a strategy stage
broader than the six seams; revisit after the discovery front end lands).

## Recommendation

Adopt all six seams as one OpenSpec change, phased scaffold-then-content (the approach the
methodology-skills precedent proved). If forced to a minimal first slice, ship **Seam 1
(`create-prd`) + Seam 3 (`strategy-red-team`) + Seam 2 (`prioritize-features`)** — the three
highest-traffic seams, each wiring into a skill already invoked daily. See the companion
proposal for the full plan, phases, and spec deltas.
