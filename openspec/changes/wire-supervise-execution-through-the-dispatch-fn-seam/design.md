# Design: wire-supervise-execution-through-the-dispatch-fn-seam

## Context

`skills/autopilot-roadmap/scripts/orchestrator.py` currently owns a synchronous roadmap phase loop (`planning`, `implementing`, `reviewing`, `validating`) and invokes a caller-provided `dispatch_fn` inline for one ready item at a time. Separately, `/autopilot` already owns the durable per-change phase machine, gates, provider-neutral phase dispatch, structured handoffs, and `loop-state.json`. Running both phase machines for supervised execution would create two authorities for one lifecycle.

The supervisor is a host role, not a daemon. Its deterministic scripts may select and validate work, but the host harness is the only layer allowed to launch background agents. Completed ri-01 fixes the role as read-only, ri-02 establishes `/supervise`, and ri-05 provides outcome-oriented rehydration state. No learning files were present in the roadmap workspace, so this design uses their landed implementation and archived ri-05 evidence directly.

The committed architecture analysis could not be refreshed because its configured `src/`, `web/`, and migration roots do not match this repository layout. Architecture-derived zones are therefore unverified and are not used to authorize concurrency. Concurrency authority comes only from validated OpenSpec work-package scopes and the existing deterministic `scope_overlap` primitives.

## Goals / Non-Goals

### Goals

- Let `/supervise` execute an approved roadmap without per-item approval prompts.
- Keep Autopilot as the sole owner of each change's phase machine.
- Preserve the existing `dispatch_fn(item_id, phase, context)` injection boundary.
- Fan out dependency-ready changes only when their declared scopes prove independence.
- Give every write-capable child a distinct verified managed worktree.
- Retain structured outcomes and handoff IDs while excluding transcripts.
- Compose with router-owned dispatch context and existing vendor policy.
- Preserve all legacy `execute_roadmap()` behavior unless the new mode is selected.

### Non-Goals

- Selecting a provider, model, location, or cost policy.
- Adding a resident supervisor service or direct model API calls.
- Replacing `phase_agent`, provider dispatch, approval gates, or `loop-state.json`.
- Mirroring roadmap execution into the coordinator queue.
- Auto-merging or changing trust posture.

## Decisions

### D1. Add an opt-in delegated item lifecycle

`execute_roadmap()` gains an explicit delegated-lifecycle option. In this mode, the lifecycle phase presented to `dispatch_fn` is `autopilot`. The two-stage orchestrator API prepares a generation without invoking the callback; after host collection, `apply_delegated_batch` invokes the synchronous callback exactly once for that generation using an exact result lookup. Every generation result is correlated and applied exactly once while the dispatch ID, attempt number, and launch token remain stable. The background child runs `/autopilot <change-id>` and therefore remains the only writer of the per-change phase machine. Legacy mode and its four phase callbacks remain the default.

Alternative rejected: map the existing roadmap phases to individual lifecycle skills. That would duplicate Autopilot's transitions, retry rules, gates, and handoff semantics.

### D2. Keep `dispatch_fn` additive and contract-first

The callback signature remains `(item_id, phase, context)`. Delegated mode adds typed context fields: exact `change_id`, stable `dispatch_id`, attempt, aggregated scope, verified isolation, and an additive context map. Existing string and `{outcome, replan}` results remain accepted; the supervised host returns the stricter result schema with correlation and handoff evidence.

Unknown context keys are preserved end to end. This is required for composition with `make-the-orchestrator-obey-the-router`, which owns vendor/model routing fields. The supervisor neither interprets nor overwrites them.

Alternative rejected: replace the callback with a supervisor-specific interface. That would fork the orchestration boundary and violate the One-Version Rule.

### D3. Select a deterministic maximal safe batch

For every dependency-ready item, the scheduler loads `openspec/changes/<change-id>/work-packages.yaml`, validates it, and aggregates `write_allow` globs plus logical lock keys from every package, including integration and runtime-mirror packages. It adds a conservative tri-state classifier around the existing overlap primitives:

