# Design: Define evidence ledger schema with immutable facts

## Context

The roadmap `evidence-grounded-debugging` frames debugging as constraint satisfaction over
two tiers:

- The **factual tier** holds immutable, gathered evidence.
- The **derivative tier** holds hypotheses. A hypothesis is only valid when it is consistent
  with every fact.

This change defines the data structure that holds both tiers, plus the validator that keeps
the factual tier immutable. ri-02 extends the same validator with the hypothesis-by-fact
matrix and the `root_cause` gates. ri-03, ri-04, ri-05 and ri-10 read and write ledgers.

## Goals

- One versioned schema that every later roadmap item consumes unchanged.
- A deterministic, offline validator with stable violation codes that consumers can assert on.
- Immutability of recorded facts enforced by a mechanical check, not by convention.

## Non-Goals

- The matrix, signal-strength counts, all-✓ rows, the `root_cause` gates and the necessity
  check. These belong to ri-02.
- Writing ledgers. That belongs to ri-03 and ri-05.

## Decisions

### D1 — A new infrastructure skill owns the format

`skills/evidence-ledger/` holds `SKILL.md`, `scripts/evidence_ledger.py` and
`install_assets/openspec/schemas/evidence-ledger.schema.json`.

The skill is not user-invocable. It is registered as `portable` in
`skills/install-manifest.json`, so `install.sh` ships it, schema included, to downstream
repositories. Approaches B and C in the proposal were rejected for the reasons recorded there.

### D2 — Three byte-identical schema copies, with `install_assets` as the runtime source

| Copy | Role |
| --- | --- |
| `skills/evidence-ledger/install_assets/openspec/schemas/evidence-ledger.schema.json` | What the validator loads at runtime. Resolved relative to the script file (`Path(__file__).resolve().parents[1]`), so it works from the canonical tree and from installed runtime copies alike. |
| `openspec/schemas/evidence-ledger.schema.json` | The canonical repository copy, next to the other OpenSpec schemas. |
| `openspec/changes/<id>/contracts/schemas/evidence-ledger.schema.json` | The draft this plan was written against. |

A drift test asserts that all three copies are byte-identical. It locates the third copy
with `change_dir()`, so archival does not break the test.

`install.sh` only *reports* drift, which is why a test must fail on it. The same pattern is
used by `ownership-runtime`.

### D3 — Ledger shape (schema_version 1)

**Top level**
- Required:
  - `schema_version` (const `1`);
  - `ledger_id`;
  - `facts`.
- Optional:
  - `subject`;
  - `created_at`;
  - `signals`, `hypotheses` and `reverify_requests`. Each defaults to `[]`, so a
    facts-only ledger written by `collect-facts` (ri-05) is valid without empty arrays.
- Every object in the schema sets `additionalProperties: false`.

**Fact**
- Required fields:
  - `id`;
  - `kind`: a snake_case token. It is open-ended, so ri-05 can add kinds without a schema
    bump. `source_unavailable` is a documented, reserved kind;
  - `source`;
  - `gathered_by`;
  - `host`;
  - `time_window {start, end}`;
  - `tool_version`;
  - `role ∈ {variable, control}`;
  - `observation`: a non-empty string. A fact without content cannot be cited meaningfully,
    so the roadmap's field list is extended by this single required field.
- Optional fields:
  - `trace_id`;
  - `data`: a free-form object for structured payloads.

**Signal**
- Required fields:
  - `id`;
  - `variable_fact`;
  - `control_fact`;
  - `classification ∈ {signal, noise}`.
- Optional fields: `metric` and `description`.
- `variable_fact` and `control_fact` are scalar fact ids, not arrays. "Exactly one" is
  therefore structural in the schema. The roles they point to are semantic, and the
  validator checks them (D6).

**Hypothesis**
- Required fields:
  - `id`;
  - `statement`;
  - `cites`: an array of fact ids. It may be empty while the status is `open`;
  - `status ∈ {open, supported, rejected, root_cause}`.
- Optional fields: `components` and `notes`.
- The `root_cause` value is defined here. The gates that apply to it are added by ri-02.

**Reverify request**
- Required fields:
  - `id`;
  - `fact_id`: the disputed fact;
  - `reason`;
  - `requested_by`.
- Optional field: `replacement_fact`, the id of the newly gathered fact.

### D4 — One id namespace per ledger

Ids are unique across all four collections. This means a citation, a signal reference or a
reverify target can never resolve to the wrong kind of entry. The id pattern is
`^[A-Za-z][A-Za-z0-9_.:-]*$`.

