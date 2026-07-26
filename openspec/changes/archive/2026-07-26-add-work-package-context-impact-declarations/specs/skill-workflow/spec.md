## ADDED Requirements

### Requirement: Work Package Context Impact Declaration

A work package SHALL be able to declare, in an optional `context_impact` block,
which derived project-context surfaces it may affect. The declaration SHALL name
zero or more of the six canonical surfaces `capabilities`, `apis`,
`architecture`, `decisions`, `documentation`, and `semantic_code`, each of which
SHALL correspond to the producer or skill that canonically owns it.

<!-- Scenario ID: skill-workflow.context-impact-schema -->
#### Scenario: Schema accepts a context impact declaration

- **WHEN** a `work-packages.yaml` declares `context_impact.surfaces` on a package
- **THEN** `work-packages.schema.json` SHALL validate the document
- **AND** SHALL reject any surface name outside the six canonical surfaces
- **AND** SHALL require `surfaces` whenever the `context_impact` block is present

<!-- Scenario ID: skill-workflow.context-impact-optional -->
#### Scenario: Existing work packages remain valid

- **WHEN** a `work-packages.yaml` omits `context_impact` on every package
- **THEN** the schema SHALL validate the document unchanged
- **AND** no existing required field SHALL gain or lose a constraint

### Requirement: Undeclared Context Impact Detection

The system SHALL infer the context surfaces a work package affects from its
changed files and the change's declared contract files, independently of what the
package declared. Inference SHALL use a reviewable glob rule table, SHALL
consider only changed files matching the package's `scope.write_allow`, and SHALL
NOT depend on file modification times.

<!-- Scenario ID: skill-workflow.context-impact-inference -->
#### Scenario: Changed files imply surfaces

- **WHEN** the detector is given a package's `scope.write_allow` and the branch's
  changed files
- **THEN** it SHALL return the set of surfaces implied by the matching files
- **AND** SHALL exclude changed files that fall outside `scope.write_allow`
- **AND** SHALL imply `apis` when a changed file is listed in
  `contracts.openapi.files`

<!-- Scenario ID: skill-workflow.context-impact-rule-integrity -->
#### Scenario: Rule table integrity is enforced

- **WHEN** the rule table is loaded
- **THEN** loading SHALL fail when a rule names a surface outside the six
  canonical surfaces
- **AND** SHALL fail when the rule file is missing rather than infer an empty
  rule set

### Requirement: Context Impact Validation Gate

Validation SHALL fail when a work package that declares a `context_impact` block
omits a surface the detector implies, unless an approved rationale is recorded for
that surface. A rationale SHALL carry a non-empty reason and a non-empty
`approved_by` attribution.

<!-- Scenario ID: skill-workflow.context-impact-undeclared -->
#### Scenario: Undeclared implied surface fails validation

- **WHEN** a package declares `context_impact` and the detector implies a surface
  absent from `surfaces` with no rationale for it
- **THEN** the gate SHALL report that package as `undeclared`, naming the surface
  and the changed files that implied it
- **AND** SHALL exit non-zero

<!-- Scenario ID: skill-workflow.context-impact-rationale -->
#### Scenario: Approved rationale permits omission

- **WHEN** a package records a rationale with a non-empty `approved_by` for an
  implied but undeclared surface
- **THEN** the gate SHALL report that surface as `rationalized` and SHALL exit
  zero
- **AND** SHALL report a rationale for a surface the detector does not imply as
  `spurious_rationale` and exit non-zero

<!-- Scenario ID: skill-workflow.context-impact-empty-declaration -->
#### Scenario: An empty surface list is a strict assertion

- **WHEN** a package declares `context_impact.surfaces` as an empty list
- **THEN** the gate SHALL treat any implied surface as `undeclared`
- **AND** SHALL NOT treat the package as unmigrated

### Requirement: Context Impact Migration Compatibility

A work package that omits `context_impact` entirely SHALL receive an explicit
`unmigrated` compatibility result rather than a failure. The result SHALL name
the surfaces the detector inferred so the declaration can be adopted mechanically,
and a `--strict-legacy` mode SHALL promote `unmigrated` to a failure.

<!-- Scenario ID: skill-workflow.context-impact-unmigrated -->
#### Scenario: Legacy package reports a compatibility result

- **WHEN** a package without a `context_impact` block has implied surfaces
- **THEN** the gate SHALL report it as `unmigrated` with the inferred surface list
- **AND** SHALL exit zero in the default mode
- **AND** SHALL exit non-zero when `--strict-legacy` is requested

### Requirement: Declared Package Scopes Available To Context Consumers

The system SHALL expose each work package's resolved read scope so downstream
semantic indexing and context injection query the planner's declared boundaries
rather than re-deriving them. Resolution SHALL return the package's
`scope.read_allow` and `scope.deny` globs, with `deny` taking precedence.

<!-- Scenario ID: skill-workflow.context-impact-index-scopes -->
#### Scenario: Resolved scopes are queryable

- **WHEN** a caller resolves the index scopes for a work package
- **THEN** the result SHALL contain the package's `read_allow` and `deny` globs
- **AND** a path matching both SHALL resolve as denied
- **AND** resolution SHALL NOT introduce a second copy of the globs in the schema