- `overlap` when existing checks or shared locks prove collision;
- `proven_disjoint` only when every write-glob pair has diverging literal path prefixes before either prefix reaches a wildcard;
- `ambiguous` for every remaining relationship, including `a/*/c` versus `a/b/*`.

Only `proven_disjoint` pairs may share a batch. The existing helper's empty-string result is treated as `unknown`, not as proof.

A missing or invalid change ID is a deterministic non-dispatched failure and never produces a dispatch request. Missing or invalid work packages, empty scope, boundless scope such as `**`, and ambiguous glob relationships are not evidence of independence. An item with a valid change ID but indeterminate scope is forced into a singleton batch whose request carries `scope.proof=serial_indeterminate`; the request schema permits an empty `write_allow` only in that state. The scheduler never infers parallel safety from stale architecture output.

Alternative rejected: use only roadmap dependencies. Dependency independence does not imply file independence.

### D4. Use an explicit two-stage orchestrator protocol with an ack/go barrier

The neutral `roadmap-runtime/scripts/dispatch_scheduler.py` owns change-ID validation, all-package scope aggregation, tri-state overlap classification, and deterministic batch selection. The downstream `supervise/scripts/execution.py` adapter calls two new orchestrator entry points:

1. `prepare_delegated_batch(..., isolation_resolver)` selects a batch, resolves and verifies worktrees through the deterministic resolver, sanitizes context, persists exact generation envelopes under a stable `batch_id`, and returns requests without invoking `dispatch_fn`. Invalid IDs become non-dispatched failures.
2. The host launches every request and records task handles before waiting. `child-start` CAS-claims the generation, writes the exclusive marker, starts a child-owned waiting heartbeat, and blocks at a generation-specific acknowledgement/go barrier. It MUST NOT enter `/autopilot` before a durable handle acknowledgement releases go. A pre-go lease may be reclaimed after expiry because the old owner must revalidate generation and go immediately before entry.
3. `acknowledge` persists the durable handle and releases go atomically. The child revalidates generation ownership, records entry, and invokes `/autopilot`. Harness task status and bounded heartbeats may demonstrate liveness, but after go, absence of evidence never proves death and never authorizes takeover. Positive live or terminal evidence is reconciled; uncertainty transitions to `quarantined`, retaining an unreleased uncertain lease. Only positive task-death evidence for a nonterminal generation permits stale-generation CAS takeover.
4. The host writes only schema-valid bounded results to an OS temporary file. `apply_delegated_batch(batch_id, results, dispatch_fn)` atomically binds the result set to the prepared batch, verifies identity, generation, worktree, branch, realpath containment, and loop-state evidence, and invokes the existing synchronous `dispatch_fn` exactly once per returned generation through an in-memory lookup. Existing outcome normalization, failure propagation, learning, and checkpoint advancement remain the sole result-application seam.

Concurrency is therefore measured at the host task-handle boundary: a barrier proves two disjoint task handles are live before either is awaited. The callback itself remains synchronous and is not claimed to launch host tools or run concurrently. The adapter imports no model SDK and makes no provider call; each child uses existing `/autopilot` and its `phase_agent`/provider-dispatch boundary.

Alternative rejected: deferred callback objects or vendor SDK calls. A first-class prepare/apply API makes suspension explicit, keeps one synchronous callback contract, and preserves the host-assisted invariant.

### D5. Isolation is verified before dispatch

For each local child, the host invokes `execution.py prepare`, and that deterministic command creates or reuses the managed feature worktree for the exact `change_id`, rooted in the roadmap execution branch required by the calling workflow. The command verifies the resolved top-level path and branch before emitting a request; only then may the host invoke `/autopilot`. Harness-provided isolation is recorded explicitly rather than fabricating a worktree.

