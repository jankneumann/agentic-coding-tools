# Add decision-point policy playbook schema and capture

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-decision-point-policy-playbook-schema-and-capture`
> Effort: M
> Priority: 6

## Summary

Define a playbook schema for policy entries (trigger condition, decision, rationale, author, scope) and, when a human resolves a judgment-call escalation, offer to save the resolution as a policy entry. Builds on owner-routed-escalation and its existing storage.

## Dependencies

- None

## Acceptance Outcomes

- Resolving an escalation offers to save a policy entry, which validates against the playbook schema.
- A policy entry missing a trigger condition, author, or scope fails validation.

## Rationale

Recurring judgment calls such as roll back vs fix forward or accepting a signal regression are a top source of human interventions. Recording them as policy is the first step to resolving them without a human.
