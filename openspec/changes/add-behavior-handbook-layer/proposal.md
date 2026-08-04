# Change: add-behavior-handbook-layer

## Why

The architecture pipeline (`docs/architecture-analysis/`) produces a rich structural index — 1909 nodes, 1160 edges — but no artifact that answers the question every change request actually asks: *where does behavior X live?* The evidence is stark: `cross_layer_flows` is empty and 96 entrypoints are disconnected, meaning the structural graph cannot narrate a single request end-to-end, and agents planning changes must reconstruct behavior-to-code mappings from raw AST edges every session.

The Harness Handbook paper (arXiv 2607.13285) demonstrates that a behavior-centric representation — a three-level map (system flow → behavior units → unit detail) with source-verified evidence locators, consumed via progressive disclosure — improves edit-plan quality (+10 to +19 pp win rate) while *reducing* planner tokens (~9–13%). This repo is a harness in the paper's exact sense (prompt construction, state management, tool invocation, execution coordination), so the findings should transfer directly. We also gain a persona-aware reading surface: newcomers, reviewers, and planning agents enter the same map at different levels with different token budgets, instead of forking per-audience documents that drift.

## What Changes

- Add a **behavior handbook generator** to the `refresh-architecture` pipeline that synthesizes `architecture.behaviors.json` (Layer 2.5) from existing Layer 1/2 artifacts: L1 system flows, L2 behavior units, L3 unit details (triggers, state changes, execution paths, exception paths, evidence).
- Add a **verified locator** contract: every L3 claim carries a locator (node ID + file + span + content digest) that a resolver checks against HEAD; unresolvable locators become `architecture.diagnostics.json` errors and fail `make architecture-check`.
- Extend **provenance/freshness**: `architecture.provenance.json` records the handbook artifact digest and its input fingerprint so the existing content-based staleness gate covers the handbook (no parallel freshness system).
- Add a **progressive-disclosure query CLI** (`handbook_query.py`) that serves one level at a time under explicit token budgets (L1 ≈ 400 tokens, L2 card ≈ 150, L3 expansion ≤ 1500), for consumption by planning skills.
- Add an **HTML drill-down artifact generator** (`generate_handbook_html.py`) rendering the three-level map as a self-contained interactive page (L1 flow → L2 unit cards → L3 detail panes) with persona-selectable entry points (newcomer / reviewer / planner / auditor).
- Wire **behavior seeding** from existing data: `entrypoints[]`, `high_impact_nodes` (107), the 96 disconnected endpoints, and `treesitter_enrichment.json` exception patterns (promoting exception paths from aggregate stats to named L3 content).
- Add an **evaluation harness scenario** measuring behavior-localization accuracy and tokens-to-localization with vs. without the handbook, using archived changes with known ground-truth touched files.
- Non-breaking: all new artifacts are additive; existing consumers of `architecture.graph.json` are unaffected.

## Approaches Considered

### Approach 1: Extend the refresh-architecture pipeline (Layer 2.5 artifact)

Description: Add handbook synthesis as a new stage inside the existing `refresh-architecture` skill, consuming Layer 1/2 JSON and emitting `architecture.behaviors.json` + HTML view, governed by the existing provenance/freshness gate.

- Pros:
  - Reuses deterministic staging, `SOURCE_DATE_EPOCH` clocking, digest-based freshness, and `make architecture-check` — the handbook can never silently go stale.
  - Behavior units reference existing stable node IDs; the graph remains the single evidence store (matches `codebase-analysis` spec's "single source of truth" requirement).
  - One refresh command, one diagnostics file, one provenance record.
- Cons:
  - The LLM-assisted structuring step introduces nondeterminism into an otherwise deterministic pipeline; needs a cached/committed synthesis with deterministic re-verification.
  - Grows an already large skill.
- Effort: M

### Approach 2: Standalone handbook skill with its own pipeline

Description: A new `behavior-handbook` skill with its own analyzers, its own output directory, and its own refresh command, independent of `refresh-architecture`.

- Pros:
  - Clean separation; no risk to the existing deterministic pipeline.
  - Free to iterate on schema without touching the codebase-analysis spec.
- Cons:
  - Duplicates provenance, freshness, staging, and diff machinery — a second staleness story is exactly the failure mode the paper's verification design exists to prevent.
  - Two graphs drift apart; evidence locators would not share node IDs with `architecture.graph.json`.
- Effort: L

### Approach 3: Prompt-time-only handbook (no committed artifact)

Description: No generated artifact; a planning-time skill walks `architecture.graph.json` on demand and synthesizes behavior context per request (BGPD as a pure runtime protocol).

- Pros:
  - Nothing to keep fresh; always reflects HEAD.
  - Zero pipeline changes.
- Cons:
  - Re-pays the synthesis token cost every session — the paper's token savings come precisely from amortizing synthesis into a reusable artifact.
  - No HTML reading surface for humans; no reviewable, diffable behavior map; quality varies per session.
- Effort: S

### Recommended

Approach 1. The repo's decisive advantage is that `architecture.provenance.json` already solves the hardest problem of a synthesized handbook — silent staleness — via content-based digests and drift reason codes. Approach 2 forfeits that and doubles maintenance; Approach 3 forfeits both the amortized-token benefit and the human-facing artifact, which are the two headline outcomes we want. The nondeterminism concern in Approach 1 is contained by committing the synthesized behavior map and re-verifying locators deterministically on every check.

### Selected Approach

Approach 1 (fast-forward workflow; recorded as the working selection, pending user override).

## Impact

Affected architecture layers: **Execution** (new pipeline stage, CLI, HTML generator), **Coordination** (planning skills consume handbook levels when packing worker context), **Governance** (freshness gate extended to a new artifact class).

Affected specs (delta files under `specs/` in this change):

| Capability | Delta | Nature |
|---|---|---|
| `codebase-analysis` | `specs/codebase-analysis/spec.md` | ADDED requirements: behavior handbook artifact schema, verified locators, handbook freshness, progressive-disclosure query, HTML view |

Major code/doc touchpoints:

- `skills/refresh-architecture/scripts/` — new `synthesize_behaviors.py`, `verify_locators.py`, `handbook_query.py`, `reports/generate_handbook_html.py`; staging integration in `refresh_architecture.sh` / `run_architecture.py`
- `Makefile` — `architecture-handbook`, handbook coverage in `architecture-refresh` / `architecture-check`
- `docs/architecture-analysis/` — new `architecture.behaviors.json`, `views/handbook.html`; provenance entries
- `docs/architecture-artifacts.md` — document the new layer and commands
- `skills/context-engineering/SKILL.md` — reference handbook levels as a packing source
- `packages/gen-eval` / `skills/gen-eval-scenario` — behavior-localization eval scenario
- Tests under `skills/refresh-architecture/scripts/tests/`

Rollback: not breaking; remove the new pipeline stage and generated artifacts. Provenance entries for the handbook are additive keys ignored by older tooling.
