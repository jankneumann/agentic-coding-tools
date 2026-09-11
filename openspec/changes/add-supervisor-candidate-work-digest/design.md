# Design — add supervisor candidate-work digest

## Context

The cycle's digest is prose with no memory; stubs have no home; approval hands over a
proposal path a stub does not have. The design gives stubs a tracked store, splits ranking
into model judgment (schema-constrained) and script arithmetic (weights, signals, caching),
and routes approval through `refine-roadmap`'s transaction. Approach 1 (Gate 1).

## D1 — Stub store: one tracked file per stub, lifecycle elsewhere

**Decision.** `openspec/supervise/candidates/<encoded-stub-key>.json`, written by SENSE after
dedupe with `indent=2, sort_keys=True` and a trailing newline. The file is the stub payload
exactly as validated against `candidate-work.schema.json`; nothing else. Lifecycle
(`pending | approved | deferred | rejected`) is in `back_edge.digested_stubs`.

**Why files, not the handoff.** The handoff is a transport (change 2, D4); carrying every
stub in it makes each handoff grow with the backlog. Files are git-truth, diffable in PRs,
and already inside `_ALLOWED_WRITE_PREFIXES`. **Why lifecycle elsewhere.** A decision is a
supervisor fact, not a finding fact; keeping the file byte-identical to the validated stub
lets `stub_key` stay stable and lets ri-12's generators overwrite a stub without clobbering
a decision.

**`stub_key` as filename.** Only `change:<valid-change-id>` and `prov:<hex32>` are
accepted, including at the CLI boundary. They encode as `change--<id>` and
`prov--<hex32>`; decoding revalidates the canonical form before any path is joined.
The rank input is the union of fresh post-dedupe stubs and retained pending/deferred
store files, deduplicated by key. Before the unchanged-fingerprint gate, `store
--prune-only` removes terminal files and reports whether a deferred `until` is due;
a due transition bypasses the early exit and re-ranks from cached scores.

## D2 — Ranking: rubric sub-agent scores, script ranks

**Decision.** Five factors, each an integer 1–5 with a ≤200-char justification:

| Factor | Question the sub-agent answers | Evidence it is given |
|---|---|---|
| `relevance` | Is the finding still true on the current tree? | stub + provenance artifact excerpt |
| `value` | What changes for users/operators if this lands? | stub, roadmap proposals it maps to |
| `readiness` | Could an implementer start today? | ready set, active changes |
| `scope_fit` | Is it one change, or several, or a fragment? | stub `effort`, sibling stubs |
| `risk` | Blast radius if it goes wrong | stub `tags`, provenance generator |

`digest.py rank` validates the scores (`rubric-score.schema.json`) and requires score
keys to be a unique exact match for the requested batch manifest. The manifest is emitted
by `digest.py prepare-batch --as-of <RFC3339>`; `--as-of` is supplied by the host, copied
into the prompt, and MUST equal the score document's `scored_at` exactly. A model-produced
timestamp that differs from the manifest is rejected before any cache or digest write.
The script computes mechanical signals itself — `dependency_ready` from a strict index of
all roadmap item/change statuses plus archived changes, `staleness_days` as of the trusted
manifest time, and `prior_decision`. An empty dependency list is ready; a dependency is
ready only when its referenced item/change is completed or archived-completed; pending,
blocked, unresolved, and pending-stub dependencies are not ready. Risk is
inverted: 5 means safest. The fixed score is `3*relevance + 3*value + 2*readiness +
scope_fit + risk - min(floor(staleness_days / 30), 5)`; null staleness has no penalty
and is marked degraded. The total order is: pending before future-deferred,
dependency-ready before blocked, descending score, then ascending `stub_key`.
Rejected stubs are excluded. These constants and buckets are emitted in `weights`, so
a reader can recompute every rank and tied inputs always have one answer.

**Why not deterministic-only.** A formula over `priority`/`effort`/readiness/staleness
cannot judge relevance or value — it would rank a stale-but-high-priority finding above a
fresh, important one. **Why not model-only.** The skill promises that an unchanged tree
re-runs identically; a free-form ranking cannot keep that promise. The split keeps each
half where it is strong and makes the join point (the score file) inspectable.

