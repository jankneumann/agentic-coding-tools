# supervise Specification

## Purpose
TBD - created by archiving change extend-handoff-document-with-supervisor-record. Update Purpose after archive.
## Requirements
### Requirement: Supervisor Rehydration Record

The `/supervise` skill SHALL rehydrate a fresh session from a supervisor record with four sections — `active_changes`, `pending_gates`, `standing_decisions`, `back_edge` — conforming to `contracts/schemas/supervisor-record.schema.json`. The full record SHALL validate against the canonical `openspec/schemas/supervisor-record.schema.json`, and the mirror SHALL validate against `openspec/schemas/supervisor-record-mirror.schema.json`. The record SHALL be produced by the deterministic host-assisted command `cycle_state.py supervisor-record [--prior PATH] [--repo-root PATH] [--now RFC3339]`, which SHALL derive `active_changes` from `openspec/changes/*/loop-state.json` and `openspec/roadmaps/*/roadmap.yaml` on every run and SHALL carry `pending_gates`, `standing_decisions`, and `back_edge` forward from the prior record. At the end of INTAKE and non-dry-run CYCLE the skill SHALL write the record to the coordinator handoff (`supervisor_record`) and SHALL write the three non-derivable sections to the tracked mirror `openspec/supervise/supervisor-record.json`. On rehydrate the skill SHALL read the most recent handoff via `try_handoff_read(supervisor_only=true)`; when the coordinator is unreachable, or the mirror's `written_at` is newer than the handoff's, it SHALL rehydrate from the mirror plus a fresh derivation and report `Degraded: handoff`.

#### Scenario: Fresh session restores durable state and re-derives active changes
- **GIVEN** repository loop state lists two active changes
- **AND** the newest handoff `supervisor_record` carries one pending gate and one standing decision
- **WHEN** a fresh `/supervise cycle` session rehydrates with no conversation context
- **THEN** its rehydrate output SHALL list both freshly derived changes with their phases, the pending gate with its deadline, and the standing decision
- **AND** its "Needs a decision" section SHALL include the pending gate

#### Scenario: Builder is deterministic
- **WHEN** `cycle_state.py supervisor-record --prior P --now T` runs twice over an unchanged tree with the same T
- **THEN** the two outputs SHALL be byte-identical
- **AND** `active_changes` SHALL be sorted by `change_id`

#### Scenario: Derivable section is recomputed, not carried
- **GIVEN** a prior record whose `active_changes` lists change X at `PLAN`
- **AND** `openspec/changes/X/loop-state.json` now reads `current_phase: IMPLEMENT`
- **WHEN** the builder runs
- **THEN** the output SHALL list X at `IMPLEMENT`
- **AND** a change present in the prior record but no longer under `openspec/changes/` SHALL be absent

#### Scenario: Non-derivable sections are carried forward
- **GIVEN** a prior record with a standing decision and a pending gate
- **WHEN** the builder runs with no new inputs
- **THEN** both SHALL appear unchanged in the output
- **AND** a standing decision whose `expires_at` is in the past SHALL be dropped

#### Scenario: Mirror holds only the non-derivable sections
- **WHEN** the skill writes `openspec/supervise/supervisor-record.json`
- **THEN** the file SHALL contain `schema_version`, `written_at`, `pending_gates`, `standing_decisions`, `back_edge`
- **AND** it SHALL NOT contain `active_changes`
- **AND** the write SHALL pass `cycle_state.py audit-writes`

#### Scenario: Coordinator unreachable falls back to the mirror
- **GIVEN** `try_handoff_read` reports the coordinator unreachable
- **AND** a mirror file exists
- **WHEN** the session rehydrates
- **THEN** the record SHALL be built from the mirror plus a fresh derivation
- **AND** the digest SHALL list `Degraded: handoff`

#### Scenario: Newer mirror wins over a stale handoff
- **GIVEN** a handoff `supervisor_record` written at T1 and a mirror written at T2 > T1
- **WHEN** the session rehydrates
- **THEN** the non-derivable sections SHALL come from the mirror