### D5 — `components` are hypothesis ids

A multi-cause hypothesis lists the ids of other hypotheses in the same ledger as its
components. This is what lets ri-02's necessity check remove one component at a time and
re-evaluate the facts it explains.

The validator rejects:
- unknown component ids;
- a hypothesis that lists itself as a component;
- a component that is itself composite. Nesting is limited to one level, which keeps the
  necessity check finite and readable.

### D6 — Validation layers and stable violation codes

`validate_ledger(doc) -> list[Violation]`. A `Violation` is a frozen dataclass with `code`,
`path` and `message`. The layers run in order:

1. **Schema:** `Draft202012Validator.iter_errors`. Each error becomes `schema_violation`, with
   a JSON-pointer-style path. If the schema fails, the semantic layers are skipped, because
   their assumptions about shape would not hold.
2. **Semantic:**
   - `duplicate_id`;
   - `unknown_fact_ref`: a signal reference, a citation or a reverify target that does not
     resolve to a fact;
   - `signal_role_mismatch`: `variable_fact` does not have role `variable`, or `control_fact`
     does not have role `control`;
   - `signal_same_fact`: the variable and control are the same fact;
   - `unknown_hypothesis_ref`, `self_component` and `nested_component` (D5);
   - `replacement_is_target`: a reverify request whose replacement is the disputed fact
     itself;
   - `invalid_timestamp`: a value that `datetime.fromisoformat` cannot parse, after a trailing
     `Z` is normalized;
   - `time_window_inverted`: `start` is after `end`.

`check_revision(previous, current) -> list[Violation]`:
- `ledger_id_changed`;
- `fact_removed` and `fact_mutated`. Facts are compared by id, using canonical JSON
  equality: sorted keys, after the YAML or JSON load;
- `reverify_removed` and `reverify_mutated`. Reverify requests are audit records, so they are
  append-only too.

Signals and hypotheses are derivative-tier entries. They may change between revisions,
because hypothesis status is expected to move.

### D7 — Disputes go through reverify_request plus a new fact

A disputed fact is never edited. The dispute is recorded instead as:
- a `reverify_request` naming the old fact;
- a newly gathered fact with its own id, provenance and time window, linked from
  `replacement_fact`.

The old fact stays in the ledger. History therefore shows both what was believed and why it
was re-gathered.

ri-02 decides how a disputed fact participates in the matrix. This change only guarantees
that the record exists and is immutable.

### D8 — Load YAML or JSON by suffix

`load_ledger(path)` loads by file suffix:
- `.yaml` and `.yml` use `yaml.safe_load`;
- `.json` uses `json.loads`;
- anything else is tried as JSON first, then YAML.

ri-03 writes `evidence-ledger.yaml`, and the tests and contracts use JSON. Both are first
class.

### D9 — CLI contract

```
python <skill-base-dir>/scripts/evidence_ledger.py validate <ledger> [--previous <ledger>] [--json]
```

| Exit code | Meaning |
| --- | --- |
| 0 | Valid. |
| 1 | One or more violations. |
| 2 | Usage or load error. |

With `--json`, the CLI prints `{"valid": bool, "violations": [{code, path, message}]}`.
Without it, the CLI prints one `code<TAB>path<TAB>message` line per violation.

`--previous` adds `check_revision` on top of the single-ledger validation of `<ledger>`.

### D10 — Tests and registration

Tests live in `skills/tests/evidence-ledger/` and cover:
- valid fixtures;
- invalid fixtures, one per violation code;
- revision pairs: an in-place edit is rejected, and the same dispute expressed as a reverify
  request plus a new fact is accepted;
- the CLI exit codes;
- the drift test (D2).

The module name `evidence_ledger` is flat-name-unique across `skills/`. The directory is
therefore safe to list in the shared `testpaths` of `skills/pyproject.toml`, which satisfies
the `ci_coverage` guard.

## Risks and Trade-offs

- **The required `observation` field is not in the roadmap's field list.** Mitigation: it is
  additive, and every consumer needs a fact body.
- **Revision checking needs the previous ledger, so callers must supply it.** Mitigation:
  `--previous` takes any file, including `git show HEAD:<path>` output that has been written
  to a temporary file. ri-03 wires this into its flow.
- **Open-ended `kind`.** It trades schema-level rigour for extension without a version bump.
  Reserved kinds are documented in `SKILL.md`.