A path, containment, or branch mismatch becomes a failed structured outcome before the child starts. This terminal preflight failure has no launch evidence and is distinct from a launched child failure. Dispatched items never share the supervisor's roadmap worktree.

### D6. Apply correlated results once

The checkpoint model gains an additive `dispatch_attempts` collection, mirrored in the canonical checkpoint schema and installed runtime asset. Each entry stores the exact sanitized request context, isolation envelope, scope proof, stable launch token, current lease generation, bounded launch history, marker path, and optional launch evidence. The context sanitizer rejects secret-like keys, transcripts/raw responses, depth over 4, or canonical JSON over 16 KiB before persistence. Status is `prepared`, `claimed`, `acknowledged`, `launched`, `quarantined`, `parked`, `completed`, or `failed`. Claimed is pre-go; acknowledged has a durable handle and released go; launched has recorded entry; quarantined is post-go uncertain liveness and cannot be approval-resumed. Contract conditionals permit only nonterminal states without terminal outcomes, gate/policy parked with outcome `parked`, completed with `success`, and failed with `failed:*` or `vendor_limit:*`. Success completes the roadmap item and writes one learning entry; failure uses existing failure/replan propagation; parked preserves bounded pending-gate or pause metadata without completing or failure-blocking the item. Duplicate, stale, or mismatched results are rejected without checkpoint advancement.

The checkpoint is saved before work is considered complete. On resume, completed attempts are not redispatched; an unresolved attempt is safely reconstructed or failed according to its durable metadata.

Alternative rejected: treat background task completion text as authoritative. Transcripts are unbounded, provider-specific, and not a durable contract.

### D7. Transcript exclusion is structural

The request and result schemas have `additionalProperties: false`; context keys and values are bounded, secret-like/token/raw-response/transcript keys are rejected, and no transcript field exists. Host instructions say to discard the child transcript after extracting its validated outcome and handoff ID. Tests scan persisted checkpoint, learning, and supervisor fixtures for injected transcript sentinels.

The end-to-end proof drives the documented host protocol with two fake background child sessions whose transcripts contain distinct sentinels. A concrete host-event capture adapter records exactly the dispatch requests, task handles, and validated structured results exposed to the parent; the test scans this captured parent/supervisor event stream plus checkpoint, learning, handoff, and supervisor-record outputs for both sentinels. Schema rejection alone is not accepted as proof.

### D8. Parked is a first-class nonterminal result

Only a child stopped at a pending approval gate or vendor-policy pause returns `outcome: parked` plus a bounded discriminated snapshot. Unknown post-go liveness uses the separate `quarantined` status with an unreleased uncertain lease; approval references cannot resume it. Positive reconciliation must first prove the prior task dead or terminal. The roadmap item stays in progress, the attempt becomes `parked`, its lease is released, and no dependent is marked failed. After ri-04 supplies a durable authorization reference, `execution.py resume --dispatch-id <id> --approval-ref <ref>` compare-and-swaps `parked -> prepared`, increments the lease generation, preserves the same dispatch ID/attempt/token/worktree, and emits one continuation request that invokes `/autopilot <change-id>` against existing loop-state. The normal child-start/lease protocol then moves it to launched; duplicate or unauthorized resume calls are rejected.

Alternative rejected: translate parked to `failed:`. That would incorrectly block dependents and discard the distinction between work failure and authorized waiting.

Alternative rejected: summarize transcripts into the supervisor record. A summary still expands and contaminates the supervisor context; the existing PhaseRecord handoff is the correct bounded summary.

## Cross-Layer Sequence