#### Scenario: Pending gate carries the deadline downstream writers need
- **WHEN** a `pending_gates[]` entry is validated against the record schema
- **THEN** `gate`, `change_id`, `requested_at`, and `deadline` SHALL be required
- **AND** `gate` SHALL be one of the nine `trust_posture.Gate` values, including `roadmap_approval`
- **AND** an entry written by the supervise gate router SHALL carry `decision_id`, `disposition`, and `source: "supervise"`

#### Scenario: Newer ordinary handoff does not mask supervisor state
- **GIVEN** a supervisor handoff followed by a newer ordinary handoff
- **WHEN** `/supervise` rehydrates with `supervisor_only=true`
- **THEN** it SHALL restore the supervisor handoff

#### Scenario: Mirror write preserves unchanged-cycle idempotency
- **GIVEN** a completed cycle has written the mirror and ledger
- **WHEN** the next cycle runs with no other repository or durable-record change
- **THEN** `write_mirror` SHALL be a no-op that preserves `written_at`
- **AND** the cycle fingerprint SHALL be unchanged

#### Scenario: Dry-run writes no supervisor state
- **WHEN** `/supervise cycle --dry-run` completes
- **THEN** neither the mirror nor a supervisor handoff SHALL be written
- **AND** in a non-dry-run cycle the mirror write SHALL occur before the final write audit

#### Scenario: Active-change derivation handles invalid and terminal state
- **GIVEN** change directories in DONE, ESCALATE, malformed, and missing-loop-state conditions
- **WHEN** active changes are derived
- **THEN** DONE, malformed, and missing-state changes SHALL be absent
- **AND** ESCALATE SHALL remain active
- **AND** malformed or ambiguous roadmap/registry inputs SHALL be reported as degraded

### Requirement: Approved Roadmap Execution

The supervise skill SHALL expose an execution path that drives an operator-approved roadmap through the separate delegated prepare/apply entry points and their existing synchronous `dispatch_fn` normalization seam without requiring per-item approval. Roadmap-altitude approval SHALL be a `roadmap_approval` gate decision with outcome `proceed` recorded in the roadmap workspace's `checkpoint.json` `gate_decisions` ledger, and `ExecutionAdapter.prepare` SHALL require a `roadmap_approval_ref` of the form `gate-decision:<decision_id>` that resolves to that record.

#### Scenario: Execute an inherited-approved roadmap
- **WHEN** the operator invokes `/autopilot-roadmap` or approves a roadmap batch from `/supervise`
- **THEN** a `roadmap_approval` gate decision with outcome `proceed` is recorded through the gate router before any dispatch (auto under an `auto` posture, coordinator-approved under `notify_with_timeout`, or console-approved via `cycle_state.py gate-answer`)
- **AND** the supervisor supplies the delegated dispatch callback, the resulting `roadmap_approval_ref`, and exact roadmap item `change_id` values
- **AND** execution continues through ready items without new discovery, direction, or per-item plan questions

#### Scenario: Refuse unapproved roadmap execution
- **WHEN** no `roadmap_approval_ref` is supplied, or the supplied reference does not resolve to a `proceed` decision for that roadmap, or the reference resolves to a `proceed` decision whose stamped `roadmap_fingerprint` no longer matches the roadmap's current DAG shape
- **THEN** `ExecutionAdapter.prepare` raises before writing any attempt and the supervisor does not dispatch an implementation agent
- **AND** it reports the missing approval without mutating roadmap execution state

### Requirement: Background Worktree Isolation

The supervise skill MUST start each delegated Autopilot item as a background sub-agent in a distinct managed worktree and MUST retain only its structured outcome and handoff identifier.

#### Scenario: Run two disjoint changes in parallel
- **WHEN** the delegated batch contains two disjoint changes
- **THEN** the host starts both `/autopilot <change-id>` agents in the background with distinct worktree paths and branches
- **AND** the supervisor context after collection contains both outcomes but no child transcript

#### Scenario: Child dispatch cannot prove isolation
- **WHEN** worktree setup or path/branch verification fails for a selected item
- **THEN** that item returns a failed dispatch outcome before `/autopilot` begins
- **AND** other independently isolated batch members may complete without sharing the failed worktree

