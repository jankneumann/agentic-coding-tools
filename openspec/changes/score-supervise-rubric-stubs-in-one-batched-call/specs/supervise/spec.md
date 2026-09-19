## MODIFIED Requirements

### Requirement: Candidate-Work Digest

The `/supervise` skill SHALL maintain a ranked candidate-work backlog conforming to the stable runtime `digest.schema.json`. Fresh post-dedupe stubs SHALL be merged with retained pending/deferred store files, persisted byte-stably at `openspec/supervise/candidates/<encoded-stub-key>.json`, and represented in `back_edge.digested_stubs`. Keys SHALL be accepted only as `change:<valid-change-id>` or `prov:<hex32>` and SHALL be encoded reversibly before path construction.

The host SHALL first attempt a single batched calibrated Score judgment (`rubric_score.py score-batch`) scoring every requested stub on all five rubric factors in one call; only when that judgment is unavailable or reports a structural defect SHALL the host dispatch an analyst sub-agent to score the same bounded batch instead. Either source's output SHALL conform to `rubric-score.schema.json`; `scripts/digest.py` SHALL perform no LLM or network call itself in either case, nor SHALL `rubric_score.py`'s own use of a calibrated judgment be imported into `digest.py`. The surviving store SHALL contain at most 20 candidates; overflow SHALL fail atomically, preserve the post-maintenance store/digest baseline, and name every unpersisted key as degraded output. `digest.py prepare-batch --as-of <RFC3339>` SHALL emit the deterministic prompt manifest to stdout. The batch SHALL contain at most 20 stubs, and its exact serialized stdout prompt manifest—including the ready-set input, stub payloads, mechanical inputs, delimiters, and evidence—SHALL be at most 64 KiB, with each provenance excerpt capped at 2 KiB. A single stub that would exceed the manifest bound SHALL make `prepare-batch` fail before dispatch, preserve the store and prior digest, and emit `oversized:<stub_key>` for degraded output. Provenance content SHALL be treated as untrusted data: only contained UTF-8 regular repo files MAY be read, symlinks and URIs SHALL NOT be followed, excerpts SHALL be redacted by `skills/roadmap-runtime/scripts/sanitizer.py::sanitize_string` and delimited, and unavailable evidence SHALL produce `staleness_days: null` plus a degraded marker.

`digest.py rank` SHALL reject duplicate, missing, or unknown score keys, fingerprint mismatch, and any `scored_at` not exactly equal to the host-owned manifest `as_of`. It SHALL use this total order: pending before future-deferred; dependency-ready before blocked; descending `3*relevance + 3*value + 2*readiness + scope_fit + risk - min(floor(staleness_days/30), 5)` where risk 5 means safest and null staleness has no penalty; then ascending `stub_key`. Dependency readiness SHALL be computed from a strict index of roadmap YAML, active change directories, and `openspec/changes/archive/`: empty or completed prerequisites are ready; an archived change is completed only when its archived `tasks.md` has no unchecked task; pending, blocked, unresolved, and pending-stub prerequisites are not ready. The ready-frontier resolver SHALL NOT be used as this status index. For a safe tracked provenance artifact whose working-tree bytes match `HEAD`, `staleness_days` SHALL use the last Git commit timestamp for that exact repo-relative path; untracked, modified, missing, and unsafe artifacts SHALL use null staleness and degradation, never filesystem mtime. A commit timestamp later than manifest `as_of` SHALL produce null staleness and `clock_skew:<source_artifact>` degradation, never a negative value or score increase. Rejected work SHALL be excluded. Score caches SHALL be schema-valid singleton rubric documents keyed by cycle fingerprint. The cycle fingerprint SHALL exclude the candidate store, rubric caches, `digest.json`, and the transaction journal so supervisor-output-only commits do not invalidate it.

