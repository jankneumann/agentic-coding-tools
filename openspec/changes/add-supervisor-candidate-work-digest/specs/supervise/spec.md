# supervise — delta

## ADDED Requirements

### Requirement: Candidate-Work Digest

The `/supervise` skill SHALL maintain a ranked candidate-work backlog conforming to the stable runtime `digest.schema.json`. Fresh post-dedupe stubs SHALL be merged with retained pending/deferred store files, persisted byte-stably at `openspec/supervise/candidates/<encoded-stub-key>.json`, and represented in `back_edge.digested_stubs`. Keys SHALL be accepted only as `change:<valid-change-id>` or `prov:<hex32>` and SHALL be encoded reversibly before path construction.

A host-dispatched analyst SHALL score bounded batches against `rubric-score.schema.json`; `scripts/digest.py` SHALL perform no LLM or network call. Each batch SHALL contain at most 20 stubs and 64 KiB total evidence, with each provenance excerpt capped at 2 KiB. Provenance content SHALL be treated as untrusted data: only contained UTF-8 regular repo files MAY be read, symlinks and URIs SHALL NOT be followed, excerpts SHALL be secret-redacted and delimited, and unavailable evidence SHALL produce `staleness_days: null` plus a degraded marker.

`digest.py rank` SHALL reject duplicate, missing, or unknown score keys and SHALL use this total order: pending before future-deferred; dependency-ready before blocked; descending `3*relevance + 3*value + 2*readiness + scope_fit + risk - min(floor(staleness_days/30), 5)` where risk 5 means safest and null staleness has no penalty; then ascending `stub_key`. Rejected work SHALL be excluded. Score caches SHALL be schema-valid singleton rubric documents keyed by cycle fingerprint. The cycle fingerprint SHALL exclude the candidate store, rubric caches, and `digest.json` so supervisor-output-only commits do not invalidate it.

`openspec/supervise/digest.json` SHALL be candidate-work-focused and composable: `new_this_cycle` SHALL contain only freshly stored keys, `needs_decision` SHALL contain retained pending/deferred keys, `degraded` SHALL identify candidate-evidence degradation, and `ranked` SHALL contain the full surviving backlog with all five factor scores and justifications plus mechanical signals. The host SHALL merge these additions into the existing five-section supervisor prose after rendering verified gates (including deadlines), ready work, blockers, and degraded sensors; the candidate artifact SHALL NOT replace those operational lines. `generated_at` SHALL be the maximum rubric `scored_at`; cache/reuse diagnostics SHALL be stdout-only. Under `--dry-run`, nothing below `openspec/supervise/` SHALL be created, modified, or removed.

#### Scenario: Digest on a fresh cycle
- **GIVEN** three schema-valid stubs survive dedupe and no cached scores exist
- **WHEN** the CYCLE runs
- **THEN** three encoded, byte-stable files SHALL exist under `openspec/supervise/candidates/`
- **AND** the host SHALL dispatch rubric batches whose requested keys cover each stub exactly once
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

#### Scenario: Supervisor outputs do not invalidate their own cache
- **GIVEN** a completed cycle's store, caches, digest, ledger, and mirror are committed
- **WHEN** the next CYCLE runs with no non-supervisor tree change and no due lifecycle transition
- **THEN** the cycle fingerprint SHALL equal the prior fingerprint
- **AND** no rubric sub-agent SHALL be dispatched
- **AND** the validated prior `digest.json` SHALL be re-presented byte for byte

#### Scenario: A changed tree re-scores the backlog
- **GIVEN** valid caches from the prior cycle
- **WHEN** a non-supervisor cycle input changes
- **THEN** the fingerprint SHALL change
- **AND** the complete retained-plus-fresh backlog SHALL be dispatched in deterministic bounded batches

#### Scenario: Lifecycle maintenance runs before unchanged exit
- **GIVEN** one approved stub file and one stub deferred until 2026-09-15
- **WHEN** a normal CYCLE runs on 2026-09-16 over an otherwise unchanged tree
- **THEN** the approved stub file and cache SHALL be pruned before the fingerprint early exit
- **AND** the deferred stub SHALL return to pending and be re-ranked from its cache without rubric dispatch

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

Approving a stub into an existing roadmap SHALL use `digest.py stub-to-request <stub_key> --roadmap <roadmap-id> --acceptance <text>... [--after <item-id>]` followed by `refiner.py preview` and, after operator confirmation, `refiner.py apply --expect-base-sha256 <preview-base>`. The request SHALL contain exactly one `op: add`; SHALL map title, description plus provenance, rationale, effort, and suggested change ID; SHALL assign the next free `ri-NN`; SHALL place by stub priority unless `--after` overrides it; and SHALL resolve prerequisites to local `depends_on`, typed `external_depends_on`, or already-satisfied archived dependencies. Unresolved candidate dependencies SHALL fail closed. The refiner SHALL own final priority renumbering.

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