#### Scenario: Child parks at a pending gate
- **WHEN** a background Autopilot child reaches a pending gate or policy pause
- **THEN** the host returns a parked result containing the bounded gate or pause snapshot
- **AND** success and parked results include worktree path, branch, and loop-state evidence that exactly match the prepared attempt
- **AND** the supervisor retains the next action without retaining the child transcript or marking the item failed
- **AND** the supervisor resolves the parked gate only through `gate_router.resolve_parked`, which records a gate decision and either resumes the attempt with `approval_ref = gate-decision:<decision_id>` or surfaces the gate in `pending_gates` with its disposition, approval id, and deadline

### Requirement: Router-Neutral Supervisor Dispatch

The supervise skill SHALL pass through router-owned dispatch context and SHALL NOT select or override the vendor, model, location, or cost-policy decision itself.

#### Scenario: Preserve routed context
- **WHEN** the roadmap orchestrator supplies router decision fields in dispatch context
- **THEN** the supervisor forwards those fields unchanged to the background dispatch boundary
- **AND** the recorded result remains correlated to the original dispatch identifier

#### Scenario: Router context is unavailable
- **WHEN** no router decision is present
- **THEN** the supervisor uses the existing archetype/provider resolution path
- **AND** it does not invent a vendor preference or widen the item scope

#### Scenario: Reject unsafe additive context
- **WHEN** dispatch context contains a secret-like or token key, raw response or transcript content, nesting deeper than four levels, or canonical JSON larger than 16 KiB
- **THEN** preparation fails before persistence or dispatch with a bounded deterministic reason
- **AND** valid bounded router-owned fields pass through unchanged

### Requirement: Supervise Gate Routing

The supervise skill SHALL evaluate every gate it raises — `roadmap_approval` at the end of `cycle`, the `execute` precondition, and the resolution of parked `pending_gate` and `policy_pause` attempts — exclusively through `skills/supervise/scripts/gate_router.py`, which SHALL call `shared.approval_gate.ApprovalGate.evaluate` against the supervisor repository root's `TRUST_POSTURE.md`. Whenever the router produces a new decision it SHALL append a `gate-decision.schema.json` record carrying `decision_id`, `source: "supervise"`, `verb`, `roadmap_id`, and any correlating `change_id` / `dispatch_id` to the roadmap workspace's `checkpoint.json` `gate_decisions` ledger before acting on that decision; reusing or re-surfacing a prior record SHALL append nothing. When the workspace has no `checkpoint.json` the router SHALL create one from the roadmap before recording, and `gate-log` SHALL report an absent workspace as empty rather than failing. Records SHALL be built with `shared.approval_gate.build_gate_decision_record` and console answers with `shared.approval_gate.console_decision`; the router SHALL NOT import `autopilot.py`. Before evaluating, the router SHALL apply a prior-record rule to the ledger keyed by the decision's subject (`gate`, `roadmap_id`, and `dispatch_id` for parked attempts or `roadmap_fingerprint` for `roadmap_approval`): a `proceed` record is reused without evaluating; an open `posture_block` record is re-surfaced unchanged unless the posture's disposition for that gate changed; a blocked record carrying an `approval_id` is checked through `ApprovalGate.check_filed` before any new approval is filed; a `rejected` or `console_rejected` record is terminal until the subject changes or a console answer is recorded. `check_filed` SHALL NOT upgrade a prior fail-closed block to `proceed`: it SHALL be called with `notified` sourced from the prior record's own `notified` field (never a literal or a default), and when the coordinator reports `expired` and that `notified` value is `False`, it SHALL return no decision rather than apply a `proceed` default. No other module under `skills/supervise/scripts/` SHALL import or call the approval gate. `cycle_state.py` SHALL expose `gate-check`, `gate-answer`, and `gate-log` subcommands and SHALL import the `Gate` and `Disposition` enums from `shared.trust_posture` rather than duplicating them. `gate-answer` SHALL require a prior parked record for every gate except `roadmap_approval`, whose console answer MAY originate a record; the posture snapshot a console answer records SHALL come from the router's own prior blocked record for that subject, or from the live posture when the answer originates one. The router SHALL project every blocked decision into the tracked mirror's `pending_gates` (keyed by `decision_id`) and every `proceed` decision out of it — upserting the `roadmap_approval` standing decision — through `cycle_state.write_mirror`, merging its change into the currently selected durable state so `back_edge` and unrelated standing decisions survive, and a reused decision SHALL leave the mirror untouched. `cycle_state._clean_pending_gate` SHALL carry `decision_id` through, since it is an allowlist that would otherwise strip the projection key. `gate-check` SHALL NOT run under `cycle --dry-run`, and `execute` SHALL begin with `gate-check`, whose exit-3 record supplies the `roadmap_approval_ref`. `skills/supervise/SKILL.md` SHALL contain no gate whose only enforcement is prose.

