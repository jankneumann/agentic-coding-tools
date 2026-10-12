# Contracts — define-evidence-ledger-schema-with-immutable-facts

| Contract type | Applies | Artifact |
| --- | --- | --- |
| OpenAPI | No | This change adds no HTTP surface. |
| Database | No | This change makes no schema or migration change. |
| Event / data format | **Yes** | [`schemas/evidence-ledger.schema.json`](schemas/evidence-ledger.schema.json) |
| Type generation | No | Python consumers use plain dicts plus the `Violation` dataclass in `evidence_ledger.py`. |

## Data format

`schemas/evidence-ledger.schema.json` is the draft this plan was written against. The
implementation promotes it **byte-identically** to two places (design D2):
- `openspec/schemas/evidence-ledger.schema.json`
- `skills/evidence-ledger/install_assets/openspec/schemas/evidence-ledger.schema.json`

A drift test fails if any of the three copies diverge. That test locates this directory with
`change_dir()`.

### Rules the validator enforces

The validator enforces these rules beyond the schema (design D6):
- ids are unique across all collections;
- `signal_role_mismatch`, `signal_same_fact` and `unknown_fact_ref`;
- `unknown_hypothesis_ref`, `self_component` and `nested_component`;
- `replacement_is_target`;
- `invalid_timestamp` and `time_window_inverted`.

Across revisions (`check_revision`), it reports:
- `ledger_id_changed`;
- `fact_removed` and `fact_mutated`;
- `reverify_removed` and `reverify_mutated`.

### CLI contract

The CLI contract is defined in design D9:
- exit code 0 means the ledger is valid;
- exit code 1 means there are violations;
- exit code 2 means a usage or load error;
- `--json` prints `{"valid": bool, "violations": [{"code", "path", "message"}]}`.
