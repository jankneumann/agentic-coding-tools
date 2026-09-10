# harness-engineering — delta for restructure-documentation-layers

Completes the *Progressive Context Architecture* requirement on the human-reader side: the
hand-authored documentation is organised into three layers with one map, every hand-authored
doc declares its layer and sources, and generated inventories replace hand-maintained
catalogues.

## ADDED Requirements

### Requirement: Layered Documentation Map

Hand-authored documentation SHALL be organised into three layers: Layer 0 (entry points: `README.md`, `CLAUDE.md`, `VISION.md`), Layer 1 (one concept per guide under `docs/guides/`), and Layer 2 (formal specifications, generated artifacts, and dated runbooks). Exactly one file, `docs/guides/documentation.md`, SHALL serve as the map that lists every hand-authored documentation file under its layer.

Every Layer 0 and Layer 1 document SHALL declare document metadata with the fields `layer`, `owns`, `sources`, and `verified_against`. Layer 1 documents SHALL carry the metadata as YAML frontmatter; Layer 0 documents SHALL carry it in a leading HTML comment so that no metadata table renders above the project's front page.

`README.md` SHALL fit one screen (at most 80 lines), SHALL introduce each concept with a link to the Layer 1 guide that owns it, and SHALL NOT restate inventories (skill counts, spec counts, skill tables) that a generated artifact already provides.

Skill inventories SHALL be provided only by the generated `docs/architecture-analysis/skills-inventory.md`; a hand-maintained skills catalogue SHALL NOT exist. Hand-written orientation prose for the inventory SHALL live outside the generated marker region of that file.

#### Scenario: Newcomer reaches every guide in one click

- **WHEN** a reader opens `README.md`
- **THEN** every Layer 1 guide SHALL be reachable through a single relative link from `README.md` or from the map it links
- **AND** every Layer 1 guide SHALL contain a relative link back to `docs/guides/documentation.md`

#### Scenario: Hand-authored doc missing from the map

- **WHEN** a markdown file exists under `docs/` or `docs/guides/` that is neither generated nor a per-run log
- **AND** the map does not list it
- **THEN** the documentation structure test SHALL fail and name the unlisted file

#### Scenario: Document metadata is complete

- **WHEN** the documentation structure test parses a Layer 0 or Layer 1 document
- **THEN** the metadata SHALL parse and SHALL contain `layer`, `owns`, `sources`, and `verified_against`
- **AND** every path listed in `sources` SHALL exist in the repository

#### Scenario: Document metadata is missing or malformed

- **WHEN** a Layer 1 guide has no frontmatter, or its frontmatter lacks a required field
- **THEN** the documentation structure test SHALL fail and name the document and the missing field

#### Scenario: README carries no inventory claims

- **WHEN** `README.md` is checked
- **THEN** it SHALL contain at most 80 lines
- **AND** it SHALL NOT contain a numeric count of skills or specifications
- **AND** every `/skill-name` mention SHALL resolve to `skills/<skill-name>/SKILL.md`

#### Scenario: Hand-maintained catalogue reintroduced

- **WHEN** a file named `docs/skills-catalogue.md` exists
- **THEN** the documentation structure test SHALL fail with a message pointing to the generated inventory

#### Scenario: Inventory preface survives regeneration

- **WHEN** `make context-refresh` regenerates `docs/architecture-analysis/skills-inventory.md`
- **THEN** the hand-written preface outside the generated markers SHALL be byte-identical before and after
- **AND** `make context-refresh-check` SHALL report the producer as fresh