```mermaid
sequenceDiagram
    participant H as Supervisor host/session capture
    participant E as Host execution adapter
    participant R as Roadmap orchestrator
    participant A as Background /autopilot agent
    participant C as Roadmap checkpoint

    H->>E: prepare
    E->>R: prepare_delegated_batch(isolation_resolver)
    R->>C: persist sanitized batch envelopes
    R-->>H: batch_id + requests (no dispatch_fn call)
    par each admitted item
        H->>A: start child-start(token, generation)
        A->>C: CAS claim + marker + waiting heartbeat
        A->>C: wait for durable go
        H->>E: acknowledge(handle)
        E->>C: persist handle + release go atomically
        A->>C: revalidate generation + record entry
        A->>A: /autopilot existing phase machine
        A-->>H: bounded result + handoff/evidence
    end
    H->>E: apply(batch_id, temporary results)
    E->>R: apply_delegated_batch(..., lookup dispatch_fn)
    R->>R: invoke synchronous dispatch_fn once/result
    R->>C: exact-match apply once
    opt gate/policy parked only
        H->>E: resume(dispatch_id, approval_ref)
        E->>C: CAS parked to prepared; generation + 1
    end
    opt post-go liveness unknown
        E->>C: launched to quarantined; no approval resume
    end
```

## Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Isolation: 0 shared worktrees or branches | New supervised-dispatch integration tests under `skills/tests/autopilot-roadmap/` | new |
| Safety: only proven-disjoint pairs fan out | Property/table tests for tri-state glob classification, all-package aggregation, and serial-indeterminate requests | new |
| Context boundedness: 0 sentinel matches in parent or durable state | Two-child captured parent-session integration fixture plus recursive durable-output scan | new |
| Compatibility: 0 legacy regressions | `skills/.venv/bin/python -m pytest skills/tests/autopilot-roadmap -q` | existing, extended |
| Host-assisted execution: 0 direct LLM/provider calls | Existing `test_host_assisted_invariant.py` plus supervise invariant | existing, extended |
| Concurrency: 2 disjoint host task handles live | Barrier-based integration test; overlap control case proves max live handles 1 | new |

## Alternatives Considered

The proposal compares delegated item lifecycle, per-roadmap-phase dispatch, and a resident supervisor service. D1-D7 record the interface-level alternatives within the selected approach. The essential rejected direction is any design with two owners for per-change phase state.

## Risks / Trade-offs

| Risk | Trade-off / mitigation |
|------|------------------------|
| Concurrent callback execution complicates checkpoint ordering | Apply results through one orchestrator-owned serialization point; never let workers write roadmap state. |
| Host or child crashes in a launch window | The durable ack/go barrier makes pre-entry takeover safe; post-go takeover requires positive death evidence and uncertainty quarantines. |
| Work-package globs approximate real future writes | Fail closed on absent, boundless, or ambiguous evidence and preserve singleton execution. |
| Router change lands first or later | Preserve arbitrary additive context keys and keep routing out of supervisor code. |
| `add-supervisor-candidate-work-digest` edits the same skill document | Keep supervise prose/test changes in a dedicated package and rebase before integration. |
| A host dies while children run | Durable handles, heartbeats, and loop-state distinguish proven live/dead/terminal evidence; unknown post-go liveness quarantines without takeover. |
| A child parks at a gate | Release its lease; resume only with durable authorization via parked-to-prepared CAS on the same attempt/token and a new generation. |
| New mode accidentally changes legacy behavior | Default remains legacy; characterization tests cover current callback order and result forms. |

## Migration Plan

1. Land schemas and contract fixtures without enabling delegated mode.
2. Add the optional checkpoint attempt ledger and its runtime asset with backward-compatible loading.
3. Add the neutral scheduler and delegated orchestrator behavior behind an explicit option.
4. Add the downstream host adapter with leased prepare/launch/heartbeat/resume/apply commands.
5. Add the supervise host protocol and recursive runtime-mirror verification.
6. Exercise a fixture roadmap with disjoint and overlapping pairs, including resume and transcript sentinel checks.
7. Keep existing `/autopilot-roadmap` callers on legacy mode until `/supervise` opts in.

Rollback is additive: remove the `/supervise execute` prompt path or stop passing the delegated-lifecycle option. Legacy phase-by-phase execution remains intact, and no data migration or coordinator schema rollback is required.
