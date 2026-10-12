# Define evidence ledger schema with immutable facts

> Parent roadmap: `evidence-grounded-debugging` (item `ri-01`)
> Change ID: `define-evidence-ledger-schema-with-immutable-facts`
> Effort: M
> Priority: 1

## Why

Debugging in this repository has no shared record that ties a hypothesis to the evidence
behind it. The roadmap's core gap is exactly that missing schema. Without it, an agent can
present a root cause with no citations, quietly "correct" an observation that disproves its
favourite theory, or compare a variable against nothing.

Every later item in the roadmap reads this ledger:
- the debugging-skill rewrite (ri-03) writes `evidence-ledger.yaml`;
- the eliminative reviewer (ri-04) culls uncited claims from it;
- `collect-facts` (ri-05) fills it with provenance-bearing facts;
- the gap taxonomy (ri-10) links interventions to it;
- regression-scenario drafting reads its strongest signal.

Immutability of facts is a hard constraint of the method: the factual tier is gathered
evidence, and the derivative tier (hypotheses) must bend to it, never the reverse. That
constraint has to be enforced at the foundation, not left to each consumer.

## What Changes

- **New infrastructure skill `skills/evidence-ledger/`** (not user-invocable). It contains
  `SKILL.md`, which documents the ledger format, the immutability rule and the validator CLI.
- **New schema `evidence-ledger.schema.json`** (`schema_version: 1`, JSON Schema Draft
  2020-12). It is shipped by the skill under `install_assets/openspec/schemas/` and mirrored
  byte-identically at `openspec/schemas/evidence-ledger.schema.json`. It covers:
  - **facts**: `id`, `kind`, `source`, `gathered_by`, `host`, `time_window{start,end}`,
    `tool_version`, `role ∈ {variable, control}`, and `observation`;
  - **signals**: `id`, `variable_fact`, `control_fact`, `classification ∈ {signal, noise}`;
  - **hypotheses**: `id`, `statement`, `cites: [fact_id]`, optional `components`,
    `status ∈ {open, supported, rejected, root_cause}`;
  - **reverify_requests**: `id`, `fact_id`, `reason`, `requested_by`, optional
    `replacement_fact`.
- **New deterministic validator `skills/evidence-ledger/scripts/evidence_ledger.py`**. It loads
  YAML or JSON and reports violations in three layers:
  1. schema conformance;
  2. referential integrity:
     - ids are unique;
     - every signal names exactly one fact whose role is `variable` and exactly one whose role
       is `control`;
     - every citation resolves to a recorded fact;
     - every reverify target resolves to a recorded fact;
  3. a revision check against the previous ledger. A previously recorded fact or
     reverify_request may not be edited or removed. Appending facts and reverify_requests is
     allowed.

  It exposes a Python API (`load_ledger`, `validate_ledger`, `check_revision`) and a CLI
  (`validate <ledger> [--previous <ledger>] [--json]`).
- **Tests** in `skills/tests/evidence-ledger/`:
  - valid and invalid fixtures;
  - revision-pair fixtures;
  - a copy-drift test across the canonical, shipped and change-local schema copies. This test
    resolves the change directory with `change_dir()`.
- **Registry updates**:
  - `skills/install-manifest.json` (portable distribution);
  - `skills/pyproject.toml` `testpaths` (the module name is flat-name-unique);
  - the Infrastructure Skills list in `docs/guides/workflow.md`.

## Approaches Considered

### Approach A — Dedicated `evidence-ledger` infrastructure skill with schema + validator module (Recommended)

A new skill owns the schema (via `install_assets`, the same pattern as `audit-choices` and
`ownership-runtime`) and a single flat-name-unique validator module. Consumers import it or
shell out to its CLI.

- **Pros**
  - One owner for the format.
  - Ships to other repos through `install.sh` exactly like existing skill-owned schemas.
  - The flat module name avoids the known shadowing problem in the shared pytest session.
  - ri-02 extends the same module with the matrix and gates, without touching any consumer.
- **Cons**
  - Adds one more skill directory and registry rows.
  - Consumers in other skills must locate the module through the installed skill path.

### Approach B — Put the schema and validator inside `debugging-and-error-recovery`

Co-locate the ledger with its first writer, the debugging skill.

- **Pros**
  - No new skill.
  - Lives next to the code that writes ledgers.
- **Cons**
  - ri-04, ri-05 and ri-10 would depend on a skill that ri-03 is about to rewrite wholesale.
    Ownership would follow the wrong axis, and the rewrite would churn a foundation that other
    items pin.
  - Creates a file-overlap conflict between ri-01 and ri-03, which the roadmap DAG treats as
    independent writers.

### Approach C — Schema only, with immutability enforced by an append-only JSONL event log

Store facts as an append-only event stream and enforce immutability by construction instead
of by validation.

- **Pros**
  - Mutation is impossible rather than merely detected.
- **Cons**
  - Contradicts the roadmap's stated artifact, a single `evidence-ledger.yaml` per
    investigation that humans and reviewers read directly.
  - Needs a reducer for every consumer.
  - Still needs a validator for signals and citations.
  - Adds a storage format and gives up nothing it saves.

### Selected Approach

**Approach A.** It matches the repository's established pattern for skill-owned schemas. It
keeps the format independent of the skill that ri-03 will rewrite. It gives ri-02 a single
module to extend. Approach C's guarantee is reproduced by `check_revision`, which compares a
revision against the previous ledger. That is the same model git history gives any YAML file,
and it costs no new storage format.

## Non-Goals

These are deliberately deferred to ri-02, `add-hypothesis-fact-matrix-and-root-cause-gate-to-validator`:
- the hypothesis-by-fact matrix (✓/✗/?);
- per-signal hypothesis counts;
- all-✓ row detection;
- `root_cause` gates (uncited, contradicted);
- the multi-cause necessity check.

ri-01 defines the `root_cause` status value but does not gate it.

The following are also out of scope:
- writing ledgers (ri-03, ri-05);
- reviewer prompts (ri-04);
- any coordinator, database or runtime-service change.

## Verification Signals

**Not applicable — reason:** this change adds an offline, deterministic file validator and a
JSON Schema. It changes no runtime behaviour. There is no service, request path, RPC,
external call, database query or token-consuming step whose quantity could drift against a
baseline. Correctness is observed entirely through the validator's exit code (0 valid,
1 violations, 2 usage/load error) and its violation list, both of which are asserted by
fixture tests. The ledger's own signal entries are domain data that this change defines, not
runtime telemetry that it emits.

## Impact

- **Affected specs:** new capability `evidence-ledger`.
- **New files:**
  - `skills/evidence-ledger/**`
  - `openspec/schemas/evidence-ledger.schema.json`
  - `skills/tests/evidence-ledger/**`
- **Edited files:**
  - `skills/install-manifest.json`
  - `skills/pyproject.toml`
  - `docs/guides/workflow.md`
- **Dependencies:** none new. `jsonschema` and `PyYAML` are already in `skills/.venv`.

## Acceptance Outcomes

- The schema validates a fixture ledger containing variable and control facts, a derived
  signal, and a cited hypothesis.
- The validator rejects a ledger revision in which a previously recorded fact's fields were
  edited in place. It accepts the same dispute expressed as a reverify_request plus a new
  fact.
- Signals are classified as signal or noise, and each references exactly one variable fact
  and one control fact.
- Validator tests live under `skills/tests/` and resolve any OpenSpec paths via
  `change_dir()`.
