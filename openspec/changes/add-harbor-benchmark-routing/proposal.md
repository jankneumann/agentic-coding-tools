# Proposal: add-harbor-benchmark-routing

## Why

Routing decisions in this repo are static guesses. `archetypes.yaml` maps phases to
vendor/model/thinking tiers that nobody has ever measured against real outcomes, and
the adaptive router designed to replace those guesses
(`add-adaptive-model-router`, 21/71 tasks) is stalled on two missing pieces: its data
plane (the `model_catalog` / `model_posteriors` / `routing_decisions` /
`routing_spend_ledger` migration was never created) and any populated source of
quality/cost priors. The scoring math in
`agent-coordinator/src/model_routing/` (resolver, feedback, exploration) is landed and
unit-tested but has nothing to read.

Meanwhile the repo owns a ready-made benchmark corpus: **114 archived OpenSpec
changes**, each retaining `proposal.md` (114), `tasks.md` (113), delta `specs/` (114),
and usually `design.md` (90) — human-ratified task statements written *before* their
implementations. The unstarted `skill-rightsizing` scaffolds (ri-02 corpus split,
ri-05 replay runner, ri-03 telemetry scorecard) already recognized this; they lack an
execution substrate. Harbor (github.com/harbor-framework/harbor, from the
Terminal-Bench team) is that substrate: a standard task format (instruction +
Dockerfile environment + reward-writing verifier), built-in Claude Code / Codex CLI
agent adapters, a `BaseAgent` extension point for custom harnesses, per-trial
token/cost/trajectory capture, and parallel containerized execution.

**User intent (discovery, 2026-09-01):** the benchmark is the means; the ends are
(1) stop hand-picking vendors/tiers — route on measured evidence from *this repo's*
task distribution — and (2) unblock `add-adaptive-model-router` by giving it both its
data plane and its first real prior source.

## What Changes

