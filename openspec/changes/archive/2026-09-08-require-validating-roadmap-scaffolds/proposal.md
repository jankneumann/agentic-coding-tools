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

## Archive Note — superseded before archival (2026-09-08)

Archived with `--skip-specs`. Its `MODIFIED` delta was **not** applied, and that
is deliberate: `scaffold-validating-roadmap-changes` (archived
`2026-09-02-scaffold-validating-roadmap-changes`) landed the same intent first,
in a stronger form. The delta's copy of `Requirement: Proposal Decomposition into
Roadmap Changes` carries 2 scenarios; the requirement now on `main` carries 13.
A `MODIFIED` block replaces the whole requirement, so applying this delta would
have deleted 11 scenarios — the 2026-09-08 archive sweep stopped here for exactly
that reason.

Every assertion in this delta is already on `main`, verified clause by clause:

| This delta asserts | Covered on `main` by |
|---|---|
| draft change dirs created for approved candidates | `Seed OpenSpec change scaffolds from approved candidates` |
| proposal scaffold carries `parent_roadmap` | same scenario |
| each created change passes `openspec validate --strict` | `Scaffolded changes are valid OpenSpec changes` |
| delta under `specs/` declaring ≥1 requirement | `Scaffolded changes are valid OpenSpec changes` |
| each acceptance outcome appears as a `#### Scenario:` | `Spec deltas are derived from acceptance outcomes` |
| delta marked as a preliminary sketch | `Scaffolded artifacts declare themselves preliminary` |

`main` additionally requires the delta to survive being committed rather than
relying on an untracked empty directory — the concrete failure (#343) that
motivated this proposal. Nothing is lost by not applying the delta; something
would have been lost by applying it.