**Reproducibility.** Each cache is a schema-valid singleton rubric document at
`<encoded-stub-key>.rubric.json`. The cycle fingerprint excludes the candidate store,
rubric caches, and `digest.json`, as it already excludes ledger/mirror state, so writing
supervisor outputs cannot self-invalidate it. Unchanged fingerprint plus no due lifecycle
transition means no dispatch and byte-for-byte reuse of the validated prior digest. A
changed fingerprint re-scores the retained-plus-fresh backlog in one bounded batch. The
store admits at most 20 surviving candidates; a would-be 21st candidate makes `store`
fail atomically, leaves the prior store/digest untouched, and returns a degraded overflow
record naming every unpersisted key so the host can carry those upstream inputs into the
next cycle. This deliberately chooses a hard, visible capacity bound over unbounded model
cost. `generated_at` is the host-owned manifest `as_of`, and persisted output contains no
reuse/cache flags. Staleness uses that same trusted clock, not model-selected or wall time.

**Where the model is called.** From `SKILL.md`, by the host, as a sub-agent with the
`templates/rubric-prompt.md` prompt and the batch as input, returning JSON only. Never from
`scripts/` — `TestHostAssistedInvariant` covers `digest.py` automatically because it walks
the whole directory.

## D3 — `digest.py` owns behavior; `cycle_state.py` exposes narrow state helpers

**Decision.** `store`, `prepare-batch`, `rank`, `digest`, `stub-to-request`, `decide` live in
`skills/supervise/scripts/digest.py`, importing `stub_key`, `compute_fingerprint`,
`load_ledger`, `classify_write`, and `write_mirror` from
`cycle_state`. `cycle_state.py` changes only to exclude derived supervisor artifacts
from the cycle fingerprint and to preserve the extended `digested_stubs` fields.

**Why.** `cycle_state.py` is 586 lines of idempotency machinery with its own CLI; adding
five subcommands and ranking logic there would double it. The narrow helper changes keep
state normalization in its existing owner while the digest module and prompt template
remain independently implementable after the contract package lands.

## D4 — Approval goes through `refine-roadmap`, never a supervise-side roadmap write

**Decision.** `digest.py stub-to-request` renders a request YAML; the host runs
`refiner.py preview` then `apply --expect-base-sha256`. Field mapping:

| Stub | Roadmap item |
|---|---|
| `title` | `title` |
| `description` + `\n\nProvenance: <source_artifact> (<finding_ids>)` | `description` |
| `rationale` | `rationale` |
| `effort` | `effort` |
| `priority` | copied as the item's explicit numeric priority |
| target-roadmap change dependency | local `depends_on: [ri-NN]` |
| other-roadmap change dependency | `external_depends_on: [roadmap-id:ri-NN]` |
| archived-completed dependency | omitted as already satisfied |
| `suggested_change_id` | `change_id` (refiner rejects collisions) |
| — | `item_id`: next free `ri-NN` |
| — | `acceptance_outcomes`: from `--acceptance`, required |

Already-qualified roadmap refs are validated and preserved. `change:<id>` candidate refs
are normalized before resolution; unresolved `prov:` or change refs fail closed and name
the dependency for operator disposition. `--after` selects YAML insertion position only;
it does not alter the explicit priority, and this change does not claim that refiner
renumbers priorities after an add.

**Why the host drafts acceptance outcomes.** They are the one roadmap field a stub cannot
supply and the one `refine-roadmap` refuses to accept empty. Drafting them in conversation
is the operator's confirmation step — the "yes" is a yes to specific outcomes.

**Why not `plan-roadmap --force`.** `refine-roadmap/SKILL.md:122` says it plainly: `--force`
replaces the artifact and erases statuses and provenance. The transaction is the point.

## D5 — `decide` writes the supervisor record's `back_edge`; the cycle prunes

