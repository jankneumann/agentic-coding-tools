# Design: add-harbor-benchmark-routing

## Context

Selected approach (Gate 1): Harbor execution substrate subsuming ri-05, feeding
priors into the adaptive router's tables and a flagged read-path in
`resolve_for_phase`. All Harbor usage is confined to `packages/harbor-bench/`.

## Decisions

### D1 — Harbor is a pinned, package-local dependency

`harbor` is added only to `packages/harbor-bench/pyproject.toml`, pinned to an exact
version, never to `agent-coordinator` or `skills`. The coordinator consumes benchmark
*results* (via the importer), never Harbor APIs. If Harbor is abandoned or breaks,
the blast radius is one package.

- Rejected: repo-wide dependency (couples the coordinator to an eval framework);
  vendoring (maintenance burden, upstream moves fast).

### D2 — `combo` is the sweep unit; "arm" stays reserved

A combo is `{vendor, model, thinking, harness}` recorded per trial. `harness`
identifies the executing agent adapter (e.g. `claude-code@<harbor-ver>`,
`codex-cli@<ver>`, `harbor-bench/grok-adapter@<sha>`), distinct from `vendor`
because one vendor can be driven by different harnesses. "Arm" keeps its
rightsizing-roadmap meaning (skills-before/after); the shared scorecard schema gets a
`combo` field so both studies can coexist without ambiguity. Thinking values are
vendor-specific free-form strings, exactly as in `archetypes.yaml`'s
`{model, thinking}` tier entries — no cross-vendor normalization is attempted.

### D3 — Migration 035 lands the catalog, posteriors, and import ledger only

`035_model_routing.sql` is derived from
`openspec/changes/add-adaptive-model-router/contracts/db/schema.sql` but deliberately
lands only the three tables the importer and read-path need:

- `model_catalog` — adds `thinking TEXT` to the contract's key so codex
  frontier/premium (same model, different thinking) are distinct candidates; adds
  `benchmark_prior NUMERIC` with `prior_source TEXT NOT NULL` provenance.
- `model_posteriors` — keyed `(catalog_id, task_type, metric)` per the contract,
  with `source TEXT NOT NULL` (`harbor-replay` for this change) and `sample_size`.
- `model_posterior_imports` — the per-job import ledger that makes re-import
  idempotent (see below).

Idempotency is carried by the ledger, not by a "last job" column. A single
`last_job_id` on the posterior row only remembers the most recent import, so the
sequence *import A → import B → import A again* leaves `last_job_id = A` after the
third step and double-counts A's trials into an aggregate that already contains them.
Because the importer folds many jobs into one posterior row, the identity of **every**
contributing job has to survive.

`model_posterior_imports` therefore stores one row per
`(job_id, catalog_id, task_type, metric, source)` holding that job's own
contribution (`sum_value`, `sample_size`, `graded_by`), under a UNIQUE constraint on
that tuple. The importer writes ledger rows with `ON CONFLICT ... DO UPDATE` — so a
replay of any job, in any order, overwrites that job's contribution instead of adding
to it — and then recomputes the `model_posteriors` row as a deterministic aggregate
over its ledger rows. Re-importing an already-seen job is a no-op on the aggregate by
construction rather than by a guard the importer has to remember to check.

`routing_decisions` and `routing_spend_ledger` remain with
`add-adaptive-model-router` (they serve live-dispatch logging, which this change does
not do). The pilot's $50 OpenRouter cap is enforced inside the sweep runner from
Harbor's per-trial cost records, not from the coordinator ledger. That change's
tasks.md must be annotated on approval: its migration task becomes "extend 035", not
"create".

