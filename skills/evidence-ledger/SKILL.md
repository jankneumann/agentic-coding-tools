---
name: evidence-ledger
description: "Schema and validator for the per-incident evidence ledger: immutable provenance-stamped facts, variable/control signals, and hypotheses that cite facts by id"
category: Infrastructure
tags: [debugging, evidence, schema, validation, infrastructure]
user_invocable: false
---

# Evidence Ledger

Non-user-invocable infrastructure skill. It owns the data contract that evidence-grounded
debugging is built on: a per-incident **evidence ledger** in which observations (facts) are
recorded once with provenance and never edited, and in which every derived claim (signals,
hypotheses) points back at facts by id.

Other skills write ledgers; this skill only defines and checks them.

## Files

| Path | Purpose |
| --- | --- |
| `<skill-base-dir>/scripts/evidence_ledger.py` | Loader, validator and CLI. |
| `<skill-base-dir>/install_assets/openspec/schemas/evidence-ledger.schema.json` | JSON Schema (draft 2020-12). Installed to `openspec/schemas/evidence-ledger.schema.json`. |

## Ledger shape

A ledger is a YAML or JSON document with `schema_version: 1`, a `ledger_id`, and four
collections. Only `facts` is required; the others default to empty.

- **Facts** (`facts`) — the observation tier. Required fields: `id`, `kind`, `source`,
  `gathered_by`, `host`, `time_window {start, end}`, `tool_version`,
  `role` (`variable` or `control`) and `observation`. Optional: `trace_id`, `data`.
  - `kind` is an open snake_case token, so collectors can add kinds without a schema bump.
  - `source_unavailable` is a reserved kind: a collector that could not reach a source records
    that as a fact, rather than silently omitting it.
- **Signals** (`signals`) — exactly one `variable_fact` and one `control_fact` (fact ids),
  classified as `signal` or `noise`.
- **Hypotheses** (`hypotheses`) — a `statement`, the fact ids it `cites`, a `status`
  (`open`, `supported`, `rejected`, `root_cause`) and optional `components`, which are the ids
  of other, non-composite hypotheses in the same ledger.
- **Reverify requests** (`reverify_requests`) — the only way to dispute a fact. Name the
  disputed `fact_id`, give a `reason` and `requested_by`, gather a new fact, and link it as
  `replacement_fact`. The disputed fact stays in the ledger unchanged.

Ids share one namespace across all four collections.

## Immutability

Facts and reverify requests are append-only. When a previous revision is supplied, a fact or
reverify request whose id existed before must still exist and must be identical (compared as
canonical JSON, so key order does not matter). Signals and hypotheses may change between
revisions; hypothesis status is expected to move.

## CLI

```bash
python <skill-base-dir>/scripts/evidence_ledger.py validate <ledger> [--previous <ledger>] [--json]
```

| Exit code | Meaning |
| --- | --- |
| 0 | Valid. |
| 1 | One or more violations. |
| 2 | Usage or load error (missing file, unparseable document). |

Plain output is one `code<TAB>path<TAB>message` line per violation. With `--json` the CLI
prints `{"valid": bool, "violations": [{"code", "path", "message"}]}`. Output is sorted, so
two runs over the same input produce the same bytes.

## Python API

```python
from evidence_ledger import load_ledger, validate_ledger, check_revision

doc = load_ledger(path)  # YAML or JSON; unquoted YAML timestamps stay strings
violations = validate_ledger(doc)  # single-ledger checks
violations += check_revision(old, doc)  # cross-revision immutability
```

Each `Violation` has `code`, `path` (JSON-pointer style) and `message`.

## Violation codes

Codes are stable; callers may branch on them.

**Single ledger** (`validate_ledger`). The schema runs first; if it fails, the semantic checks
are skipped.

| Code | Meaning |
| --- | --- |
| `schema_violation` | The document does not match the JSON Schema. |
| `duplicate_id` | An id is used more than once across the four collections. |
| `unknown_fact_ref` | A signal, citation or reverify target names a fact that does not exist. |
| `signal_role_mismatch` | `variable_fact` is not a `variable` fact, or `control_fact` is not a `control` fact. |
| `unknown_hypothesis_ref` | A component names a hypothesis that does not exist. |
| `self_component` | A hypothesis lists itself as a component. |
| `nested_component` | A component is itself composite (nesting is limited to one level). |
| `replacement_is_target` | A reverify request's replacement is the disputed fact itself. |
| `invalid_timestamp` | A timestamp is not ISO 8601. |
| `time_window_inverted` | A fact's time window starts after it ends. |

**Across revisions** (`check_revision`, CLI `--previous`).

| Code | Meaning |
| --- | --- |
| `ledger_id_changed` | The revision has a different `ledger_id`. |
| `fact_removed` | A previously recorded fact is gone. |
| `fact_mutated` | A previously recorded fact was edited in place. Dispute it with a reverify request instead. |
| `reverify_removed` | A previously recorded reverify request is gone. |
| `reverify_mutated` | A previously recorded reverify request was edited. |

## Out of scope

The signal/noise matrix, the evidence gates that apply to `root_cause`, and fact collection
are owned by later changes. This skill only guarantees the record exists, is well formed,
and is immutable.
