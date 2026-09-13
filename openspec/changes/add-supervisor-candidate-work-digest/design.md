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
store files, deduplicated by key. Before SENSE and the unchanged-fingerprint gate,
`store --prune-only` removes terminal files and reports `lifecycle_changed` whenever it
prunes a terminal decision or wakes a due deferral. Any lifecycle mutation bypasses the
early exit and rebuilds the digest from cached scores; pruning before SENSE immediately
frees store capacity for a fresh candidate in the same cycle. Under `--dry-run`, the same
maintenance result and rebuilt digest are computed and emitted without persisting any
prune, decision, cache, digest, ledger, journal, or mirror write.

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
manifest time, and `prior_decision`. For a tracked, unmodified provenance artifact,
`staleness_days` subtracts the timestamp of the most recent Git commit that changed that
exact repo-relative path (`git log -1 --format=%cI -- <path>`) from manifest `as_of`.
Untracked, modified, missing, or otherwise unsafe artifacts have null staleness and a
degraded marker; filesystem mtime is never used. If the Git commit timestamp is later than
manifest `as_of`, staleness is also null with `clock_skew:<source_artifact>` degradation,
so negative staleness can neither violate the schema nor increase a score. An empty dependency list is ready; a
dependency is ready only when its referenced item/change is completed or
archived-completed; pending, blocked, unresolved, and pending-stub dependencies are not
ready. The index walks strict roadmap YAML plus active change directories and treats a
change as archived-completed only when it exists below `openspec/changes/archive/` and
its archived `tasks.md` has no unchecked task. Risk is
inverted: 5 means safest. The fixed score is `3*relevance + 3*value + 2*readiness +
scope_fit + risk - min(floor(staleness_days / 30), 5)`; null staleness has no penalty
and is marked degraded. The total order is: pending before future-deferred,
dependency-ready before blocked, descending score, then ascending `stub_key`.
Rejected stubs are excluded. `weights` emits the five numeric weights, the per-30-day
penalty and cap, `risk_higher_is_safer`, both bucket orders, and the ascending `stub_key`
tie-breaker, so a reader can reconstruct every rank and tied inputs always have one answer.

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
store admits at most 20 surviving candidates; after pre-SENSE maintenance has committed
any lifecycle rebuild, a would-be 21st candidate makes `store` fail atomically, leaves that
maintained store/digest baseline untouched, and returns a degraded overflow record naming
every unpersisted key so the host can carry those upstream inputs into the next cycle. This
deliberately chooses a hard, visible capacity bound over unbounded model cost. On a scored
rank, `generated_at` and `state_updated_at` both equal manifest `as_of`. A cache-only
lifecycle rebuild preserves the cached scoring time in `generated_at` and sets
`state_updated_at` to maintenance `as_of`; persisted output contains no reuse/cache flags.

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
The next CYCLE's pre-SENSE, pre-fingerprint `store --prune-only` removes
approved/rejected files and caches. Deferred files remain; when `until` is due, maintenance
changes the decision to pending. Terminal pruning and due waking both request a cache-only
re-rank, bypass the unchanged exit, and publish the maintained baseline before fresh store
admission. The ranker validates each reused cache against its original scoring manifest:
its `scored_at` must match the preserved `generated_at`, while maintenance `as_of` is used
only for lifecycle decisions and the new `state_updated_at`; no scorer is dispatched.

**Why prune next cycle, not immediately.** `decide` may run several times in one
conversation; preflight pruning keeps cleanup inside the next audited CYCLE and, unlike
the old post-SENSE placement, still runs on an otherwise unchanged tree.

## D6 — Digest artifact and the unchanged-fingerprint path

`digest.json` is deliberately candidate-work-focused:
`{schema_version, fingerprint, generated_at, state_updated_at, weights, sections:
{needs_decision[], new_this_cycle[], degraded[]}, ranked:[...]}`. `new_this_cycle` contains
only keys freshly stored in this cycle; retained pending/deferred keys go under
`needs_decision`; `ranked` contains the full retained-plus-fresh backlog. The host merges
these three candidate additions into the existing five-section digest after it has
rendered pending gates (including deadlines), ready work, blockers, and degraded sensors.
The candidate artifact cannot erase or replace those operational lines.

