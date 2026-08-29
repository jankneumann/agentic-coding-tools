# Require roadmap scaffolds to validate

> Parent roadmap: `skill-rightsizing`
> Change ID: `require-validating-roadmap-scaffolds`

## Why

`roadmap-orchestration` requires `plan-roadmap` to seed OpenSpec change scaffolds
from approved candidates, but says nothing about those scaffolds being valid.
The scaffolder honoured the letter of the requirement and created `specs/` as an
empty directory, writing no delta into it. `openspec validate --strict` rejects a
change with no delta carrying a `#### Scenario:` block, and Git does not track
empty directories, so scaffolded changes reached CI with no `specs/` at all and
failed `validate-specs` — observed on #343, where three scaffolded items failed
that gate.

The requirement is not stale text to remove. It encodes the intended model:
every roadmap item carries a preliminary OpenSpec setup from roadmap-creation
time, refined per item by `/plan-feature` once its dependencies have landed.
What is missing is the obligation that the seeded scaffold actually validates.

## What Changes

- Strengthen the "Seed OpenSpec change scaffolds" scenario to require that each
  created change passes `openspec validate --strict`.
- Add a scenario requiring the seeded spec delta to be derived from the item's
  acceptance outcomes, so the sketch carries the item's intent rather than a
  placeholder.