- Rejected: landing all four router tables (claims scope this change can't verify);
  file-based priors (fails the read-path goal); a `last_job_id` column on the
  posterior row (only idempotent across a single-job history); an importer-side
  "seen jobs" set (not durable across importer processes).

### D4 — Budget model: USD cap for OpenRouter, headroom throttle for subscriptions

Vendors are classed `metered` (pi/OpenRouter) or `subscription`
(claude_code, codex, grok, antigravity) in the sweep config. Subscription vendors are
throttled by a per-vendor max-trials-per-window setting (quota headroom is not
programmatically readable for all vendors; the window setting is the enforceable
proxy). Every trial record stores `cost_usd` (metered) or `cost_usd = NULL` + token
counts (subscription), so the scorecard reports cost in the unit that actually
constrains each vendor.

The metered cap is enforced by **reservation, not by observation**. A trial's true
cost is only known once it finishes, so a check of the form
`accumulated_actual >= cap` admits any trial while the counter is still under the cap
and can overshoot by a full trial cost — or, with `attempts` fanned out in parallel,
by several at once. The runner therefore keeps three quantities per job:

- `spent_usd` — summed actual cost of completed metered trials,
- `reserved_usd` — summed estimates of metered trials currently in flight,
- `estimate(trial)` — a conservative upper bound for one trial, computed before
  launch from the combo's `prompt_usd_per_mtok`/`completion_usd_per_mtok` and the
  task's configured max token budget (the same ceiling the adapter enforces), with a
  configured `cost_estimate_safety_factor` (default 1.25) applied.

Admission is `spent_usd + reserved_usd + estimate(next) <= cap`; a trial that fails
this check is refused, not queued, and the refusal is recorded in the job summary
with the three quantities that produced it. On completion the trial's reservation is
released and its actual cost added to `spent_usd`. Because the estimate is an upper
bound, `spent_usd` converges from above: the cap binds a *worst case*, so the job can
finish under budget but never over it. A trial whose actual cost exceeds its own
estimate (a mispriced model, a runaway adapter) is recorded as a
`cost_estimate_exceeded` job-summary event so the safety factor can be re-tuned
rather than silently absorbed.

- Rejected: post-hoc reconciliation (over-spend already happened); serializing
  metered trials to one at a time (correct but throws away the parallelism the sweep
  needs to finish).

### D5 — Corpus manifest: ri-02 method, re-sealed at 114

The manifest generator implements ri-02's declared method over the current archive
(114 changes): dev/holdout partition, holdout biased toward post-2026-05-01 entries,
SHA-256 checksum of the assignment, and a runner that refuses holdout tasks unless
`--decision-run` is passed. The 92-change split described in the rightsizing roadmap
was never generated, so there is no compatibility to preserve — this manifest becomes
the sealed one, and ri-02 is marked absorbed.

### D6 — Verifier ladder, deterministic-first

Per converted task, the verifier composes (highest tier available wins the reward):

1. **Scenario tests** — executable checks derived from the change's own
   Given/When/Then delta-spec scenarios plus tests the original implementation
   added; reward = weighted pass fraction.
2. **Repo gates** — lint/typecheck/existing-suite pass as a floor multiplier.
3. **LLM-judge** (flagged per task, default off) — only for archive entries whose
   scenarios aren't mechanically checkable; the judge prompt receives the diff and
   scenarios but never the combo identity (ri-08 blinding constraint), and
   judge-scored rewards are marked `graded_by: judge` so the importer can weight or
   exclude them.

Tasks where the converter cannot produce a tier-1 or tier-2 verifier are excluded
from the sealed manifest rather than judge-scored by default — thin verifiers poison
priors.

### D7 — task_type is a change-level reduction of `package_kind`

Trial records and posterior keys use the existing controlled vocabulary
`metadata.package_kind` (`algorithm|data_model|crud|config|migration|integration`).
No new taxonomy is invented. But a trial carries exactly one `task_type` while an
archived change carries one `package_kind` *per work package*, so a deterministic
reduction is required — without one, conversion either fails or labels trials
arbitrarily and corrupts the task-type posteriors. Over the current archive the
multi-kind case is not a corner case, it is the common one. Of 115 archived changes:

- 46 have no `work-packages.yaml` at all;
- 35 have one but declare no `metadata.package_kind` (they predate the field);
- 34 declare at least one kind — and **28 of those 34 declare two or more distinct
  kinds** (7 declare four, e.g. `2026-04-09-add-software-factory-tooling`).

So only 6 archived changes have an unambiguous declared kind, and 81 have no declared
kind at all. Two consequences follow. First, the reduction below is the normal path
for declared changes, not an edge case. Second — and this is the sharper one — the
inference fallback carries roughly 70% of the corpus, so it is a load-bearing rule
rather than a safety net, and its own determinism is what actually governs most
task-type labels.

The converter reduces in four ordered steps, and every step is recorded on the trial
record so a suspicious posterior can be traced back to how its label was chosen:

1. **Collect and normalize.** Read every package's `metadata.package_kind`. Values
   outside the controlled vocabulary are *legacy*: they contribute no weight and are
   not remapped. The only such value in the current archive is `feature`
   (`2026-04-22-vendor-ux-enhancements`, 3 of its 4 packages); it predates the
   vocabulary and spans what are now several distinct kinds, so guessing a modern
   equivalent would invent signal that was never declared.
2. **Weight.** Each in-vocabulary package contributes its `metadata.loc_estimate`.
   Where `loc_estimate` is absent for every package in a change (one entry today,
   `2026-08-26-introduce-fitness-function-gates`), each package contributes weight 1
   instead, so the reduction degrades to a package count rather than failing.
3. **Reduce.** `task_type` is the kind with the greatest summed weight. Ties break by
   the fixed precedence `algorithm > data_model > migration > integration > crud >
   config`, chosen so the more specific kind wins over the more generic one. A change
   whose kinds all reduce from a single declared value is stamped
   `task_type_source: declared`; one reduced from two or more distinct kinds is
   stamped `declared_dominant`.
4. **Infer where nothing is declared.** A change with no `work-packages.yaml`, one
   that declares no `package_kind`, or one whose declared kinds are all legacy, falls
   through to inference from the delta-spec capability and is stamped
   `task_type_source: inferred`. This is the path for 81 of the 115 archived changes,
   so the inference rule must itself be deterministic and reproducible — it is
   specified and tested at task 2.8, not left to the converter's discretion. A change
   whose capability does not map to exactly one vocabulary value is excluded from the
   corpus with a recorded reason, on the same principle as D6's verifier ladder: a
   guessed label poisons a posterior as surely as a thin verifier does.

Whatever the path, the trial record also carries `task_type_mix` — the normalized
per-kind weights the reduction consumed — so the scorecard and the importer can
down-weight or exclude trials whose label rests on a thin plurality, and so a
posterior built from `declared_dominant` labels is never mistaken for one built from
unambiguous ones.

- Rejected: mapping `feature` onto a modern kind (fabricates a declaration);
  splitting a multi-kind change into one trial per package (the Harbor instruction is
  the change's whole `proposal.md`, so per-package trials would score the same work
  several times); first-package-wins (order in `work-packages.yaml` is not
  meaningful).

### D8 — Read-path: `ROUTING_ADAPTIVE` flag, golden-parity default

`resolve_for_phase` gains a mode switch: when `ROUTING_ADAPTIVE` is unset/off, the
code path is byte-for-byte the current static resolution (guarded by a golden test
capturing today's outputs for all 15 phases). When on, candidates are built from
`model_catalog` rows for the phase's archetype tier-set and ranked via
`model_routing.resolver.score_and_rank()` under the `balanced` objective profile;
the chosen `{provider, model, thinking}` replaces the static lookup, and the
response's `reasons[]` records `routing=adaptive` plus the ranking provenance.
Escalation rules and `write_capable`/trust constraints apply unchanged in both modes
(they filter candidates, not scores). Exploration is explicitly NOT wired.

**Prerequisite — the scorer must carry `thinking` first.** `CandidateInput` and
`ScoredCandidate` in `agent-coordinator/src/model_routing/resolver.py` are keyed
today on `(vendor, model, endpoint_kind)` only. Two catalog rows that share vendor
and model but differ in thinking — codex frontier vs premium, the grok tiers, i.e.
precisely the distinction this change exists to measure — collapse into
indistinguishable candidates, and `score_and_rank()` cannot report which thinking
tier won. The read-path therefore cannot return a `thinking` value at all until both
dataclasses gain a `thinking: str = ""` field carried from `model_catalog.thinking`
through to the ranked result.

That extension lands in `wp-db-import` alongside the D9 feedback re-keying, not in
`wp-readpath`: `resolver.py` sits under `agent-coordinator/src/model_routing/`, which
is `wp-db-import`'s write scope, and `wp-readpath` depends on it. Sequencing the two
the other way round would leave `wp-readpath` unable to implement its own spec
scenario within its scope.

### D9 — Feedback re-keying before any fit

`model_routing/feedback.py` normalizers currently emit `model_id = vendor`, which
collapses thinking tiers. They are re-keyed to `(vendor, model, thinking)` composite
model ids in the same form the catalog uses, with a compatibility shim for
existing readers, before the importer writes anything. This ordering is mandatory:
priors fitted under the old keying would be unusable.

### D10 — Container runtime is podman, not Docker

This repo standardizes on **podman** (user directive, 2026-09-01). Harbor's local
execution provisions environments through the Docker Engine API, so the sweep runner
targets podman's Docker-compatible API socket: it verifies/starts
`podman.socket` (rootless preferred) and exports
`DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock` (or the rootful
`/run/podman/podman.sock`) for the Harbor process. Task-environment `Dockerfile`s
are written to the OCI-compatible subset both runtimes build. The pilot smoke test
(1 task × 1 combo) runs against podman and is the acceptance check for this
decision; if a Harbor feature proves hard-incompatible with the podman socket, that
is a blocker to surface, not a reason to install Docker.

- Rejected: installing Docker alongside podman (violates repo runtime convention);
  cloud sandbox providers (Daytona/Modal) as the workaround (out of scope for v1
  per discovery — adds account/credential setup).

## Risks

- **Contamination**: archived changes are public on GitHub; absolute rewards may be
  inflated. Mitigation: priors are used comparatively across combos on the same task
  distribution; the scorecard reports per-combo deltas, not absolute claims.
- **Instruction under-specification**: some proposals assume unstated context.
  Mitigation: pilot triage step reviews failing tasks for instruction-vs-capability
  failure before any prior import; ambiguous tasks are excluded from the manifest.
- **Harbor API drift**: pinned version + one adapter boundary module
  (`harbor_bench/harbor_io.py`) that owns all Harbor imports.
- **Container runtime unavailability in CI**: converter/importer/read-path tests
  are pure; only the sweep smoke test needs a container runtime and is marked
  `integration`.

## Task decomposition note

Two L-sized areas were split per the sizing rule: the converter (split into
instruction/environment emission vs verifier emission) and the sweep runner (split
into runner core vs budget/throttle policy). No XL tasks remain.