#### Scenario: Auto posture takes a conversation to execution without a human touch
- **GIVEN** a `TRUST_POSTURE.md` with `roadmap_approval: auto`
- **WHEN** `cycle_state.py gate-check --roadmap R` runs after the digest
- **THEN** it records a `roadmap_approval` decision with resolution `auto` and exits 3
- **AND** the skill proceeds into `/plan-roadmap` approval and `execute` without asking the operator

#### Scenario: Block posture parks the roadmap approval for a console answer
- **GIVEN** no `TRUST_POSTURE.md` (or `roadmap_approval: block`)
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it records a `posture_block` decision, prints a `pending_gates` entry with `gate: roadmap_approval`, a deadline, and `source: supervise`, and exits 0
- **AND** `gate-answer --roadmap R --gate roadmap_approval --decision approved` records a `console_approved` decision, mirrors it into `standing_decisions`, and prints the `roadmap_approval_ref`

#### Scenario: Notify posture waits for the posture timeout and honours a late answer without re-filing
- **GIVEN** `roadmap_approval: notify_with_timeout` with `timeout_seconds: T` and `default_action: block`, and a reachable coordinator that leaves the approval unanswered
- **WHEN** `gate-check --roadmap R` runs
- **THEN** it files exactly one approval request, waits no longer than T, records a `timeout_default_block` decision carrying the `approval_id`, prints a `pending_gates` entry whose `deadline` is `requested_at + T`, and exits 4
- **AND** when the operator approves that request in the coordinator after the timeout and the next `gate-check --roadmap R` runs, the router calls `ApprovalGate.check_filed(Gate.ROADMAP_APPROVAL, approval_id, notified=False)` — `notified` sourced from the timed-out record's own field, and `False` here because `default_action: block` reached the timeout with no delivery — records an `approved` decision with outcome `proceed`, files no second request, and exits 3
- **AND** when the coordinator still reports the request `pending`, the second run re-surfaces the same entry and deadline and files nothing

#### Scenario: Approved roadmap is not re-asked until its DAG changes
- **GIVEN** a `proceed` `roadmap_approval` record for roadmap R whose `roadmap_fingerprint` matches R's current sorted `(item_id, change_id, depends_on, external_depends_on, status)` tuples, where `status` is normalized so completion-only transitions do not change it
- **WHEN** `gate-check --roadmap R` runs again after an item of R completes
- **THEN** it reuses the existing record, appends nothing to the ledger, prints the reused record, and exits 3
- **AND** when `refine-roadmap` adds, splits, or supersedes an item, or an external dependency edge changes, so the fingerprint changes, the next `gate-check` evaluates `roadmap_approval` anew

#### Scenario: Direct invocation records an originating console decision
- **WHEN** `/autopilot-roadmap` is invoked directly and runs `gate-answer --roadmap R --gate roadmap_approval --decision approved --note "direct invocation"` with no prior parked record
- **THEN** a `console_approved` `roadmap_approval` decision with outcome `proceed` is recorded, its posture snapshot taken from the live posture, and `roadmap_approval_ref` is printed
- **AND** `gate-answer --gate pr_creation` for a dispatch with no parked record is refused without recording anything

