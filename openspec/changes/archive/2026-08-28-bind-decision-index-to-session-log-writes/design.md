# Design — bind the decision index to session-log writes

## Context

`write_both()` is a best-effort persistence sequence whose own docstrings describe a coupling
it does not perform. This change adds the missing step. The whole change is one function's
worth of code; the design work is in the failure semantics and in what must *not* move.

## D1 — Regeneration is a fourth step in `write_both()`, not a caller responsibility

**Decision.** Step four runs inside `write_both()`, after the coordinator step.

**Why.** The defect is that regeneration lives somewhere a caller must remember. Moving it to
seven callers relocates the defect and adds seven future skills that must remember. It goes
where the invalidation is created.

**Why after the coordinator step, not before.** Steps one to three persist the record; step
four derives from what step one wrote. Running it earlier would regenerate from a session log
that does not yet contain this entry — producing a confidently wrong index rather than a
stale one, which is worse.

**Rejected**: a git pre-commit hook. It also catches hand-edits, which this does not, but it
is absent in CI, in cloud harnesses, and in a fresh clone. Convention-only enforcement is
what produced issue #157.

## D2 — Always on, with no flag

**Decision.** No parameter, no environment variable, no opt-out.

**Why.** Measured cost is 0.06s across 168 changes producing 25 index files, so there is no
performance argument for a switch. And this repository has a fresh, specific lesson about
off-by-default correctness work: `rescope-context-drift-enforcement` shipped a `context_gate`
telemetry emitter that was correct, tested, and **unreachable**, because the only thing that
could enable it was an environment variable nobody was assigned to set. It took two follow-up
rounds to wire. A flag here would recreate that shape for a step whose entire purpose is to
happen every time.

**On Rule 4 (safe defaults).** Rule 4 exists so a new option does not silently change
behaviour for existing callers. Here the changed behaviour *is* the fix, it is confined to a
derived artifact the system already claims to own, and no caller's inputs, outputs, or
`PhaseWriteResult` fields change. The rule is satisfied in substance: nothing an existing
caller depends on moves.

## D3 — Best-effort, and the session log outranks the index

**Decision.** Step four catches broadly, warns to stderr, appends to `warnings`, and never
raises — matching the three steps beside it.

**Why the ordering matters under failure.** By the time step four runs, the markdown is on
disk and the handoff has been attempted. A regeneration that raised would lose neither, but it
would surface as an exception from a method documented never to raise, breaking every caller
that treats `write_both()` as infallible. The session log is the durable record of a phase; a
stale index is a reported, one-command-fixable condition. The precedence is not close.

## D4 — Orchestrator-scoping becomes enforced, not assumed

**Decision.** A test asserts that no work-package worker path invokes `write_both()`.

**Why.** Step four writes `docs/decisions/`, outside every package's `write_allow`. Verified
at planning time: all seven call sites are orchestrator phase-boundary steps, so the conflict
is latent rather than actual. But it is latent by convention, and this session produced three
separate defects of exactly this shape — a schema copy no package could write, a telemetry
variable nobody was assigned to set, and a manifest declaration outside scope. Each was
individually invisible because no check tied the declaration to the reality. This one gets a
check.

**Rejected**: widening `write_allow` to include `docs/decisions/**` for packages that write
session logs. It would let two parallel packages write the same derived path and weaken the
non-overlapping-scope rule that makes the parallel tier safe.

**Rejected**: exempting derived paths from `scope_checker.py`. The scope checker caught three
real defects this session; a blanket exemption is easy to add and hard to narrow later.

## D5 — The gate keeps checking

**Decision.** No change to the `decisions.timeline` producer, its registry entry, or its
blocking classification.

**Why.** This removes one cause. A hand-edited session log, a manual archive move, and any
future writer that bypasses `PhaseRecord` all still stale the index, and all must still be
caught. The measured six firings were one cause with one fix; that is an argument for closing
the cause, never for lowering the check that found it.

## Note on the "and" splitting heuristic

Three task titles contain "and" and are deliberately not split, because each is a single
outcome with two assertions rather than two outcomes:

- **1.1** — "matches a fresh regeneration, **and** a second produces no further change" is one
  property, idempotent currency, and asserting only the first half would pass for a generator
  that runs twice and disagrees with itself.
- **1.5** — one edit to one docstring; "3-step to 4-step" and "name the fourth step" describe
  the same sentence.
- **1.7** — one scenario: a hand-edited log must be reported **and** must still block. Split,
  the second half is the one that would quietly go unwritten, and it is the guard against this
  change becoming a way to stop checking.

## Migration

Single step, no ordering constraints, no data migration. The first `write_both()` after this
lands regenerates the index as a side effect; if it was already current, the regeneration is a
no-op and the tree is untouched.

## Rollback

Revert one commit. The three prior steps are unmodified, `PhaseWriteResult` keeps its fields,
and no caller changed — so reverting restores today's behaviour exactly, including the drift.

## Risks

| Risk | Mitigation |
|---|---|
| `phase_record.py` gains a dependency on the index generator | Resolved lazily at call time, not at module import; absence is a warning and a skipped step, pinned by a scenario |
| A caller in a repository with no `docs/decisions/` tree | Same path as a missing generator: warn, skip, continue |
| Regeneration cost grows as the archive grows | 0.06s at 168 changes; the generator reads only session logs, and the NFR table pins ≤ 250 ms so a regression is caught rather than absorbed |
| The added step masks index drift from other causes | D5 keeps the gate checking; a scenario asserts a hand-edited log still reports drift |
