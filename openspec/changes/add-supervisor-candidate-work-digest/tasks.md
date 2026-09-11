# Tasks — add-supervisor-candidate-work-digest

Five phases, one per work package. Tests precede the behavior they verify (TDD RED →
GREEN). Capability short name: `sv` = `supervise`.

---

## Phase 0 — wp-contracts: runtime and persistence contracts first

- [x] 0.1 RED: add schema fixtures/tests covering full rubric and digest documents; exact
      five-factor justification coverage; strict canonical stub keys; duplicate/missing/
      unknown score-key semantic rejection; and supervisor-record decisions for approved
      refine-roadmap, approved plan-roadmap, deferred, rejected, and invalid metadata — **S**
      **Spec scenarios**: sv *Score coverage must exactly match each batch*, *Decisions
      round-trip without state loss*
      **Dependencies**: None

- [x] 0.2 GREEN: finalize the change-local schemas, install byte-identical stable runtime
      copies at `openspec/schemas/supervise-rubric-score.schema.json` and
      `openspec/schemas/supervise-digest.schema.json`, and extend both canonical
      supervisor-record schemas with `roadmap_ref`, `route`, `until`, `reason`, and
      decision-specific conditions — **S**
      **Contracts**: all four runtime schemas plus two change-local source schemas
      **Dependencies**: 0.1

- [ ] Checkpoint: schema tests green; runtime copies match change-local sources; review
      the diff and run strict OpenSpec validation

## Phase 1 — wp-digest-module: state helpers and `digest.py`

- [ ] 1.1 RED: test strict reversible key encoding; retained-plus-fresh store merge;
      byte-stable writes; terminal prune and due-deferral maintenance before SENSE and
      unchanged exit; maintained-baseline precedence over later capacity failure; the
      atomic 20-candidate capacity bound with named overflow; dry-run no-write and
      pending-journal reporting behavior; `--force` cache reuse; and cycle fingerprint
      stability across committed store/cache/digest outputs — **S**
      **Spec scenarios**: sv *Digest on a fresh cycle*, *Supervisor outputs do not
      invalidate their own cache*, *Lifecycle maintenance runs before unchanged exit*,
      *Dry run writes nothing*
      **Dependencies**: 0.2

- [ ] 1.2 GREEN: implement store/key/maintenance behavior in `digest.py`; update
      `cycle_state._tree_listing` to exclude the candidate store, rubric caches, and
      digest artifact while preserving all non-supervisor inputs — **S**
      **Design decisions**: D1, D3
      **Dependencies**: 1.1

- [ ] 1.3 RED: test exact batch-key/fingerprint matching; host-manifest `as_of` exactness
      against missing/earlier/later/naive/future `scored_at`; cache-only validation
      against preserved `generated_at`; `state_updated_at`; complete emitted ranking
      policy; risk inversion; Git-commit staleness and modified/untracked/future-clock-skew
      null behavior; strict dependency-status indexing
      (empty/completed/archived/pending/blocked/unresolved/pending-stub), decision/readiness buckets, stable
      stub-key tie-break, shuffled inputs, schema-valid singleton caches, whole-backlog
      invalidation on changed fingerprint, byte-identical unchanged reuse, candidate-only
      section assignment, and rank-to-back-edge synchronization — **M**
      **Spec scenarios**: sv *Ranking has one deterministic answer*, *Score coverage must
      exactly match each batch*, *A changed tree re-scores the backlog*, *Retained backlog
      is composed without operational regression*, *Digest state survives rehydration*
      **Dependencies**: 0.2

- [ ] 1.4 GREEN: implement `rank` and read-only `digest` rendering; source runtime schemas
      only from stable paths; keep reuse/cache diagnostics on stdout; validate prior bytes
      before reuse; stage cache/digest/mirror replacements in memory and publish only after
      whole-document validation; publish replacement and deletion operations through the
      fsynced roll-forward journal, including terminal candidate/cache removal, with
      `digest.json` last; recover interruption at every operation boundary on non-dry-run
      mutating command startup and
      report without mutation on dry-run; leave the successful
      ledger fingerprint unadvanced on scoring failure; update the rehydrated record
      through `write_mirror` — **M**
      **Design decisions**: D2, D3, D5, D6
      **Dependencies**: 1.2, 1.3

- [ ] 1.5 RED: test the public `prepare-batch --as-of` manifest contract and bounded
      evidence loader against valid UTF-8, URI, missing, binary,
      symlink, traversal, oversized, secret-bearing, and prompt-injection fixtures; prove
      unavailable evidence is not read and becomes null-staleness degradation; prove the
      20-stub/full-canonical-manifest 64-KiB bounds, including one individually oversized
      stub, and deterministic stdout bytes — **S**
      **Spec scenarios**: sv *Unsafe or unavailable provenance is not read*
      **Dependencies**: 0.2

- [ ] 1.6 GREEN: implement `prepare-batch`, contained regular-file loading, 2-KiB
      excerpting, `roadmap-runtime` `sanitize_string` reuse, untrusted-data framing, and
      deterministic one-batch manifest output — **S**
      **Design decisions**: D8
      **Dependencies**: 1.5

