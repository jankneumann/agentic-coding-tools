# vendor-ux — delta for add-atomic-harness

Surfaces experimental-vendor status wherever vendors are listed or selected, so an
operator can always tell a trial vendor from a first-class one.

## ADDED Requirements

### Requirement: Experimental Vendor Identification

Vendor-facing surfaces (vendor listings, health/readiness output, `/quick-task` vendor
selection feedback, and the kanban vendor visualization) SHALL identify experimental
vendors with an explicit experimental marker wherever vendor names are shown.
Experimental vendors SHALL be selectable through the same flags and pickers as
first-class vendors; selection SHALL NOT be blocked, only labeled.

#### Scenario: Health output labels experimental vendor

- **GIVEN** `atomic-local` is declared with `experimental: true` and its binary is present
- **WHEN** vendor health/readiness is reported
- **THEN** the `atomic-local` row SHALL carry an experimental marker alongside the standard health dimensions
- **AND** first-class vendor rows SHALL be unchanged

#### Scenario: Quick task accepts experimental vendor with label

- **GIVEN** the user invokes `/quick-task --vendor atomic-local "list files"`
- **WHEN** the task is dispatched
- **THEN** only the `atomic-local` vendor SHALL be used
- **AND** the dispatch feedback SHALL note the vendor is experimental

#### Scenario: Missing experimental vendor fails soft in listings

- **GIVEN** `atomic-local` is declared but its binary is not on PATH
- **WHEN** vendors are listed
- **THEN** the listing SHALL either omit `atomic-local` or show it unavailable with the experimental marker
- **AND** the absence SHALL NOT block listing or dispatch of other vendors
