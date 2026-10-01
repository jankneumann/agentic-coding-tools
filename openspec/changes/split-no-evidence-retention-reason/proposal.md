# Change: split-no-evidence-retention-reason

## Why

`apply_incumbent_retention` (`agent-coordinator/src/model_routing/resolver.py`) records
`retention.reason = "no-evidence"` whenever no feasible challenger is evidenced. That
includes the case where the **held incumbent row itself is well evidenced**. In the audit
trail, two different situations therefore look identical:

- **"The catalog has no evidence at all."** This is the state at launch, and it is why
  `ROUTING_ADAPTIVE` is safe to turn on.
- **"The incumbent has evidence and no rival does."** This is a router that holds its
  choice on purpose.

The first is a bootstrapping condition and the second is steady state. Operators deciding
whether routing evidence is accumulating, and the feedback writers coming in #612, cannot
tell them apart without re-deriving each catalog row's evidence after the fact.

This is item 5 of #636. It is cheap now and expensive later. No consumer branches on
`no-evidence` today; the only reasons anything branches on are the null-selected pair. And
#609 (benchmark priors) is about to make evidenced incumbents common. If the reason is split
after evidence exists, every audit row written before the split stays permanently ambiguous.

## What Changes

- Add an eighth retention reason, **`no-evidenced-challenger`**. It is emitted when an
  incumbent is supplied, its held catalog row is evidenced (posterior samples ≥ 1 or a
  benchmark prior > 0), and no feasible challenger is evidenced. The outcome is
  unchanged: `retained: true` and the incumbent is selected.
- Narrow **`no-evidence`** to mean what its name says: neither the held incumbent row nor
  any feasible challenger is evidenced. The spec scenario's WHEN clause is tightened so it
  says this explicitly.
- Publish a **v1.3 contract overlay** under this change. It contains the full OpenAPI
  restatement, the decision-record JSON schema and the generated models, with the new value
  in the `retention.reason` enum and in the "kept reasons ⇒ `retained: true`" conditional.
  Following D7 of `retain-static-model-until-routing-evidence`, the archived v1.2 contract
  is not edited.
- Add a **parity test** that fails when the code's `RetentionReason` Literal and the
  contract's `retention.reason` enum disagree. Today only field names are compared, so a
  code-only enum edit would pass.
- Update the operator-facing reason list in `agent-coordinator/CLAUDE.md`.

Nothing here is **BREAKING**. The change is additive: every existing reason keeps its
meaning, selection behavior is unchanged, and `retention.reason` remains an open string in
the database (migration 044 has no CHECK on it), so no migration is needed. One
reclassification does happen: decisions that would have been labelled `no-evidence` while
the incumbent was evidenced now carry the new value. In production that case cannot occur
yet, because the catalog has 0 evidenced rows and every lane is `missing_probe` (#643).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | Selection outcome (`selected`, `retained`) for every retention-table input, before vs after | 0 differences; only the reason label changes, and only in the evidenced-incumbent case | Unit tests over the existing retention matrix (Implementation) |
| Compatibility | Responses for requests without an incumbent | Byte-identical shape: no `retention` key | Existing `test_no_incumbent_keeps_prior_behavior_and_omits_retention` (CI) |
| Observability | Reason values in code vs the contract enum | Exact set equality, enforced by a test | New parity test (CI) |
| Operability | DB migrations required | 0 | Review of the `routing_decisions` constraints (Validation) |

## Approaches Considered

### Approach 1: New enum value with a full v1.3 overlay (Recommended)

Add `no-evidenced-challenger` to the reason enum. Following the D7 overlay convention,
publish a self-contained `v1.3.yaml` plus a revised `routing-decision-record.schema.json`
and `generated/models.py` under this change. Point the contract tests at the new change
with `change_dir()`.

- **Pros**
  - The fact is machine-readable in the one field consumers already read.
  - It follows the established overlay pattern (v1.1 → v1.2 → v1.3), so no new convention.
  - The archived v1.2 stays untouched.
  - The existing "kept reasons ⇒ retained" conditional extends naturally.
- **Cons**
  - The overlay restates the whole API (about 600 lines), mostly copied from v1.2.
  - Contract tests move to the new change id.
- **Effort:** S

### Approach 2: New enum value with a delta-only overlay

Add the enum value, but publish only the changed `Retention` schema as a partial overlay
that is merged with v1.2 at read time.

- **Pros**
  - A much smaller contract diff.
  - The change is visible at a glance.
- **Cons**
  - It breaks the "self-contained overlay" convention that every prior version follows.
  - Readers and tests would need merge logic that doesn't exist yet.
  - The published API is never written down in one place.
- **Effort:** S–M, because the merge tooling has to be built.

### Approach 3: Keep `no-evidence` and add a boolean `retention.incumbent_evidenced`

Leave the enum alone and add an optional boolean to `Retention` that records whether the
held incumbent row was evidenced.

- **Pros**
  - No enum change, so anything matching on reason strings is untouched.
  - The extra fact is available for every retained reason, not only this one.
- **Cons**
  - It keeps the misleading label. `reason: "no-evidence"` next to
    `incumbent_evidenced: true` reads as a contradiction.
  - Every consumer has to read two fields to get one fact.
  - It still needs a v1.3 overlay for the new field.
- **Effort:** S

### Recommended

**Approach 1.** The defect is that the label says something false, and only a new label
fixes that; Approach 3 keeps the false label and adds a field that contradicts it. Approach
1 also costs no new tooling: it repeats the overlay pattern v1.1 and v1.2 already
established. Approach 2's smaller diff would require overlay-merge logic that no test or
reader has today.

### Selected Approach

**Approach 1: new enum value with a full v1.3 overlay.** Selected at Gate 1 (2026-10-01)
with no modifications. Discovery answers folded into the plan:

- **Name:** `no-evidenced-challenger`.
- **Parity test:** included.
- **Spec wording:** the `no-evidence` WHEN clause is tightened.
- **Sequencing:** implementation waits for
  `implement-the-task-router-vendor-x-location-x-model` to merge.

Approaches 2 and 3 were not taken, for the reasons under Recommended.

## Impact

- **Spec capability `model-routing`:** MODIFIED requirement *Incumbent Retention Until
  Routing Evidence* (`specs/model-routing/spec.md`). It tightens the "Empty evidence keeps
  the incumbent" scenario and adds an "Evidenced incumbent without an evidenced challenger"
  scenario.
- **Code**
  - `agent-coordinator/src/model_routing/resolver.py`: `apply_incumbent_retention`.
  - `agent-coordinator/src/model_routing/api.py`: the `RetentionReason` Literal.
- **Contracts** (new, under this change)
  - `contracts/openapi/v1.3.yaml`
  - `contracts/events/routing-decision-record.schema.json`
  - `contracts/generated/models.py`
- **Tests**
  - `tests/model_routing/test_incumbent_retention.py`
  - `tests/model_routing/test_service_incumbent.py`
  - `tests/model_routing/test_incumbent_retention_contracts.py`, repointed to this change,
    gains the reason-parity check.
- **Docs:** `agent-coordinator/CLAUDE.md` (the reason list).
- **Architecture layer:** Coordination (model routing).
- **Sequencing:** implement after `implement-the-task-router-vendor-x-location-x-model`
  merges. That change holds write scope on `resolver.py` and `api.py`, and only its
  validate, review and PR tasks remain.