- [ ] 1.7 RED: test stub-to-request priority placement/`--after`, next free item ID,
      provenance, acceptance requirement, local/cross-roadmap/completed dependency
      resolution, unresolved dependency refusal, change-ID collision, real refiner preview
      and apply, and stale-base refusal — **M**
      **Spec scenarios**: sv *Approve a stub into an existing roadmap*, *Unresolved
      dependency is refused*, *Missing acceptance outcomes are refused*, *Approval never
      bypasses the preview*
      **Dependencies**: 0.2

- [ ] 1.8 GREEN: implement `stub-to-request` without any roadmap write; build the same
      strict all-status index from roadmap YAML, active changes, and archived changes, use
      ri-16's typed reference rules but not its ready frontier, and emit a temporary request
      for the host/refiner transaction — **S**
      **Design decisions**: D4
      **Dependencies**: 1.7

- [ ] 1.9 RED: test rank-created pending entries and `decide` round trips for all decisions,
      conditional metadata validation, newer-handoff state preservation, same-key replace,
      unrelated-entry preservation, and an AST guard against roadmap writes/LLM/network
      calls — **S**
      **Spec scenarios**: sv *Digest state survives rehydration*, *Decisions round-trip
      without state loss*, *Approval never bypasses the preview*
      **Dependencies**: 0.2

- [ ] 1.10 GREEN: extend `_clean_digested_stub`; implement rehydrated-record merge and
      `decide`; preserve idempotent `write_mirror` behavior — **S**
      **Design decisions**: D3, D5
      **Dependencies**: 1.4, 1.9

- [ ] Checkpoint: supervise suite green including host-assisted invariant; ruff clean;
      verify only the declared module/state/test files changed

## Phase 2 — wp-rubric-prompt: bounded analyst contract

- [x] 2.1 RED: test that the template names all five factors and fixed scale (including
      risk inversion), embeds the stable runtime schema ID, requires JSON-only exact-key
      output, identifies the analyst archetype, declares batch/evidence limits, and marks
      stub/provenance blocks as untrusted data whose instructions must not be followed — **S**
      **Spec scenarios**: sv *Digest on a fresh cycle*, *Unsafe or unavailable provenance
      is not read*
      **Dependencies**: 0.2

- [x] 2.2 GREEN: write `templates/rubric-prompt.md` with `{{batch}}`, `{{ready_set}}`, and
      `{{fingerprint}}` slots; document the single-manifest dispatch, exact timestamp
      echo, 120-second timeout and one retry, and analyst fallback (omit model override if
      analyst resolution is unavailable) — **S**
      **Design decisions**: D2, D8
      **Dependencies**: 2.1

- [ ] Checkpoint: prompt contract test green; review the prompt as a security boundary

## Phase 3 — wp-skill-docs: compose candidate state into CYCLE and INTAKE

- [ ] 3.1 RED: extend `TestWorkflowContract` so CYCLE runs maintenance before unchanged
      exit, merges retained backlog with fresh stubs, uses bounded analyst dispatch, renders
      candidate additions without replacing gate deadlines/ready/blocker/sensor lines,
      records keys, and keeps dry-run non-persisting; INTAKE names the exact preview/apply/
      decide and new-roadmap fallback sequence — **S**
      **Spec scenarios**: all CYCLE composition and approval routing scenarios
      **Dependencies**: 1.4, 1.6, 1.8, 1.10, 2.2

- [ ] 3.2 GREEN: rewrite CYCLE steps 1–5 and Output/Idempotency sections around lifecycle
      preflight, store, bounded rubric dispatch, candidate rank/digest composition, back-edge
      synchronization, and unchanged/any-lifecycle-transition behavior — **S**
      **Design decisions**: D1, D2, D5, D6, D8
      **Dependencies**: 3.1

- [ ] 3.3 GREEN: add INTAKE "approve from digest" with acceptance drafting, request
      generation, preview, operator confirmation, apply with expected SHA, decide, and
      `/plan-roadmap --new <slug> "<pitch>" --draft` fallback — **S**
      **Design decisions**: D4, D5
      **Dependencies**: 3.1

- [ ] 3.4 Run `bash skills/install.sh --check`, resync mirrors if required, then prove
      canonical and `.agents`/`.claude` supervise skills are byte-identical — **XS**
      **Dependencies**: 3.2, 3.3

- [ ] Checkpoint: supervise workflow tests green; mirrors synchronized

## Phase 4 — wp-integration

- [ ] 4.1 Run the complete supervise suite and ruff. Execute a two-cycle fixture flow:
      fresh store → bounded score → rank → mirror/rehydrate → candidate composition →
      decision → output-only commit simulation → unchanged cache hit/prune/due transition.
      Exercise terminal-only pruning, dry-run lifecycle reporting, modified/untracked
      provenance (including future-dated Git history), an individually oversized stub, the
      21st-candidate atomic overflow, and timeout/invalid/partial-score paths. Interrupt
      scored and terminal-only/mixed lifecycle journals after every delete/replace boundary,
      prove per-parent fsync, roll-forward recovery, and retry without successful-ledger
      advancement, and prove
      no mixed cache/mirror state lands. Execute the real stub-to-request → refiner preview
      → apply transaction and stale-SHA
      refusal against a temporary roadmap — **M**
      **Dependencies**: all Phase 1–3 tasks

- [ ] 4.2 Run all `skills/tests`, work-package schema/DAG/overlap validation, context-impact
      validation against the feature base, and `openspec validate
      add-supervisor-candidate-work-digest --strict`; append the Implementation PhaseRecord,
      update checkboxes, commit, and push — **S**
      **Dependencies**: 4.1