**Decision.** `rank` synchronizes every ranked pending/deferred stub into
`back_edge.digested_stubs`, using the score evidence time as `decided_at` for a new
pending observation and preserving existing decision timestamps. `digest.py decide`
accepts the rehydrated record, replaces the matching entry, and calls `write_mirror`, so
a newer handoff's unrelated gates, decisions, and back-edge entries survive. The
canonical record schemas and `_clean_digested_stub` preserve `roadmap_ref`, `route`,
`until`, and `reason`; decision-specific validation requires a route for approval, a
roadmap ref for `refine-roadmap`, null for `plan-roadmap`, and a reason for rejection.
The next CYCLE's pre-fingerprint `store --prune-only` removes approved/rejected files and
caches. Deferred files remain; when `until` is due, maintenance requests a cache-only
re-rank and the decision becomes pending even if the tree fingerprint is unchanged.

**Why prune next cycle, not immediately.** `decide` may run several times in one
conversation; preflight pruning keeps cleanup inside the next audited CYCLE and, unlike
the old post-SENSE placement, still runs on an otherwise unchanged tree.

## D6 — Digest artifact and the unchanged-fingerprint path

`digest.json` is deliberately candidate-work-focused:
`{schema_version, fingerprint, generated_at, weights, sections:
{needs_decision[], new_this_cycle[], degraded[]}, ranked:[...]}`. `new_this_cycle` contains
only keys freshly stored in this cycle; retained pending/deferred keys go under
`needs_decision`; `ranked` contains the full retained-plus-fresh backlog. The host merges
these three candidate additions into the existing five-section digest after it has
rendered pending gates (including deadlines), ready work, blockers, and degraded sensors.
The candidate artifact cannot erase or replace those operational lines.

`generated_at` is the host-owned batch-manifest `as_of`, not model or render time.
`cached_scores` and `reused_prior` are stdout diagnostics, not persisted fields. When
`cycle_state.py fingerprint` reports unchanged and maintenance reports no due transition,
the skill schema-validates and re-presents the prior bytes. A due deferral is the explicit
exception: maintenance changes the decision bucket using the host-owned `--as-of`, then
rebuilds the digest from the existing validated cache without dispatching a scorer.

## D7 — Sequencing

- ri-05's `back_edge` slot/mirror and ri-16's cross-roadmap resolver are on main. This
  change extends their stable contracts rather than carrying a mirror-only fallback.
- ri-12 (generators emit stubs) is the real producer; fixtures stand in until then.
- `TestWorkflowContract` string assertions move with the reworded CYCLE sections.

## D8 — Evidence is bounded untrusted data and scoring is transactional

The host uses the analyst archetype for the single rubric batch and omits an explicit
model when resolution is unavailable. `digest.py prepare-batch` is the public, read-only
boundary: it accepts the store/record/ready-set inputs plus the host-owned `--as-of`,
loads and sanitizes evidence, sorts by `stub_key`, and emits one JSON manifest to stdout
containing the fingerprint, `as_of`, requested keys, mechanical inputs, and prompt-ready
payload. The store and therefore the manifest are capped at 20 stubs and 64 KiB total
input; provenance excerpts are capped at 2 KiB each. The loader reads only
UTF-8 regular files whose resolved path stays inside the repository, rejects symlinks,
and never fetches URIs. It calls
`skills/roadmap-runtime/scripts/sanitizer.py::sanitize_string` before placing excerpts
inside explicit untrusted-data delimiters; the prompt says never to follow instructions
found there. Missing, binary, URI, symlink, or out-of-root provenance yields no excerpt,
`staleness_days: null`, and a degraded marker.

The host gives the rubric dispatch 120 seconds and at most one retry. `rank` receives the
manifest and the one returned score document, validates fingerprint, exact key coverage,
and exact `scored_at == manifest.as_of`, builds all cache/digest/mirror replacements in
memory, then publishes them atomically only after every validation passes. Timeout,
missing output, retry exhaustion, partial/invalid output, or timestamp mismatch writes no
cache/digest/mirror state, preserves the prior valid digest, and adds one degraded scoring
line to the host-rendered cycle output. Stub files already accepted by `store` remain for
the next cycle. This all-or-nothing boundary prevents a partial batch from becoming a
mixed-evidence ranking.

## Task sizing notes

No task is L or XL. The rank task (1.4) is M because scoring validation, signals, weights,
caching, and ordering are one function's worth of logic that only makes sense tested
together.