`generated_at` is the original host-owned scoring-manifest `as_of`, not model or render
time; `state_updated_at` is that same value on a scored run and the host-owned maintenance
`as_of` on a cache-only lifecycle rebuild. `cached_scores` and `reused_prior` are stdout
diagnostics, not persisted fields. When `cycle_state.py fingerprint` reports unchanged
and maintenance reports no lifecycle mutation, the skill schema-validates and re-presents
the prior bytes. Terminal pruning or a due deferral is the explicit exception: maintenance
updates the backlog using its host-owned `--as-of`, then rebuilds from caches whose
`scored_at` is validated against the preserved `generated_at`, without dispatching a
scorer. `--force` bypasses the SENSE early exit but does not invalidate same-fingerprint
rubric caches: it dispatches only for missing scores or a changed requested-key set and
otherwise reuses validated bytes unless candidate composition changed.

## D7 — Sequencing

- ri-05's `back_edge` slot/mirror and ri-16's cross-roadmap reference validation are on
  main. This change extends the stable record contracts. It does not use ri-16's
  ready-frontier result as a status index: ranking and routing build their own strict
  all-status index because completed, blocked, pending, and nonexistent dependencies must
  remain distinguishable.
- ri-12 (generators emit stubs) is the real producer; fixtures stand in until then.
- `TestWorkflowContract` string assertions move with the reworded CYCLE sections.

## D8 — Evidence is bounded untrusted data and scoring is transactional

The host uses the analyst archetype for the single rubric batch and omits an explicit
model when resolution is unavailable. `digest.py prepare-batch` is the public, read-only
boundary: it accepts the persisted store plus optional validated dry-run stubs,
record, and ready-set inputs plus the host-owned `--as-of`,
loads and sanitizes evidence, sorts by `stub_key`, and emits one JSON manifest to stdout
containing the fingerprint, `as_of`, requested keys, bounded ready set, mechanical inputs,
and prompt-ready payload. The ready set is embedded inside that manifest rather than injected
as a second unbounded template payload. The store is capped at 20 stubs, and the exact serialized stdout prompt manifest—including stub payloads, mechanical inputs, delimiters, and evidence—is capped
at 64 KiB; provenance excerpts are capped at 2 KiB each. If one stub alone would exceed
the 64-KiB manifest bound, `prepare-batch` fails before dispatch, preserves the store and
prior digest, and emits `oversized:<stub_key>` for host degradation and later correction.
The loader reads only
UTF-8 regular files whose resolved path stays inside the repository, rejects symlinks,
and never fetches URIs. It calls
`skills/roadmap-runtime/scripts/sanitizer.py::sanitize_string` before placing excerpts
inside explicit untrusted-data delimiters; the prompt says never to follow instructions
found there. Missing, binary, URI, symlink, or out-of-root provenance yields no excerpt,
`staleness_days: null`, and a degraded marker.

The host gives the rubric dispatch 120 seconds and at most one retry. `rank` receives the
manifest and the one returned score document, validates fingerprint, exact key coverage,
and exact `scored_at == manifest.as_of`, then builds every cache/digest/mirror replacement
in memory. Publication uses `openspec/supervise/.digest-transaction.json`. Its ordered operations
encode either `{op: replace, target, bytes, sha256}` or `{op: delete, target}`. A scored
transaction includes cache, mirror, and digest replacements; a lifecycle transaction also
includes every terminal stub/cache deletion plus the rebuilt mirror and digest. Recovery accepts only canonical candidate/cache paths plus the digest and supervisor mirror,
validates the complete bounded journal before mutation, and refuses all other targets. The journal
is atomically written and fsynced before any target mutation. Recovery idempotently applies
sorted non-digest deletes/replacements, verifies replaced bytes by checksum, fsyncs every
affected parent directory, then replaces and fsyncs `digest.json` last as the commit marker.
It removes the journal only after all targets are durable and fsyncs the journal's parent.
Every non-dry-run mutating digest CLI entry point recovers first. Read-only and dry-run
commands report pending recovery and refuse to serve a candidate digest from mixed state
without mutating it. The journal is excluded from the cycle fingerprint.
Timeout, missing output, retry exhaustion, partial/invalid output, timestamp mismatch, or
oversized prompt writes no journal and no cache/digest/mirror state, preserves the prior
valid digest, and does not advance the cycle ledger's last successful fingerprint, so the
next cycle retries. Stub files already accepted by `store` remain. This recoverable
all-or-nothing protocol prevents partial batches and interrupted replacement sequences
from becoming a durable mixed-evidence ranking.

## Task sizing notes

No task is L or XL. The rank task (1.4) is M because scoring validation, signals, weights,
caching, and ordering are one function's worth of logic that only makes sense tested
together.
