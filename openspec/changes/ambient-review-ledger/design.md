# Design: Ambient Continuous Review with a Self-Verifying Finding Ledger

## Context

This change adds a continuous, commit-granular review *sensor* beneath the
existing gate-time consensus *gates*. It reuses the established finding/consensus
schemas and synthesis machinery rather than inventing parallel ones. Five phases;
Phase 0 de-risks an overlap with the in-progress `harness-engineering-features`.

## Decisions

### D1 — Local-first ledger, coordinator sync best-effort

The ledger's source of truth is a local directory (`.review-ledger/`). Coordinator
sync (`memory`/`audit`) is best-effort and idempotent on a stable finding id.

- **Rationale**: Honors the operator's local-first decision; keeps ambient review
  working offline / under degraded network. Mirrors the durability pattern in
  `checkpoint_findings.py` (write locally first, sync opportunistically).
- **Trade-off**: Accepts a local/remote reconciliation path in exchange for
  resilience. Rejected coordinator-only storage (Approach B) because it breaks
  offline use and can't see commits until they're registered server-side.
- **capability**: ambient-review-ledger

### D2 — Stable finding id derived from content, not sequence

Findings are keyed by a stable id derived from `(file_path, normalized
line anchor, type, normalized description)` rather than the schema's per-review
integer `id`. This makes dedup, lifecycle transitions, coordinator sync, and
GitHub-issue mapping idempotent across re-reviews and `compact` runs.

- **Rationale**: The existing `review-findings.schema.json` `id` is a per-review
  integer; ambient review re-reviews the same code repeatedly, so we need an
  identity that's stable across runs. Reuses `consensus_synthesizer`'s matching
  primitives to compute equivalence.
- **Trade-off**: Content-derived ids can drift if a line moves; `compact`
  re-anchors them. Rejected raw line-number keys (too brittle under edits).
- **capability**: ambient-review-ledger

### D3 — `refine-core` extraction is behavior-preserving (Phase 0 first)

Extract iterate/synthesize/fix/validate primitives from `convergence_loop.py`
into `skills/parallel-infrastructure/scripts/refine_core.py`. `converge()`
becomes a thin caller of `refine-core`. No behavior change; covered by the
existing convergence tests plus a characterization test asserting identical
outputs before/after.

- **Rationale**: Both this change (Phase 3) and `harness-engineering-features`
  Feature 1 need to touch the convergence machinery. A shared module converts a
  merge-conflict risk into a shared dependency. Phase 0 lands first.
- **Trade-off**: Adds an indirection layer. Accepted because it unblocks two
  changes cleanly. Must be coordinated with the `harness-engineering-features`
  owner so they rebase onto `refine-core`.
- **capability**: refine-loop

### D4 — Ambient review is single-vendor and read-only

Ambient review dispatches to exactly one vendor (configured ambient archetype,
default fast tier) and has no fix authority. Multi-vendor consensus and fix
authority remain exclusively gate/refine concerns.

- **Rationale**: Keeps per-commit cost and latency low; preserves the "consensus
  is a gate property" invariant; limits prompt-injection blast radius (read-only).
- **Trade-off**: Single-vendor ambient findings are lower-confidence — that's
  acceptable because the gate still runs full consensus, and `compact` suppresses
  noise. A new `review_type` value (e.g. `ambient`) is added to the findings
  schema enum to distinguish ambient from gate findings.
- **capability**: ambient-review

### D5 — `compact` reuses consensus matching for dedup

`compact` consolidates duplicate findings using the existing
`consensus_synthesizer` matching logic (location match, file+description,
type+description with Jaccard threshold) rather than a new matcher.

- **Rationale**: Single source of matching truth; avoids a third dedup
  implementation (CLAUDE.md warns against parallel copies of shared logic).
- **capability**: review-ledger

### D6 — Hook mirrors the existing `.githooks` resolution pattern

`post-commit` follows the same structure as `post-merge`: resolve repo root,
prefer an env override seam for tests, locate the venv python, fail open
(non-blocking, exit 0) on any error.

- **Rationale**: Consistency with the existing hook contract; testability via the
  env seam; never block a developer's commit.
- **capability**: ambient-review

## Schema impact

- `review-findings.schema.json`: add an `ambient` value to the `review_type`
  enum (additive, backward-compatible). Findings otherwise unchanged.
- New `review-ledger.schema.json`: ledger entry = a finding plus
  `{ stable_id, lifecycle_state, first_seen_sha, last_verified_sha,
  issue_number?, transitions[] }`.

## Open questions

- Exact ambient archetype/tier default (`economy` vs `standard`) — to be set in
  config; defaults to the fast tier pending a cost measurement during Phase 1.
- Whether `compact` runs on a timer, on each `post-commit`, or only at gate
  entry — start with "on gate entry + manual", revisit after Phase 2 telemetry.