#### Scenario: Parked child unparks after a posture flip
- **GIVEN** a `pending_gate` attempt parked on `pr_creation` under `block`
- **WHEN** the operator edits `TRUST_POSTURE.md` to `pr_creation: auto` and the supervisor runs `resolve_parked`
- **THEN** the router records an `auto` decision and calls `ExecutionAdapter.resume` with `approval_ref = gate-decision:<decision_id>`
- **AND** no console answer is required

#### Scenario: Policy pause resolves through escalate_resume
- **WHEN** a `policy_pause` attempt (child in `ESCALATE`) is resolved
- **THEN** the router evaluates `Gate.ESCALATE_RESUME`, not a new gate
- **AND** a `BLOCKED` decision leaves the attempt parked and surfaces `escalate_resume` in `pending_gates`

#### Scenario: Evaluation log covers every supervised gate
- **WHEN** a full simulated run (cycle → execute → parked child → resume) completes and `cycle_state.py gate-log --roadmap R` runs
- **THEN** the output lists one record per `ApprovalGate.evaluate`, `check_filed` decision, or console answer made by the supervisor — and none for a reused or re-surfaced record — plus each item's child `gate_decisions`, each with the posture disposition that was applied and its origin
- **AND** each child's `loop-state.json` SHALL be resolved through the attempt's recorded worktree (`isolation.worktree_path`, or the result's `evidence.loop_state_path`) rather than the supervisor's own `openspec/changes/<change_id>/`, because a child's loop state is untracked and lives only in that child's worktree
- **AND** a child whose loop state cannot be read SHALL be reported as a degraded origin rather than omitted silently
- **AND** every `approval_ref` used during the run resolves to one of those records

#### Scenario: Router is the only seam
- **WHEN** the test scans `skills/supervise/scripts/*.py` by AST
- **THEN** the names `ApprovalGate`, `build_default_gate`, and `check_filed`, and any `.evaluate(...)` call whose receiver is an approval-gate object, appear only in `gate_router.py`
- **AND** `cycle_state.py` MAY call the router's own module-level `evaluate` / `answer` / `resolve_parked` functions, which the scan SHALL NOT treat as a gate-service call site
- **AND** no module under `skills/supervise/scripts/` imports `autopilot`

#### Scenario: Unknown parked gate is a schema error, not a decision
- **WHEN** a parked snapshot names a gate outside `trust_posture.Gate`, or is of kind `pending_gate` with a null `gate` (which the result contract permits)
- **THEN** `resolve_parked` raises without recording a decision or resuming
- **AND** the attempt stays parked

#### Scenario: Router projects gate state into the mirror a fresh session rehydrates
- **GIVEN** no `TRUST_POSTURE.md` and a handoff `supervisor_record` written at T1
- **WHEN** `gate-check --roadmap R` parks `roadmap_approval` at T2 > T1 and a fresh session runs `cycle_state.py rehydrate`
- **THEN** the rehydrated record's `pending_gates` contains the entry with that `decision_id`, `disposition: block`, `source: supervise`, and a deadline, sourced from the mirror
- **AND** the entry's `change_id` is R's first ready item's change, falling back to R's first item carrying a `change_id` when no item is ready, and the gate SHALL be refused with a reported reason rather than parked when R names no change at all
- **AND** the projection preserves the prior record's `back_edge` and every standing decision it did not itself upsert
- **AND** after `gate-answer --roadmap R --gate roadmap_approval --decision approved` the next rehydrate shows no such entry and a standing decision `roadmap_approval:proceed` scoped to R
- **AND** a subsequent `gate-check --roadmap R` that reuses the decision leaves the mirror's `written_at` unchanged

### Requirement: Candidate-Work Digest

The `/supervise` skill SHALL maintain a ranked candidate-work backlog conforming to the stable runtime `digest.schema.json`. Fresh post-dedupe stubs SHALL be merged with retained pending/deferred store files, persisted byte-stably at `openspec/supervise/candidates/<encoded-stub-key>.json`, and represented in `back_edge.digested_stubs`. Keys SHALL be accepted only as `change:<valid-change-id>` or `prov:<hex32>` and SHALL be encoded reversibly before path construction.

A host-dispatched analyst SHALL score one bounded batch against `rubric-score.schema.json`; `scripts/digest.py` SHALL perform no LLM or network call. The surviving store SHALL contain at most 20 candidates; overflow SHALL fail atomically, preserve the post-maintenance store/digest baseline, and name every unpersisted key as degraded output. `digest.py prepare-batch --as-of <RFC3339>` SHALL emit the deterministic prompt manifest to stdout. The batch SHALL contain at most 20 stubs, and its exact serialized stdout prompt manifest—including the ready-set input, stub payloads, mechanical inputs, delimiters, and evidence—SHALL be at most 64 KiB, with each provenance excerpt capped at 2 KiB. A single stub that would exceed the manifest bound SHALL make `prepare-batch` fail before dispatch, preserve the store and prior digest, and emit `oversized:<stub_key>` for degraded output. Provenance content SHALL be treated as untrusted data: only contained UTF-8 regular repo files MAY be read, symlinks and URIs SHALL NOT be followed, excerpts SHALL be redacted by `skills/roadmap-runtime/scripts/sanitizer.py::sanitize_string` and delimited, and unavailable evidence SHALL produce `staleness_days: null` plus a degraded marker.

`digest.py rank` SHALL reject duplicate, missing, or unknown score keys, fingerprint mismatch, and any `scored_at` not exactly equal to the host-owned manifest `as_of`. It SHALL use this total order: pending before future-deferred; dependency-ready before blocked; descending `3*relevance + 3*value + 2*readiness + scope_fit + risk - min(floor(staleness_days/30), 5)` where risk 5 means safest and null staleness has no penalty; then ascending `stub_key`. Dependency readiness SHALL be computed from a strict index of roadmap YAML, active change directories, and `openspec/changes/archive/`: empty or completed prerequisites are ready; an archived change is completed only when its archived `tasks.md` has no unchecked task; pending, blocked, unresolved, and pending-stub prerequisites are not ready. The ready-frontier resolver SHALL NOT be used as this status index. For a safe tracked provenance artifact whose working-tree bytes match `HEAD`, `staleness_days` SHALL use the last Git commit timestamp for that exact repo-relative path; untracked, modified, missing, and unsafe artifacts SHALL use null staleness and degradation, never filesystem mtime. A commit timestamp later than manifest `as_of` SHALL produce null staleness and `clock_skew:<source_artifact>` degradation, never a negative value or score increase. Rejected work SHALL be excluded. Score caches SHALL be schema-valid singleton rubric documents keyed by cycle fingerprint. The cycle fingerprint SHALL exclude the candidate store, rubric caches, `digest.json`, and the transaction journal so supervisor-output-only commits do not invalidate it.

`openspec/supervise/digest.json` SHALL be candidate-work-focused and composable: `new_this_cycle` SHALL contain only freshly stored keys, `needs_decision` SHALL contain retained pending/deferred keys, `degraded` SHALL identify candidate-evidence degradation, and `ranked` SHALL contain the full surviving backlog with all five factor scores and justifications plus mechanical signals. The host SHALL merge these additions into the existing five-section supervisor prose after rendering verified gates (including deadlines), ready work, blockers, and degraded sensors; the candidate artifact SHALL NOT replace those operational lines. `generated_at` SHALL equal the original trusted scoring-manifest `as_of`; `state_updated_at` SHALL equal `generated_at` on a scored run and maintenance `as_of` on a cache-only lifecycle rebuild. Cache/reuse diagnostics SHALL be stdout-only. The host SHALL enforce a 120-second dispatch timeout and at most one retry. Only a wholly valid score document MAY create a crash-recovery journal and publish caches, digest, and mirror updates; the journal SHALL encode ordered replace operations with bytes/checksums and idempotent delete operations.
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
- **WHEN** a rubric document contains a duplicate key, omits a requested key, names an unknown key, misses a factor or justification, or scores outside 1–5
- **THEN** `digest.py rank` SHALL exit non-zero naming the stub and defect
- **AND** no cache or `digest.json` SHALL be written

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
- **WHEN** the analyst times out twice or returns a missing, partial, or invalid score document
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

### Requirement: Digest Approval Routing

Approving a stub into an existing roadmap SHALL use `digest.py stub-to-request <stub_key> --roadmap <roadmap-id> --acceptance <text>... [--after <item-id>]` followed by `refiner.py preview` and, after operator confirmation, `refiner.py apply --expect-base-sha256 <preview-base>`. The request SHALL contain exactly one `op: add`; SHALL map title, description plus provenance, rationale, effort, and suggested change ID; SHALL assign the next free `ri-NN`; SHALL copy the stub's explicit priority and append by default or insert after `--after`, with position independent of priority; and SHALL resolve prerequisites to local `depends_on`, typed `external_depends_on`, or already-satisfied archived dependencies. Unresolved candidate dependencies SHALL fail closed. The item's explicit priority SHALL remain the stub priority; `--after` controls insertion position independently and no renumbering is implied.

`digest.py rank` SHALL synchronize every ranked pending/deferred item into `back_edge.digested_stubs`. `digest.py decide` SHALL merge into the rehydrated supervisor record and persist through `cycle_state.write_mirror`, preserving unrelated newer durable state. The canonical full and mirror schemas SHALL permit `roadmap_ref`, `route`, `until`, and `reason`; approved decisions SHALL require route, `refine-roadmap` approvals SHALL require a roadmap ref, `plan-roadmap` approvals SHALL carry a null roadmap ref, and rejected decisions SHALL require reason. A stub that fits no roadmap SHALL route to `/plan-roadmap --new <slug> "<pitch>" --draft`. No approval path SHALL dispatch an implementer, push, or open a PR.

#### Scenario: Approve a stub into an existing roadmap
- **GIVEN** a pending stub with `suggested_change_id: add-recovery-gate`, a local dependency, a cross-roadmap dependency, and roadmap-x whose highest item is ri-08
- **WHEN** the operator approves it with two acceptance outcomes
- **THEN** `stub-to-request` SHALL emit one add operation for ri-09 with the change ID, both outcomes, provenance, local `depends_on`, and typed `external_depends_on`
- **AND** `refiner.py preview` SHALL report one new item and no errors
- **AND** `refiner.py apply` with that preview's base SHA SHALL add approved ri-09
- **AND** apply with a stale or different SHA SHALL be refused

#### Scenario: Unresolved dependency is refused
- **WHEN** a stub dependency cannot resolve to a local item, cross-roadmap item, or completed archived change
- **THEN** `stub-to-request` SHALL exit non-zero naming the dependency
- **AND** no request or roadmap file SHALL be written

#### Scenario: Approval never bypasses the preview
- **WHEN** the skill approves a stub
- **THEN** `roadmap.yaml` SHALL be modified only by `refiner.py apply` with the base SHA from the immediately preceding preview
- **AND** `skills/supervise/scripts/` SHALL contain no write to any `roadmap.yaml`

#### Scenario: Decisions round-trip without state loss
- **GIVEN** a rehydrated record newer than the mirror and containing unrelated gates, decisions, and digested stubs
- **WHEN** `digest.py decide` records an approved, deferred, or rejected decision
- **THEN** the matching entry SHALL carry the decision-specific metadata allowed by both canonical schemas
- **AND** all unrelated durable fields SHALL survive write and rehydration

#### Scenario: Missing acceptance outcomes are refused
- **WHEN** `stub-to-request` is invoked without `--acceptance`
- **THEN** it SHALL exit non-zero explaining that `refine-roadmap` requires at least one acceptance outcome
- **AND** nothing SHALL be written

#### Scenario: New-roadmap stub falls back to plan-roadmap
- **GIVEN** a stub whose scope fits no active roadmap
- **WHEN** the operator approves it
- **THEN** the skill SHALL invoke `/plan-roadmap --new <slug> "<pitch>" --draft`
- **AND** SHALL record `{decision: approved, route: plan-roadmap, roadmap_ref: null}`