`openspec/supervise/digest.json` SHALL be candidate-work-focused and composable: `new_this_cycle` SHALL contain only freshly stored keys, `needs_decision` SHALL contain retained pending/deferred keys, `degraded` SHALL identify candidate-evidence degradation, and `ranked` SHALL contain the full surviving backlog with all five factor scores and justifications plus mechanical signals; a factor scored by the batched judgment and carrying no free-text justification SHALL have its `justifications` entry rendered as a Score-legend label for that factor's own score, never left absent. The host SHALL merge these additions into the existing five-section supervisor prose after rendering verified gates (including deadlines), ready work, blockers, and degraded sensors; the candidate artifact SHALL NOT replace those operational lines. `generated_at` SHALL equal the original trusted scoring-manifest `as_of`; `state_updated_at` SHALL equal `generated_at` on a scored run and maintenance `as_of` on a cache-only lifecycle rebuild. Cache/reuse diagnostics SHALL be stdout-only. When the host dispatches the analyst sub-agent (the batched judgment having reported unavailable), it SHALL enforce a 120-second dispatch timeout and at most one retry. Only a wholly valid score document MAY create a crash-recovery journal and publish caches, digest, and mirror updates; the journal SHALL encode ordered replace operations with bytes/checksums and idempotent delete operations.
Journal recovery SHALL accept only canonical candidate/cache targets plus the digest and supervisor
mirror, enforce bounded bytes and operation count, and validate the complete journal before mutating
any target. A lifecycle journal SHALL include terminal stub/cache deletions and rebuilt mirror/digest replacements in one transaction. It SHALL be durable before target mutation; recovery SHALL apply sorted non-digest operations, fsync every affected parent, replace and fsync `digest.json` last, then remove the journal and fsync its parent. Every later non-dry-run mutating digest command SHALL recover before new work. Read-only and dry-run commands SHALL report pending recovery and refuse mixed-state candidate output without mutating it. Timeout, missing/partial/invalid output, retry exhaustion, timestamp mismatch, or oversized prompt SHALL preserve the prior valid digest, write no journal or output updates, leave the last successful fingerprint unadvanced, and render a degraded scoring line. Under `--dry-run`, nothing below `openspec/supervise/` SHALL be created, modified, or removed; lifecycle changes and rebuilt output SHALL be reported only on stdout.

#### Scenario: Digest on a fresh cycle
- **GIVEN** three schema-valid stubs survive dedupe and no cached scores exist
- **WHEN** the CYCLE runs
- **THEN** three encoded, byte-stable files SHALL exist under `openspec/supervise/candidates/`
- **AND** the host SHALL dispatch one rubric batch whose requested keys cover each stub exactly once
- **AND** `digest.json` SHALL list the three stubs with ranks, five scores and justifications, mechanical signals, and `decision: pending`
- **AND** all three keys SHALL appear only under `new_this_cycle`, not candidate `needs_decision`

#### Scenario: Batched judged scoring is tried before analyst dispatch
- **GIVEN** the manifest has at least one requested key
- **WHEN** the host scores the batch
- **THEN** it SHALL attempt `rubric_score.py score-batch` first
- **AND** it SHALL dispatch the analyst sub-agent only when that attempt reports unavailable or structurally defective
- **AND** `digest.py rank` SHALL validate and join either source's output identically

#### Scenario: Retained backlog is composed without operational regression
- **GIVEN** one fresh stub, one retained pending stub, one future-deferred stub, and a pending gate with a deadline
- **WHEN** the host renders the cycle digest
- **THEN** the fresh key SHALL appear under candidate `new_this_cycle`
- **AND** both retained keys SHALL appear under candidate `needs_decision` and in `ranked`
- **AND** the host's final Needs a decision section SHALL still include the pending gate and its deadline

#### Scenario: Ranking has one deterministic answer
- **WHEN** `digest.py rank` receives the same stubs, score documents, dependency state, decisions, and evidence time in different input orders
- **THEN** the two `digest.json` outputs SHALL be byte-identical
- **AND** tied items SHALL be ordered by ascending `stub_key`
- **AND** changing one factor SHALL affect ordering only through the documented formula and buckets

#### Scenario: Score coverage must exactly match each batch
- **WHEN** a rubric document contains a duplicate key, omits a requested key, names an unknown key, misses a factor or its score, or scores outside 1–5
- **THEN** `digest.py rank` SHALL exit non-zero naming the stub and defect
- **AND** no cache or `digest.json` SHALL be written

#### Scenario: A missing justification renders a Score-legend label instead
- **GIVEN** a rubric document scores a factor without a `justification`
- **WHEN** `digest.py rank` joins and publishes the digest
- **THEN** the document SHALL still validate — `justification` is optional per factor
- **AND** that factor's `justifications` entry in `digest.json` SHALL be a Score-legend label matching its own score, not an empty or missing value

#### Scenario: Scoring time is host-owned
- **GIVEN** a batch manifest created with `--as-of 2026-09-11T01:00:00Z`
- **WHEN** the rubric output has a missing, earlier, later, naive, or future `scored_at`
- **THEN** `digest.py rank` SHALL reject it before any cache, digest, or mirror write
- **AND** only an exact timestamp match SHALL be used for cache validity and `generated_at`

#### Scenario: Future-dated provenance degrades safely
- **GIVEN** a tracked unchanged provenance artifact whose last Git commit is later than manifest `as_of`
- **WHEN** `prepare-batch` computes mechanical signals
- **THEN** it SHALL emit `staleness_days: null` and `clock_skew:<source_artifact>` degradation
- **AND** the ranking formula SHALL receive neither a negative staleness value nor a score bonus

