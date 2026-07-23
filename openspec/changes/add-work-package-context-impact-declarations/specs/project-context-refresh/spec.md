## ADDED Requirements

### Requirement: Work packages declare context impact

The work-package contract SHALL support a `context_impact` declaration with
exactly six surface keys: `capabilities`, `apis`, `architecture`, `decisions`,
`documentation`, and `semantic_code`. Each surface SHALL declare one disposition
of `refresh`, `no-impact`, or `unknown`, and MAY provide unique targets.

#### Scenario: Complete context declaration validates

- **WHEN** a work package declares all six surface keys with valid dispositions
- **THEN** schema validation SHALL accept the declaration
- **AND** SHALL reject unknown surface keys, unknown properties, duplicate targets,
  or invalid dispositions

#### Scenario: Planning uncertainty is explicit

- **WHEN** the effect on one surface has not been resolved during planning
- **THEN** the package SHALL declare that surface as `unknown`
- **AND** strict context-impact validation SHALL fail with
  `CONTEXT_IMPACT_UNKNOWN`

### Requirement: Deterministic inference detects undeclared impact

The package validator SHALL infer context impacts from caller-supplied changed
files, declared contract files, and logical lock keys using a versioned,
deterministic rule set. Each inferred impact SHALL identify its rule and evidence.

#### Scenario: Contract change implies API impact

- **WHEN** a changed path is a declared OpenAPI, GraphQL, JSON Schema, generated
  binding, or other contract file
- **THEN** validation SHALL infer an API impact
- **AND** SHALL fail with `CONTEXT_IMPACT_UNDECLARED` if the package neither
  declares API refresh nor supplies a valid reviewed no-impact exception

#### Scenario: One path implies multiple surfaces

- **WHEN** a changed path matches rules for more than one context surface
- **THEN** every matching surface SHALL be reported with independent evidence
- **AND** output ordering SHALL be deterministic

### Requirement: No-impact exceptions are reviewable

The validator SHALL require an exception containing a non-empty rationale,
reviewer identifier, and RFC 3339 review timestamp when deterministic evidence
conflicts with a `no-impact` declaration.

#### Scenario: Reviewed exception permits deliberate no-impact

- **WHEN** inference identifies an API impact
- **AND** the API declaration is `no-impact`
- **AND** a complete exception records why the evidence does not change an API,
  who approved it, and when
- **THEN** validation SHALL accept the declaration
- **AND** normalized output SHALL retain the inference evidence and exception

#### Scenario: Unreviewed rationale fails

- **WHEN** an inferred impact is declared `no-impact` with a missing or incomplete
  exception
- **THEN** validation SHALL fail with
  `CONTEXT_IMPACT_EXCEPTION_INVALID`

### Requirement: Legacy work packages have an explicit migration result

The schema SHALL remain backward compatible with packages that omit
`context_impact`. Default validation SHALL identify each such package as
`legacy-unclassified`, while `--require-context-impact` SHALL reject it.

#### Scenario: Legacy plan in compatibility mode

- **WHEN** a valid existing work-package file omits `context_impact`
- **THEN** default validation SHALL preserve its existing validity
- **AND** SHALL emit a machine-readable `legacy-unclassified` warning

#### Scenario: Strict consumer rejects missing declarations

- **WHEN** the same file is validated with `--require-context-impact`
- **THEN** validation SHALL fail with `CONTEXT_IMPACT_MISSING`

### Requirement: Context handoff preserves package read boundaries

The validator SHALL be able to emit normalized context-impact JSON containing the
package ID, declarations, inference evidence, exceptions, rule-set version,
`scope.read_allow`, and `scope.deny`.

#### Scenario: Deny scope remains authoritative

- **WHEN** a package read-allow glob overlaps a deny glob
- **THEN** normalized output SHALL preserve both declarations
- **AND** SHALL identify effective read scope as read-allow minus deny
- **AND** no downstream handoff SHALL interpret context metadata as permission to
  read a denied path
