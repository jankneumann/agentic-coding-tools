# supervise — delta

## ADDED Requirements

### Requirement: Candidate-Work Digest

The `/supervise` skill SHALL produce, at the end of every CYCLE run, a ranked digest of candidate-work stubs conforming to `contracts/schemas/digest.schema.json`, written to `openspec/supervise/digest.json` and rendered as the five-section prose digest. Surviving stubs (after dedupe) SHALL be persisted one file per stub at `openspec/supervise/candidates/<stub_key>.json`, byte-stable, with lifecycle state held in the supervisor record's `back_edge.digested_stubs` rather than in the file. Ranking SHALL be a pure function of (a) per-stub factor scores conforming to `contracts/schemas/rubric-score.schema.json`, produced by a host-dispatched rubric sub-agent from `templates/rubric-prompt.md`, and (b) mechanical signals computed by `scripts/digest.py`: dependency readiness from `ready_across_roadmaps`, provenance-artifact staleness, and prior decisions (`deferred` sinks to the bottom until `until` passes; `rejected` is excluded). Weights SHALL live in `digest.py`. Factor scores SHALL be cached at `openspec/supervise/candidates/<stub_key>.rubric.json` keyed by the cycle fingerprint; when the fingerprint is unchanged the skill SHALL reuse cached scores and SHALL NOT dispatch the rubric sub-agent. `skills/supervise/scripts/` SHALL continue to make no LLM or network call. Under `--dry-run` nothing under `openspec/supervise/` SHALL be written.

#### Scenario: Digest on a fresh cycle
- **GIVEN** three schema-valid stubs survive dedupe and no cached scores exist
- **WHEN** the CYCLE runs
- **THEN** three files SHALL exist under `openspec/supervise/candidates/`
- **AND** the host SHALL dispatch exactly one rubric sub-agent for the batch
- **AND** `digest.json` SHALL list the three stubs with `rank`, five factor scores with justifications, mechanical signals, and `decision: pending`

#### Scenario: Ranking is a pure function of scores and signals
- **WHEN** `digest.py rank --scores S` runs twice over an unchanged tree with the same `S`
- **THEN** the two `digest.json` outputs SHALL be byte-identical
- **AND** changing one factor score SHALL change the ordering only as the documented weights dictate

#### Scenario: Unchanged fingerprint reuses cached scores
- **GIVEN** cached `.rubric.json` files whose `fingerprint` equals the current cycle fingerprint
- **WHEN** the CYCLE runs
- **THEN** no rubric sub-agent SHALL be dispatched
- **AND** the digest SHALL be identical to the prior run's

#### Scenario: Schema-invalid rubric output is rejected
- **WHEN** the rubric sub-agent returns JSON missing a factor or with a score outside 1–5
- **THEN** `digest.py rank` SHALL exit non-zero naming the stub and the failing field
- **AND** no `digest.json` SHALL be written

#### Scenario: Prior decisions shape the ranking
- **GIVEN** `back_edge.digested_stubs` marks stub A `rejected` and stub B `deferred` with `until` in the future
- **WHEN** the digest is ranked
- **THEN** A SHALL be absent from the digest
- **AND** B SHALL appear after every `pending` stub, flagged `deferred`

#### Scenario: Dry run writes nothing
- **WHEN** the CYCLE runs with `--dry-run`
- **THEN** no file under `openspec/supervise/` SHALL be created or modified
- **AND** cached scores MAY be read

#### Scenario: Digest state survives rehydration
- **GIVEN** a cycle ended with two stubs `pending` and one `deferred`
- **WHEN** a fresh session rehydrates from the supervisor record
- **THEN** its `back_edge.digested_stubs` SHALL list all three with their ranks and decisions
- **AND** the store SHALL contain all three stub files

### Requirement: Digest Approval Routing

Approving a stub from the digest SHALL route it into the roadmap without leaving the conversation, through `refine-roadmap`'s previewed transaction. `digest.py stub-to-request <stub_key> --roadmap <roadmap-id> --acceptance <text>... [--after <item-id>] [--depends-on <item-id>...]` SHALL render a refinement request YAML with exactly one `op: add` whose item maps `title`, `description` (with a provenance line naming `source_artifact` and `finding_ids`), `rationale`, `effort`, `priority`, `depends_on`, and `change_id: <suggested_change_id>` from the stub, assigns the next free `item_id`, and sets `acceptance_outcomes` from the required `--acceptance` values. The host SHALL run `refiner.py preview`, present the effects, and on operator confirmation run `refiner.py apply --expect-base-sha256`. `digest.py decide <stub_key> --decision approved|deferred|rejected [--roadmap-ref <ref>] [--until <date>] [--reason <text>]` SHALL record the decision in `back_edge.digested_stubs` and, for `approved` and `rejected`, remove the stub file on the next cycle. A stub that does not fit an existing roadmap SHALL be routed to `/plan-roadmap --new <slug> "<pitch>" --draft`. No approval path SHALL dispatch an implementer, push, or open a PR.

#### Scenario: Approve a stub into an existing roadmap
- **GIVEN** a `pending` stub with `suggested_change_id: add-recovery-gate` and a roadmap `roadmap-x` whose highest item is `ri-08`
- **WHEN** the operator approves it with two acceptance outcomes
- **THEN** `stub-to-request` SHALL emit a request with one `op: add`, `item_id: ri-09`, `change_id: add-recovery-gate`, both outcomes, and a description ending with the provenance line
- **AND** `refiner.py preview` SHALL report one new item and no errors
- **AND** after `apply`, `roadmap.yaml` SHALL contain `ri-09` with status `approved` on an approved roadmap

#### Scenario: Approval never bypasses the preview
- **WHEN** the skill approves a stub
- **THEN** `roadmap.yaml` SHALL be modified only by `refiner.py apply` with the `--expect-base-sha256` from the immediately preceding preview
- **AND** `skills/supervise/scripts/` SHALL contain no write to any `roadmap.yaml`

#### Scenario: Decision is recorded and the store is pruned
- **WHEN** `digest.py decide <key> --decision approved --roadmap-ref roadmap-x:ri-09` runs
- **THEN** `back_edge.digested_stubs` SHALL carry `{stub_key, decision: approved, roadmap_ref, decided_at}`
- **AND** the next CYCLE SHALL remove `openspec/supervise/candidates/<key>.json` and its `.rubric.json`

#### Scenario: Deferred stub returns after its date
- **GIVEN** a stub deferred `--until 2026-09-15`
- **WHEN** a CYCLE runs on 2026-09-16
- **THEN** the stub SHALL be ranked as `pending` again

#### Scenario: Missing acceptance outcomes are refused
- **WHEN** `stub-to-request` is invoked without `--acceptance`
- **THEN** it SHALL exit non-zero explaining that `refine-roadmap` requires at least one acceptance outcome
- **AND** nothing SHALL be written

#### Scenario: New-roadmap stub falls back to plan-roadmap
- **GIVEN** a stub whose `suggested_change_id` matches no active roadmap's scope
- **WHEN** the operator approves it
- **THEN** the skill SHALL invoke `/plan-roadmap --new <slug> "<pitch>" --draft` with the stub's title and description
- **AND** SHALL record the decision with `roadmap_ref: null` and `route: plan-roadmap`
