# Design: Add work-package context impact declarations

## Context

`work-packages.schema.json` is a closed schema (`additionalProperties: false` at
every level), validated by `skills/validate-packages/scripts/validate_work_packages.py`
and consumed by `/parallel-implement-feature` before dispatch. It is tracked in
two places that must stay byte-identical:

- `skills/validate-packages/install_assets/openspec/schemas/work-packages.schema.json` — canonical source
- `openspec/schemas/work-packages.schema.json` — `install.sh` output, already
  covered by `skills/tests/install_sh/test_openspec_assets.py::test_canonical_install_syncs_required_openspec_schemas`

ri-05 registered four deterministic producers (`documentation.inventory`,
`api.contracts`, `decisions.timeline`, `openspec.projection`); ri-04 owns the
architecture refresh; ri-01/ri-02 own the semantic index. Those six are exactly
the context surfaces this change asks a package to declare.

## Decisions

### D1 — The declaration is a hint; changed-file + contract analysis is the detector

A planner that omits `context_impact` entirely must not be able to slip past the
gate. So the gate never trusts the declaration as evidence of *completeness* — it
only ever uses it as a claim to be contradicted. The authoritative signal is the
package's changed files (intersected with `scope.write_allow`) plus the change's
declared contract files. This is what the roadmap proposal specifies
("changed-file and contract analysis must catch undeclared impacts") and it is
the reason the field can stay optional without weakening the gate.

### D2 — Impact rules live in a reviewable YAML table, not in Python

`context-impact-rules.yaml` maps globs to surfaces. Reviewability is the whole
point of this change; a rule table that a reviewer can read in a diff beats a
buried `if path.startswith(...)` chain. It also matches the repo convention that
thresholds and routing tables live in YAML (see `archetypes.yaml`, the
escalation thresholds). The loader validates that every rule names a known
surface, so a typo fails loudly rather than silently matching nothing.

### D3 — Progressive enforcement: strict for declared packages, compatibility result for legacy

The two acceptance outcomes pull in opposite directions — one demands failure on
undeclared impact, the other demands that existing packages get "a clear
migration or compatibility result." A single mode cannot satisfy both, because
every package in the repo today lacks the field.

Resolution: enforcement keys off **whether the block is present**.

| Package state | Implied surface not declared | Result |
|---|---|---|
| has `context_impact` | no rationale | `undeclared` → **exit 1** |
| has `context_impact` | rationale with `approved_by` | `rationalized` → pass |
| has `context_impact` | nothing implied | `declared` → pass |
| no `context_impact` | anything implied | `unmigrated` → pass, report inferred surfaces |
| no `context_impact` | nothing implied | `unmigrated` → pass |

`--strict-legacy` promotes `unmigrated` to a failure, so the repo can flip to
full enforcement in one flag once packages are migrated. Declaring the block is
therefore opt-in but one-way: once you declare, you must be complete.

`unmigrated` reports the *inferred* surface list, which makes the migration
mechanical — a planner can paste the reported list into the package.

### D4 — An empty `surfaces: []` is a real assertion, not a missing value

`context_impact: {surfaces: []}` means "this package affects no context surface"
and is checked strictly: anything the detector implies becomes `undeclared`. This
is what distinguishes a deliberate no-impact claim from a legacy package, and it
is why `surfaces` is `required` once the block exists.

### D5 — Rationale requires a named approver

`rationale.<surface>.reason` alone would let a package silence the gate with
prose. `approved_by` must be a non-empty string, making the override attributable
in review and greppable across changes. A rationale for a surface that is *not*
implied is a validation error, so rationales cannot be pre-sprinkled to blanket
future impact.

### D6 — Detection is git-free at the library layer

`context_impact.py` takes `changed_files: Sequence[str]` and never shells out.
The CLI resolves them via `git diff --name-only <base>...HEAD`. This keeps the
library unit-testable on fixtures with no repository, mirroring how
`validate_work_packages.py` stays git-free, and lets ri-09 reuse the detector
with a checkpoint's own file list instead of a git range.

### D7 — The gate is a separate CLI, not folded into `validate_work_packages.py`

`validate_work_packages.py` validates a file in isolation and is called on
fixtures with no git context. Adding a git-dependent check to it would break that
contract. `validate_context_impact.py` is a sibling that imports the same loader,
so `/implement-feature` runs both and each keeps a single responsibility.

### D8 — `index_scopes()` resolves, it does not add fields

The acceptance outcome asks that declared `read_allow` / `deny` be "available to
downstream indexing queries". Those globs already exist on `scope`. Adding a
parallel copy under `context_impact` would create two sources of truth that drift.
Instead `index_scopes(package)` returns the resolved `{read_allow, deny}` pair
that ri-12 and the semantic indexer consume, with `deny` taking precedence.

### D9 — Compatibility is proven by "no new `context_impact` error", not by "everything validates"

Measured on `3b74b74e`: **24 of 62** `work-packages.yaml` files under
`openspec/changes/**` already fail `validate_work_packages.py`, including
ri-07's own. The recurring baseline violations are a missing top-level
`contracts` block, a missing `outputs` on packages, a missing
`verification.steps[].evidence`, and `impl:` lock keys outside the schema's
`^(api|db|event|flag|env|contract|feature):` namespace.

A compatibility test asserting "every work-packages.yaml validates" would
therefore fail on an unmodified tree for reasons this change did not cause — a
gate that cannot pass proves nothing about the schema edit. The passable and
honest formulation is: **no file gains a schema error mentioning
`context_impact`**. That isolates the constraint this change actually
introduces, and it stays meaningful after the pre-existing debt is repaired.

The baseline debt itself is out of scope — it predates ri-08 and spans archived
changes. It is filed as a follow-up rather than repaired here, because touching
24 archived planning artifacts would swamp the diff this change is reviewed on.

## Failure Behavior

- Unknown surface in a declaration → schema violation, exit 1.
- Unknown surface in the rule table → loader error naming the rule, exit 1.
- Rationale for a non-implied surface → `spurious_rationale`, exit 1.
- Rationale without `approved_by` → schema violation (`minLength: 1`), exit 1.
- Missing rule file → loader error; the gate never silently passes by matching
  zero rules.
- No changed files (empty diff) → every package reports `declared` or
  `unmigrated` with an empty implied set; exit 0.

## Test Strategy

Every gate must fail against the unmodified tree before the fix lands:

- Schema tests: `context_impact` accepted; unknown surface rejected; `surfaces`
  required when the block is present; `approved_by` empty string rejected. These
  fail on today's closed schema with `additionalProperties` errors.
- Detector tests on fixtures: each of the six surfaces inferred from a
  representative path; `scope.write_allow` intersection honored; contract files
  imply `apis`.
- Enforcement matrix: one test per row of the D3 table, plus `--strict-legacy`.
- Rule-table integrity: every surface in `SURFACES` has at least one rule, and
  every rule's surface is in `SURFACES`.
- Compatibility: every `work-packages.yaml` currently in `openspec/changes/**`
  still validates against the updated schema.
