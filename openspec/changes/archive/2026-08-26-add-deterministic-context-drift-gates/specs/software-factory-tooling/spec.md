# software-factory-tooling — delta

## ADDED Requirements

### Requirement: Decision index rendering is path-independent

The decision index emitter SHALL produce byte-identical output regardless of whether it is
given a relative or an absolute archive root, and SHALL render every back-reference link
relative to the repository root.

Embedding the supplied archive root into rendered output makes the emitter's result depend
on the caller's path conventions. Because the emitter's output is a committed artifact,
that turns a caller detail into repository content: invoking it with an absolute root
writes machine-specific absolute paths into the committed index, and any freshness check
comparing rendered output against the committed tree reports drift that does not exist.

A drift check over a temporary-directory render SHALL be verified to produce an identical
report for relative and absolute repository paths, so that a renderer whose output depends
on its input paths is detected rather than silently reported as staleness.

#### Scenario: Rendered links do not embed the archive root
- **GIVEN** an emitter invoked with an absolute archive root
- **WHEN** the decision index is rendered
- **THEN** every back-reference link SHALL be repository-relative
- **AND** no rendered file SHALL contain the absolute archive root

#### Scenario: Relative and absolute roots render identically
- **GIVEN** the same repository state
- **WHEN** the index is rendered once with a relative archive root and once with an absolute one
- **THEN** the two rendered trees SHALL be byte-identical

#### Scenario: Path dependence is detected as a defect, not as staleness
- **GIVEN** a producer that compares a temporary-directory render against the committed tree
- **WHEN** its report is computed for a relative and for an absolute repository path
- **THEN** the two reports SHALL list the same artifacts
- **AND** a difference between them SHALL fail as a producer defect
