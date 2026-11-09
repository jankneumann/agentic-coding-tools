# Rewrite debugging-and-error-recovery around the two-tier method

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `rewrite-debugging-skill-around-evidence-ledger`
> Effort: L
> Priority: 2

## Summary

Rewrite the skill so its default flow is: gather facts cheapest layer first, establish a control, separate signal from noise, rank signals by hypotheses admitted, and validate the leading hypothesis against every fact. Add the five refinement tactics, progressive signal discovery, and a reproduction-parity gate. Keep pytest/bisect as tools inside the flow, and write an evidence-ledger.yaml per investigation.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- Running the skill on a seeded bug produces a schema-valid evidence ledger with at least one control fact and a computed matrix.
- A behavioural skill test under skills/tests/debugging-and-error-recovery/ fails if the skill proposes a root cause before recording at least one control fact.
- A reproduction that does not reproduce the recorded strongest signal is marked rejected in the ledger and is never cited as evidence.
- The skill text orders code reading after fact gathering and control establishment, and descends a layer only when every current signal is weak.

## Rationale

The skill still teaches the human-first reproduce-localize-reduce-fix order that produced the plausible-but-wrong diagnoses in the motivating essay. It is the primary consumer of the ledger and the place where controls and citations become the default.
