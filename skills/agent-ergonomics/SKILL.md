---
name: agent-ergonomics
description: Refine a system design or plan to be maximally agent-intuitive, agent-ergonomic, and agent-accretive — grounded in simulated agent journeys and real friction evidence, measured in tool calls and tokens, with falsifiable acceptance probes
category: Architecture
tags: [ergonomics, agent-experience, design-review, legibility, refinement]
triggers:
  - "agent ergonomics"
  - "agent-ergonomic"
  - "make this agent friendly"
  - "agent experience review"
  - "AX review"
---

# Agent Ergonomics Review

Refine a plan, design, or whole system so that an AI agent operating it can understand the situation accurately and control it optimally with the least expenditure of resources. This is an *evidence-driven redesign loop*, not a free-form meditation: you simulate concrete agent journeys, ledger every point of friction, redesign to eliminate it, and prove the improvement with before/after cost deltas.

## Arguments

`$ARGUMENTS` — the target, one of:
- An OpenSpec change-id (refine that proposal's design docs)
- One or more doc/plan paths
- `system` (default) — the whole repo's operator surface: CLAUDE.md, docs/, CLI, API, skills

Optional flags:
- `--journeys <N>` (default: 6) — number of representative agent journeys to simulate
- `--evidence <path>` — session transcripts / episodic-memory exports to mine for real friction
- `--dry-run` — produce the friction ledger and redesign proposal only; make no edits

## Definition: what "agent-ergonomic" means here

Do not invent your own rubric. Evaluate the target against these nine measurable properties. Every finding must cite the property it violates.

1. **Discoverability** — From a cold start, an agent can learn *what exists* and *what state things are in* with one obvious command or one obvious document. There is a single stable entry point; nothing load-bearing is only discoverable by grepping source.
2. **Legibility (tower of abstractions)** — Concepts form a coherent layered model: each layer is explicable in terms of the one below, names are used consistently across CLI, API, docs, and code, and there is exactly one source of truth per fact. Synonyms, near-duplicates, and drifted docs are legibility bugs.
3. **Affordance** — Every state, error, and output names the *next action*. An error message that doesn't say what to run next is a defect. Help text, `--help`, and status outputs advertise their own follow-ups.
4. **Safety & idempotency** — Mutations are retry-safe, offer dry-runs, and distinguish reversible from irreversible. An agent must never be forced to guess whether re-running is safe.
5. **Observability** — The agent can verify its own work: every operation exposes a way to check that it did what it claimed, with structured (machine-parseable) output. Silent success and silent failure are both defects.
6. **Economy** — The cost to answer common questions is low: measured in *tool calls and tokens*, not elegance. A fact needing 5 file reads when one status command could serve it is an economy defect.
7. **Feedback loops** — For every "do X" there is a cheap "did X work?" that the agent can run without human help (tests, probes, validators, status endpoints).
8. **Memory-compatibility** — Names, paths, and commands are stable across time so a returning agent's cached knowledge stays valid; deprecations leave tombstones that redirect, rather than dead ends.
9. **Accretiveness** — The system makes agents *better over time*: work products (findings, decisions, fixes) land somewhere durable and discoverable (ADRs, docs, memory, specs), so the next session starts smarter than this one.

## Anti-goals (read before redesigning)

- **Abstractions must pay rent.** A new layer, registry, or indirection is justified only by a concrete friction entry it eliminates, and its own comprehension cost counts against it. "Maximally interconnected" is not a goal; *minimally sufficient and coherent* is.
- **Prefer deletion and consolidation** over addition. The most agent-ergonomic fix for two overlapping docs is usually one doc.
- **Do not degrade human ergonomics** to serve agents; find designs that serve both (structured output *plus* readable text, not instead of).
- **No speculative generality.** Redesign for the journeys you simulated and the friction you evidenced, not for imagined future agents.
- **Smallest coherent change.** If the ledger is fixable with edits to three docs and one CLI help string, do not restructure the repo.

## Steps

### 1. Inventory the operator surface

Map what an agent driving this system actually touches: entry-point docs, CLI commands, API routes, config files, error surfaces, status/observability commands. For an OpenSpec target, the surface is the proposed design's equivalent of these. Note the intended tower of abstractions — what the layers *claim* to be.

### 2. Select representative agent journeys

Pick `--journeys` concrete, end-to-end tasks a real agent would be asked to do, spanning read (diagnose, answer, audit), write (ingest, fix, configure), and recover (retry after failure, resume after crash). Prefer journeys evidenced by real history: mine `--evidence` transcripts, episodic memory, git log, and past incident notes for tasks that actually caused struggle. State each journey as one sentence with a measurable finish line.

### 3. Cold-start simulation (the driver's seat, operationalized)

For each journey, role-play an **amnesiac agent**: assume only the documented entry point, no prior session knowledge. Walk the journey step by step *on paper against the actual docs/design*, at every step recording:
- What the agent knows, what it must guess
- Which tool call / document read it makes next and **why**
- Cumulative cost (tool calls, approximate tokens read)
- Every friction event: ambiguity, dead end, synonym confusion, missing affordance, unverifiable success, unsafe retry, doc/code drift

This simulation is the deep-thinking phase. Spend the effort here, inside the journeys — not in abstract meditation about the system.

### 4. Build the friction ledger

Consolidate findings into a table: `id | journey | step | property violated (1–9) | evidence | cost impact | proposed fix | fix cost`. Deduplicate; when one root cause produces many symptoms, ledger the root cause. Rank by (cost impact ÷ fix cost).

### 5. Redesign

Apply fixes top-down through the ledger, honoring the anti-goals. Typical moves, in order of preference: delete/merge duplicated concepts; rename for consistency; add affordances to existing errors/outputs; add one status/verify command; restructure a doc's entry hierarchy; only then introduce new abstractions. Update the actual design documents and plans — every changed doc must remain internally consistent and cross-reference the single source of truth rather than restating facts.

### 6. Re-simulate and prove the delta

Re-run each journey from Step 3 against the *revised* design. Report per-journey before/after: tool calls, tokens, friction events. A redesign that doesn't reduce these numbers is reverted or rethought.

### 7. Emit acceptance probes

For the top findings, write falsifiable probes that outlive this session, phrased so a future agent (or CI) can execute them, e.g.:
- "A cold-start agent can determine <state fact> in ≤2 tool calls starting from <entry doc>."
- "Running <mutation> twice is a no-op the second time and says so."
- "Every error in <surface> names a next action."
Record them in the target's design docs (or `openspec/changes/<id>/` for a proposal) so they gate future drift.

### 8. Report

Final output: the friction ledger, the changes made (with file paths), the before/after cost table, the acceptance probes, and an explicit list of fixes *deliberately not taken* with the anti-goal that vetoed each. If `--dry-run`, output all of the above as a proposal instead of edits.
