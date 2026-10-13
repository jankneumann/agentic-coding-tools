# Add gap taxonomy and ledger links to intervention records

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-gap-taxonomy-and-ledger-links-to-intervention-records`
> Effort: S
> Priority: 3

## Summary

Extend intervention-capture records with a required gap category from the closed vocabulary (missing_control, missing_constraint, missing_citation, missing_data_source, wrong_layer, policy_decision, other) and a link to the evidence ledger of the investigation the intervention corrected.

## Dependencies

- `ri-03`

## Acceptance Outcomes

- An intervention record without a gap category from the vocabulary fails validation.
- An intervention recorded during a debugging session stores a resolvable reference to that session's evidence ledger.

## Rationale

Treating each human intervention as missing infrastructure requires categorizing it and tying it to the investigation it fixed. This extends intervention-capture rather than replacing it.