- **New package `packages/harbor-bench/`** with three tools:
  - **Converter**: archived change → Harbor task directory (instruction from
    `proposal.md`, environment Dockerfile checked out at the pre-implementation
    commit, verifier scoring the produced diff against the change's own
    Given/When/Then scenarios plus repo quality gates; implementation diff withheld).
    Subsumes ri-05 `build-task-replay-runner` — same component, Harbor execution.
  - **Sweep runner**: runs Harbor jobs over a **combo** matrix
    (`combo = {vendor, model, thinking, harness}` — a new term; "arm" stays reserved
    for the rightsizing A/B). v1 matrix covers all 5 configured vendors: `claude-code`
    and `codex` via Harbor's built-in adapters; `grok`, `antigravity`, `pi` via custom
    `BaseAgent` adapters. Local **podman** execution (this repo's container runtime)
    via podman's Docker-compatible API socket, N≥3 attempts where budget allows.
  - **Prior importer**: Harbor trial results → `model_catalog.benchmark_prior` /
    `model_posteriors`, keyed on `(vendor, model, thinking, task_type)` with
    provenance `harbor-replay` so archive-replay priors are distinguishable from the
    router's planned OpenRouter/Artificial-Analysis prior sources.
- **Migration `035_model_routing.sql`** lands here (schema from
  `add-adaptive-model-router`'s `contracts/db/schema.sql` plus provenance and
  thinking-level columns), unblocking that change as a side effect.
- **Corpus manifest**: regenerate ri-02's sealed dev/holdout split over the current
  114 archived changes using its declared method (holdout biased post-2026-05-01,
  checksummed, runner refuses holdout without an explicit decision-run flag).
- **Feedback keying fix**: `model_routing/feedback.py` normalizers currently key on
  `vendor` alone, collapsing thinking tiers — the dimension that matters most (codex
  frontier/premium and all grok tiers differ *only* by thinking). Re-key to
  `(vendor, model, thinking)` before any prior is fitted.
- **Flagged read-path**: `resolve_for_phase` gains a `ROUTING_ADAPTIVE` mode
  (default off) that ranks candidates via `model_routing.resolver.score_and_rank()`
  using imported priors. Exploration (`exploration.choose()`) and live posterior
  feedback remain follow-ups.
- **Scorecard**: per-combo × task_type report (quality, cost, latency, sample size,
  variance) over the dev split.

**Budget model** (per discovery): claude/codex/grok/antigravity are
subscription-based — their sweep cost is usage-limit headroom, not USD; `pi` via
OpenRouter is the only USD-metered vendor. The pilot caps OpenRouter spend at
**$50/job** (ledger-enforced) and throttles subscription vendors by quota-headroom
policy. Pilot sweep: ~15–20 dev-split tasks across the full 5-vendor matrix;
imported priors carry small-n sample sizes that `blend_quality()`'s confidence
weighting already discounts.

## Relationship to Existing Changes

| Change | Relationship |
|---|---|
| `build-task-replay-runner` (ri-05, 0/10 scaffold) | **Superseded** — this change is its execution substrate; mark superseded on approval |
| `seal-archive-benchmark-corpus-split` (ri-02, 0/10) | **Absorbed** — manifest generated here with its method, re-sealed at 114 changes |
| `aggregate-process-telemetry-scorecard` (ri-03) | **Consumed** — per-run record schema reused for trial telemetry |
| `add-adaptive-model-router` (21/71) | **Advanced** — its migration and first prior source land here; its OpenRouter refresher / exploration tasks remain there |
| `calibrate-llm-judge-against-human-labels` (ri-08) | **Constraint honored** — LLM-judge scoring tiers keep combo identity hidden; judge calibration itself stays in ri-08 |
| `implement-the-task-router-*`, `make-the-orchestrator-obey-the-router` | **Follow-ups** — enforcement/execution of routing decisions is out of scope |
| `build-agent-trajectory-scenario-harness` (29/34) | **Complementary** — scenario parity matrix stays; combo adapters may share vendor CLI invocation code |

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Budget safety | OpenRouter USD per sweep job | ≤ $50, refuse trials beyond cap | VALIDATE (ledger test) |
| Corpus integrity | Holdout runs without decision flag | 0 (runner refuses) | VALIDATE |
| Provenance | Prior rows without source+combo key | 0 (NOT NULL constraints) | VALIDATE (migration test) |
| Reproducibility | Converter re-run on same archive entry | Byte-identical task dir (modulo timestamps) | IMPL_REVIEW |
| Routing safety | Behavior with ROUTING_ADAPTIVE off | Identical to current resolver (golden test) | VALIDATE |

## Approaches Considered

### Approach A — Harbor substrate subsuming ri-05 (Recommended)

New `packages/harbor-bench/` builds converter, 5-vendor sweep runner, and prior
importer on Harbor's task format and harness; lands migration 035 and the flagged
read-path in the same change.

- **Pros**: container isolation per trial (agent cannot peek at the withheld
  implementation diff — ri-05's hardest requirement, solved by construction);
  built-in claude-code/codex adapters and per-trial token/cost capture for free;
  parallel execution scales to the full dev split later; one benchmark serves both
  the routing sweep and the rightsizing A/B; unblocks the stalled router.
- **Cons**: new external dependency (harbor) to pin and track; three custom
  `BaseAgent` adapters to build (grok/antigravity/pi); Docker-in-the-loop makes CI
  integration heavier; migration ownership moves partially out of
  `add-adaptive-model-router` and both task lists must be reconciled.
- **Effort**: L (decomposed into M-sized packages below).

### Approach B — Extend `packages/agent-scenarios` instead of Harbor

Build the sweep on the nearly-done cross-vendor trajectory harness (29/34 tasks),
adding archive-replay scenarios and a prior importer; no new dependency.

- **Pros**: no external dependency; vendor invocation plumbing largely exists;
  lighter than containers for subscription-vendor CLIs already installed locally.
- **Cons**: no filesystem isolation — the withheld-diff guarantee (ri-05) must be
  reimplemented by hand and is easy to get wrong; no standardized task/verifier
  format to share or compare externally; no per-trial container reproducibility;
  scenario harness measures trajectories, not repo-level task completion, so the
  verifier layer is built from scratch anyway.
- **Effort**: L (similar build, weaker guarantees).

### Approach C — File-based priors, benchmark-only (no router touch)

Converter + sweep runner on Harbor, but the importer emits a versioned
`priors.json`; no migration, no read-path; router integration deferred entirely.

- **Pros**: smallest blast radius (`model_routing` untouched); no migration
  sequencing questions; fastest to a first scorecard.
- **Cons**: fails the stated goal — nothing in production consumes the priors, the
  router stays stalled, and hand-picking continues; a second change must redo the
  import against real tables later.
- **Effort**: M.

**Recommendation: Approach A.** It is the only approach that satisfies both stated
goals (evidence-based routing *and* unblocking the router) — C fails the goals by
design, and B rebuilds Harbor's hardest guarantees (isolation, verifier format,
per-trial metrics) by hand while still leaving the same router integration work. A's
main cost, the new dependency, is mitigated by pinning and by keeping all Harbor
usage inside one package boundary.

### Selected Approach

**Approach A — Harbor substrate subsuming ri-05** (Gate 1, 2026-09-01; latent-intent
check passed: user confirmed A matches the underlying need of evidence-based routing
plus unblocking the adaptive router). User-directed modifications from discovery:

- All 5 vendors are in the pilot sweep. claude/codex/grok/antigravity are
  subscription vendors whose sweep cost is usage-limit headroom, not USD; `pi` via
  OpenRouter is the only USD-metered vendor. The $50 ledger cap therefore applies to
  OpenRouter spend per job; subscription vendors are throttled by quota-headroom
  policy instead of dollars.
- Success criteria fixed at: (1) `resolve_for_phase` ranks with imported priors
  behind `ROUTING_ADAPTIVE` (default off), (2) per-combo × task_type scorecard over
  the dev split. Counterfactual cost-reduction analysis is explicitly deferred.
- Exploration and live posterior feedback remain in `add-adaptive-model-router`.

Approaches B (agent-scenarios substrate) and C (file-based priors) were considered
and rejected; see above for their trade-offs.
