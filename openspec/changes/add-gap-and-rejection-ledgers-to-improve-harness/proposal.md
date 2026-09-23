# Add persistent gap ledger and edit-keyed rejection ledger to improve-harness

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `add-gap-and-rejection-ledgers-to-improve-harness`
> Effort: L
> Priority: 3

## Summary

Add a gap ledger that records sightings per gap and session across runs, graduates gaps at a corroboration floor counted in distinct changes or distinct interactive sessions, retires gaps when covered by an instruction or skill description, and expires them after 90 days; and a rejection ledger keyed on edit content that suppresses a rejected edit until strictly more evidence backs it. Report the interactive versus non-interactive split.

## Dependencies

- `ri-01`
- `ri-06`
- `ri-10`

## Acceptance Outcomes

- A gap seen in one interactive session and three autopilot sessions of the same change does not graduate; the same gap seen in two distinct changes does (asserted by test).
- A gap whose text is covered by a newly added instruction unit is retired on the next run, and a gap unseen for 90 days is expired.
- A rejected edit key is not re-proposed on a rerun with identical evidence and is re-proposed when one additional qualifying session backs it.
- The report prints relevance per instruction id split by interactive and non-interactive sessions.

## Rationale

Adopt items 5 and 6 and adapt item 2 in section 4. The corroboration floor is currently advisory; a robot-heavy corpus clears a raw two-session floor trivially, so the unit must be changes or interactive sessions. If the spike chose backpass as engine this reads .backpass/gap-ledger.json and state; if port, it is the Python implementation.