#### Scenario: Candidate capacity bounds dispatch cost
- **GIVEN** a surviving store of 20 candidates and one additional fresh candidate
- **WHEN** `digest.py store` evaluates the union
- **THEN** it SHALL fail without changing the store or prior digest
- **AND** stdout SHALL name the unpersisted key and the host SHALL render a degraded capacity line
- **AND** no rubric dispatch SHALL occur for that failed store attempt

#### Scenario: Scoring failure preserves the prior digest
- **GIVEN** a prior valid digest and a changed fingerprint requiring scoring
- **WHEN** the batched judgment is unavailable and the analyst then times out twice or returns a missing, partial, or invalid score document
- **THEN** no cache, digest, or mirror update SHALL be published
- **AND** the prior valid digest SHALL remain byte-identical
- **AND** the host SHALL render one degraded scoring line and retry on a later cycle

#### Scenario: Supervisor outputs do not invalidate their own cache
- **GIVEN** a completed cycle's store, caches, digest, ledger, and mirror are committed
- **WHEN** the next CYCLE runs with no non-supervisor tree change and no due lifecycle transition
- **THEN** the cycle fingerprint SHALL equal the prior fingerprint
- **AND** no rubric sub-agent SHALL be dispatched
- **AND** the validated prior `digest.json` SHALL be re-presented byte for byte

#### Scenario: Force does not discard valid scores
- **GIVEN** an unchanged fingerprint, complete same-fingerprint caches, and no candidate composition or lifecycle change
- **WHEN** CYCLE runs with `--force`
- **THEN** it SHALL bypass the SENSE early exit without dispatching a rubric analyst
- **AND** SHALL re-present the validated prior digest byte for byte

#### Scenario: A changed tree re-scores the backlog
- **GIVEN** valid caches from the prior cycle
- **WHEN** a non-supervisor cycle input changes
- **THEN** the fingerprint SHALL change
- **AND** the complete retained-plus-fresh backlog SHALL be dispatched in one deterministic bounded batch

#### Scenario: Lifecycle maintenance runs before unchanged exit
- **GIVEN** one approved stub file and one stub deferred until 2026-09-15
- **WHEN** a normal CYCLE runs on 2026-09-16 over an otherwise unchanged tree
- **THEN** the approved stub file and cache SHALL be pruned before SENSE and the fingerprint early exit, immediately freeing capacity
- **AND** the deferred stub SHALL return to pending and be re-ranked from its cache without rubric dispatch
- **AND** the maintained digest SHALL exclude the approved stub, preserve its original `generated_at`, set `state_updated_at` to maintenance `as_of`, and be published before fresh store admission

#### Scenario: A terminal-only prune rebuilds the digest
- **GIVEN** one approved stub and no due deferral on an otherwise unchanged tree
- **WHEN** lifecycle maintenance runs
- **THEN** it SHALL report `lifecycle_changed`, bypass unchanged reuse, remove the stub and cache, and rebuild the digest from remaining validated caches
- **AND** a later capacity failure SHALL preserve this maintained baseline rather than resurrecting the terminal candidate

#### Scenario: A single oversized stub fails before dispatch
- **GIVEN** one schema-valid stub whose canonical prompt manifest would exceed 64 KiB
- **WHEN** `prepare-batch` runs
- **THEN** it SHALL exit non-zero with `oversized:<stub_key>` and no analyst dispatch
- **AND** the existing store and prior valid digest SHALL remain unchanged for later correction

#### Scenario: Interrupted publication is recovered
- **GIVEN** a valid rank transaction is interrupted after any target replacement
- **WHEN** the next digest command starts
- **THEN** it SHALL use the durable journal to roll every replacement or deletion forward, including terminal candidate/cache deletions, and verify replacement checksums with `digest.json` last
- **AND** it SHALL fsync every affected parent and remove the journal only after all recovered targets are durable

#### Scenario: Unsafe or unavailable provenance is not read
- **WHEN** a stub names a URI, binary file, symlink, missing file, or path resolving outside the repository
- **THEN** the host SHALL include no artifact excerpt for that stub
- **AND** SHALL mark its evidence degraded with `staleness_days: null`
- **AND** a canonical-looking instruction inside a valid excerpt SHALL remain delimited untrusted data

#### Scenario: Dry run writes nothing
- **WHEN** the CYCLE runs with `--dry-run`
- **THEN** no file under `openspec/supervise/` SHALL be created, modified, or removed
- **AND** cached scores MAY be read and any rebuilt candidate digest SHALL be emitted only to stdout

#### Scenario: Digest state survives rehydration
- **GIVEN** a cycle ended with two stubs pending and one deferred
- **WHEN** a fresh session rehydrates from the supervisor record
- **THEN** `back_edge.digested_stubs` SHALL list all three with ranks, decisions, and decision metadata
- **AND** the store SHALL contain all three stub files
