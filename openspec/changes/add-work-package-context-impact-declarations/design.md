# Design: Work-package context impact declarations

## Context

`work-packages.yaml` is already the reviewed execution contract for scope,
dependencies, locks, and verification. Adding a separate context file would create
another artifact that can drift. The package contract is therefore the correct
place to state expected context effects.

Changed-file inference is useful evidence but cannot prove no impact. The design
combines an authored declaration with deterministic checks and a reviewable escape
hatch.

## Decisions

### D1: One declaration object with six stable surface keys

When `context_impact` is present, it contains:

```yaml
context_impact:
  capabilities: {disposition: refresh, targets: [project-context-refresh]}
  apis: {disposition: no-impact}
  architecture: {disposition: refresh, targets: [skills]}
  decisions: {disposition: refresh}
  documentation: {disposition: refresh, targets: [docs/guides/workflow.md]}
  semantic_code: {disposition: refresh}
```

The fixed keys make review omissions visible and avoid ambiguous free-form labels.
`targets` are repository-relative paths or stable domain identifiers and are
sorted/unique.

### D2: Three dispositions, with fail-closed unknown

- `refresh`: the package expects this surface to change or be rechecked.
- `no-impact`: the package asserts no change.
- `unknown`: planning has not resolved the effect.

Strict validation rejects `unknown`. `no-impact` is valid without an exception
when inference finds no evidence. When inference does find evidence, an exception
is required:

```yaml
exception:
  rationale: "Fixture-only API payload; no public contract changes"
  approved_by: "github:jankneumann"
  approved_at: "2026-07-23T00:00:00Z"
```

The validator verifies structure and presence, not the reviewer's identity.

### D3: Inference is deterministic and versioned

The inference module accepts explicit changed paths plus the parsed work-package
contract. It does not choose a Git base. Rules include:

- OpenSpec delta/spec paths imply capabilities;
- OpenAPI, GraphQL, schema, contracts, generated bindings, and `api:`/`contract:`
  lock keys imply APIs;
- architecture-analysis, architecture guides, component boundaries, dependency
  manifests, and refresh-architecture code imply architecture;
- session logs, ADRs, and decision indexes imply decisions;
- user/contributor docs, README, AGENTS/CLAUDE, and skill narrative imply
  documentation;
- source/test/config changes within the package write scope imply semantic code.

Every inference includes rule ID and evidence path/key. Rule set version is
included in normalized output.

### D4: Migration is warning-first and strict on demand

The schema keeps `context_impact` optional so active changes remain readable.
Default validation returns `legacy-unclassified` per missing package.
`--require-context-impact` upgrades it to `CONTEXT_IMPACT_MISSING`. Templates emit
the new shape immediately. Consumers that rely on the metadata, beginning with
branch checkpoints, must use strict mode.

### D5: Existing scope is authoritative

No duplicate semantic scope is added. Normalized output copies
`scope.read_allow` and `scope.deny`; consumers calculate effective permission as
allow minus deny. Missing `deny` normalizes to an empty list. Write scope is
evidence for impact inference but never grants read access.

## Alternatives rejected

- Pure inference: cannot represent a deliberate no-impact decision.
- Free-form impact labels: impossible to validate or consume reliably.
- Making the field immediately required in the schema: breaks all active and
  archived v1 plans with no staged migration.
- LLM classification: nondeterministic and cannot serve as a merge gate.

## Test strategy

JSON Schema tests freeze the contract. Table-driven unit tests freeze inference
rules and evidence. CLI tests cover default/strict migration modes and atomic
output. Integration fixtures validate canonical and installed schema parity.
