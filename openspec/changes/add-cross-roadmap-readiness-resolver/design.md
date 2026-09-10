# Design: Cross-Roadmap Readiness Resolver

## Context

ri-17 made cross-roadmap dependencies traversable through `external_depends_on`, but execution admission remains split. Autopilot consults checkpoint terminal sets; supervise consults roadmap status only. The durable-state contract requires checkpoint truth to win when it exists and requires invalid canonical state to be reported rather than reconstructed from advisory sources.

## Decisions

### D1 — One admission helper in roadmap-runtime

`skills/roadmap-runtime/scripts/readiness.py` owns the only function definition named `_get_ready_items`. `autopilot-roadmap` and the repository-wide resolver import it. The helper's signature and behavior preserve the current autopilot contract: approved/in-progress admission, `superseded_by` exclusion, checkpoint completed/failed exclusion, local dependency completion from checkpoint, typed external completion input, and stable priority ordering.

Alternative: make `Roadmap.ready_items` the sole helper. Rejected because it lacks checkpoint terminal state and changing its established first-run model semantics would broaden ri-16.

### D2 — Checkpoint-aware effective completion

For a workspace with a valid matching checkpoint, its `completed_items` and `failed_items` are authoritative. For a workspace with no checkpoint, roadmap item statuses represent the valid never-started baseline. Cross-roadmap completion refs are derived from those effective terminal sets before any workspace is admitted.

A checkpoint is inconsistent when it has an identity mismatch, names unknown terminal item IDs, duplicates an item across completed/failed sets, or disagrees with terminal roadmap statuses. Inconsistent/invalid workspaces are stale and withheld from readiness. A normal short-lived roadmap/checkpoint ordering mismatch is reported instead of silently guessed.

Alternative: union roadmap and checkpoint completions. Rejected because it promotes stale roadmap status over the canonical checkpoint and can unblock dependents incorrectly.

### D3 — Content-derived staleness token

The report contract carries `source_fingerprint`, the SHA-256 of a canonical serialization of every readiness-relevant roadmap/checkpoint input, plus a top-level `stale` consistency boolean and a sorted `diagnostics` list. A later materialized projection stores the fingerprint and compares it to a fresh resolver result; inequality is the meaningful staleness signal. Diagnostics name workspace and reason codes derived only from parsed roadmap/checkpoint content. Missing checkpoint is recorded as `checkpoint_absent` informational state, not stale, because first-run absence is valid.

No timestamps are generated and no mtimes are read. The command serializes with stable key/list ordering and a trailing newline. The boolean reports canonical input inconsistency, while the fingerprint lets downstream projections detect drift.

Alternative: compare file timestamps or emit `generated_at`. Rejected because identical content could produce different bytes across runs or clones.

### D4 — Global ordering and compatibility projection

The canonical `ready` array is sorted by `(priority, roadmap_id, item_id)` and each entry contains `roadmap_id`, `item_id`, `priority`, `effort`, `change_id`, and `title`. The supervisor wrapper groups canonical entries by roadmap id without re-evaluating readiness so its current callers remain compatible.

Alternative: retain grouped per-roadmap ordering as the canonical form. Rejected because it cannot answer one ranked ready-now list across the repository.

### D5 — Read-only CLI boundary

`resolve_readiness.py --repo-root <path>` reads only active `openspec/roadmaps/*/roadmap.yaml` files and sibling `checkpoint.json` files, prints the schema-validated result, and performs no writes or network calls. Malformed canonical input produces deterministic diagnostics and a non-zero exit without ready entries from the affected workspace.

Alternative: ingest learnings, handoffs, or queue rows to enrich ranking. Rejected because those artifacts are advisory/projection state and would violate authority and determinism.

## Risks and mitigations

- Bare-module import collisions: load/add the runtime script directory explicitly, matching existing skill-script conventions; pin imports with AST tests.
- Existing roadmap/checkpoint drift: surface bounded diagnostics and withhold rather than silently unblock.
- Compatibility drift in supervise output: retain its grouped wrapper and existing tests while adding canonical flat-output tests.
- Schema drift: define a change-local JSON Schema contract and validate representative command output.

## Rollback

Revert the single feature commit. Autopilot's old helper and supervise's old projection can be restored without data migration because the change adds no persisted state or schema mutation.

