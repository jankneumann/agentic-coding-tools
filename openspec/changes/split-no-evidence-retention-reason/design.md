# Design: split-no-evidence-retention-reason

## Context

`apply_incumbent_retention` (`agent-coordinator/src/model_routing/resolver.py`) handles a
catalog-matched incumbent like this:

```python
if matches:
    held = max(matches, key=lambda c: c.score)
    if best_challenger is None:
        return RetentionDecision(held, True, "no-evidence", margin, held.score)
```

The evidence of `held` is never consulted. The reason enum is stated in four places that
must agree:

- `RetentionReason` in `api.py`
- the archived v1.2 OpenAPI overlay
- the archived decision-record JSON schema
- the archived `generated/models.py`

Today only field names are cross-checked, not enum values.

## Goals / Non-Goals

**Goals**
- Give the evidenced-incumbent case its own reason value.
- Keep every selection outcome identical.
- Make the code/contract enum drift detectable.

**Non-goals**
- #636 items 4, 6 and 7: the persisted assignment for retained decisions, routing for
  vendorless or alias incumbents, and the quota-exhausted incumbent.
- Specifying #647's "displaced incumbent is not explored" behavior in the exploration
  scenario. That is a separate spec edit if wanted.
- Any change to the infeasible or unresolved branches. Those reasons already describe
  their situations precisely.

## Decisions

### D1 — Evidence is judged on the held row

`no-evidenced-challenger` fires when `best_challenger is None` and `held.evidenced` is true.
`held` is the incumbent's best-scoring matching row, the same row that supplies
`incumbent_score`. A decision therefore reports the evidence of the exact row it scored.

- **Rejected: "any matching row is evidenced".** An incumbent can match several rows (for
  example different endpoints for the same `(vendor, model)`). If a non-held row were
  evidenced, the reason would describe a row the decision didn't use.

### D2 — The branch order is unchanged

The check is inserted inside the existing `best_challenger is None` branch. `below-margin`,
`challenger-evidenced-above-margin`, the infeasible branches and the unresolved branch keep
their exact conditions. That keeps the NFR "0 selection differences" true by construction:
only the label in one existing branch can change.

### D3 — A self-contained v1.3 overlay; the archive is untouched

This follows `retain-static-model-until-routing-evidence` D7. This change ships three
contract files:

- `contracts/openapi/v1.3.yaml`: a full restatement of v1.2.
- `contracts/events/routing-decision-record.schema.json`
- `contracts/generated/models.py`

Each differs from its v1.2 counterpart only in three places:

- `no-evidenced-challenger` is added to the `retention.reason` enum.
- It is added to the "kept reasons ⇒ `retained: true`" conditional. The kept set goes from
  4 values to 5.
- It is **not** added to the set allowed to have `selected: null`. It always has a held row,
  like `no-evidence` and `below-margin`.

`test_incumbent_retention_contracts.py` is repointed to this change with `change_dir()`.
Once this change archives, `change_dir()` resolves the archived copy, so the tests keep
working through archival.

### D4 — The parity test compares values, not just names

The new test asserts set equality across:

- `typing.get_args(RetentionReason)`
- the v1.3 `Retention.reason` enum
- the record-schema `retention.reason` enum
- the generated `RetentionReason` Literal

It also asserts that the contract's kept-reasons conditional equals the set of reasons that
`apply_incumbent_retention` (plus `exploration-evidenced`) can return with
`retained=True`. That second assertion uses the existing `_KEPT` set, updated, as the
oracle.

### D5 — No migration

Migration 044 puts no CHECK on `retention->>'reason'`, and the audit RPC passes the
`retention` JSONB through unchanged. A new value needs no schema change.

### D6 — Implement after the task-router change merges

`implement-the-task-router-vendor-x-location-x-model` holds write scope on `resolver.py`
and `api.py`, and only its validate, review and PR tasks remain. Planning touches neither
file. `/implement-feature` starts once that PR merges.

## Risks / Trade-offs

- **The overlay repeats about 600 lines of v1.2.** Accepted for convention consistency:
  every published version is readable on its own. The diff that matters is three lines,
  and `design.md` names them.
- **Reclassification of historical meaning.** Before this change, `no-evidence` rows may
  include evidenced-incumbent decisions. In production none exist: 0 evidenced catalog rows
  and every lane is `missing_probe` (#643). So pre-change rows are unambiguous in practice.
  That is also why this should land before #609.
