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

### D3 — Migration 035 lands `model_catalog` + `model_posteriors` only

`035_model_routing.sql` is derived from
`openspec/changes/add-adaptive-model-router/contracts/db/schema.sql` but deliberately
lands only the two tables the importer and read-path need:

- `model_catalog` — adds `thinking TEXT` to the contract's key so codex
  frontier/premium (same model, different thinking) are distinct candidates; adds
  `benchmark_prior NUMERIC` with `prior_source TEXT NOT NULL` provenance.
- `model_posteriors` — keyed `(catalog_id, task_type, metric)` per the contract,
  with `source TEXT NOT NULL` (`harbor-replay` for this change) and `sample_size`.

`routing_decisions` and `routing_spend_ledger` remain with
`add-adaptive-model-router` (they serve live-dispatch logging, which this change does
not do). The pilot's $50 OpenRouter cap is enforced inside the sweep runner from
Harbor's per-trial cost records, not from the coordinator ledger. That change's
tasks.md must be annotated on approval: its migration task becomes "extend 035", not
"create".

- Rejected: landing all four tables (claims scope this change can't verify);
  file-based priors (fails the read-path goal).

### D4 — Budget model: USD cap for OpenRouter, headroom throttle for subscriptions

Vendors are classed `metered` (pi/OpenRouter) or `subscription`
(claude_code, codex, grok, antigravity) in the sweep config. A sweep job refuses to
start a new metered trial once accumulated OpenRouter cost ≥ the job cap
(default $50). Subscription vendors are throttled by a per-vendor
max-trials-per-window setting (quota headroom is not programmatically readable for
all vendors; the window setting is the enforceable proxy). Every trial record stores
`cost_usd` (metered) or `cost_usd = NULL` + token counts (subscription), so the
scorecard reports cost in the unit that actually constrains each vendor.

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

### D7 — task_type comes from `package_kind`

Trial records and posterior keys use the existing controlled vocabulary
`metadata.package_kind` (`algorithm|data_model|crud|config|migration|integration`)
extracted from each archived change's `work-packages.yaml` where present, else
inferred by the converter from the delta-spec capability and recorded with
`task_type_source: inferred`. No new taxonomy is invented.

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
