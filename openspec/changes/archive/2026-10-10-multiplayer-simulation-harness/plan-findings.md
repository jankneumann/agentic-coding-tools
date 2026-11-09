# Plan Findings: multiplayer-simulation-harness

## Iteration 1 (2026-10-05)

Baseline: `openspec validate --strict` passed on the scaffold, which is a structural pass
only. GATEKEEPER set four conditions for PLAN:

- replace the circular WHEN/THEN scaffolds;
- record baselines without asserting later capabilities;
- decide the capability, the non-goals and the offline strategy;
- use `change_dir()`.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | testability | critical | Every scenario was circular ("WHEN implemented THEN <requirement restated>"), so nothing was verifiable | Rewrote the spec as 8 requirements with 26 concrete WHEN/THEN scenarios, each naming the command, the inputs and the exact report fields or exit codes |
| 2 | completeness | critical | proposal.md lacked Why, What Changes and Impact sections | Rewrote the proposal with Why (ri-06 and ri-11 depend on this baseline), What Changes, Non-Goals, Impact, and a table mapping outcomes to requirements |
| 3 | completeness | high | design.md was a stub that only listed open questions | Wrote design D1–D10, each decision with rejected alternatives, plus risks |
| 4 | feasibility | high | tasks.md had 5 generic tasks, none traceable to a requirement and none single-commit | Replaced them with 26 TDD-ordered tasks carrying scenario IDs, design references, dependencies and sizes |
| 5 | assumptions | high | The capability placeholder `multiplayer-collaboration` was shared by about 19 sibling deltas | Chose a new `multiplayer-simulation` capability (D1). This was a recorded autonomous decision; see the session log |
| 6 | assumptions | high | Where the harness lives and which venv runs gen-eval were unstated | D2 puts it at `skills/tests/multiplayer-simulation/`. D3 adds gen-eval to the skills `test` extra; a scratch `uv lock` resolved |
| 7 | assumptions | high | "Collision detected at plan time" has no detector today, so the baseline would pass vacuously | D4 adds a probe seam plus a ground-truth oracle. A broken fixture now exits 1 instead of reading as "not detected" |
| 8 | assumptions | high | How time-blocked is measured was undefined, and a wall-clock measure would be nondeterministic | D5 uses logical ticks and the real admission rule `Roadmap.ready_items`, with a pinned baseline of 10 ticks under fixture durations |
| 9 | testability | high | "Runs without network access" was not enforced | D9 adds an autouse socket-blocking fixture, a `file://` remote, and a byte-identity check with `COORDINATION_API_URL` set |
| 10 | consistency | high | Downstream ri-06 and ri-11 need to flip this harness, but no flip mechanism was defined | Flips happen by registering a probe (one import line) or by a fixture edit plus a rule change, followed by a reviewed edit to the pinned expectation |
| 11 | completeness | medium | Requirements covered only success paths | Added failure and edge scenarios: broken fixture, probe error, probe timeout, unknown probe, tick-budget exhaustion, fewer than two principals |
| 12 | scope | medium | Non-goals were absent, and the incident has two halves | Non-goals now exclude the competing-spec half (ri-16), live LLM agents, owners.yaml (ri-02), coordinator variants (ri-07/08), durable state, and editing ri-01's guide |
| 13 | completeness | medium | No CLI contract or report schema existed | Authored `contracts/cli/mpsim.yaml`, which validates against `cli-contract.schema.json` and cites 7 of 8 requirements, and `contracts/schemas/sim-report.schema.json`. Task 1.2 promotes both |
| 14 | parallelizability | medium | No dependency graph existed, and scenario registration was a shared-file hotspot | Added a dependency graph (max width 3) and switched to `pkgutil` scenario discovery, so 4.4 and 5.2 never edit the same file |
| 15 | testability | medium | Determinism was implicit, yet exact pinned values depend on it | Added the "Scenario Reports Are Deterministic" requirement: sorted keys, no paths or SHAs, byte-identical reruns |
| 16 | consistency | low | CI coverage guard and path guard interplay | O.3 and A.1 cover both explicitly |

Remaining below threshold: none.

## Iteration 2 (2026-10-05)

A cold re-read of the iteration-1 plan found 2 high, 4 medium and 2 low findings.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | clarity | high | The order of events within a tick was unspecified. A dependency finishing at tick 11 could admit its dependent at 11 or 12, which changes the pinned baseline (10 vs 11) | D5 now fixes the order: finishing steps push in declaration order, then waiting principals fetch and evaluate `ready_items()`, then admitted principals start |
| 2 | consistency | high | D5 said ri-11 changes no harness code, yet `ScriptedAgent` hard-coded status transitions, so emitting `contract_complete` would have needed a code edit | Status transitions are now fixture data (`on_start` / `on_finish` `set_status`). The ri-11 flip is three fixture edits plus a rule change, worth 2 ticks under baseline durations. The hard-coded alternative is recorded as rejected |
| 3 | testability | medium | O.2 compared "reports" from gen-eval runs, but gen-eval parses stdout into a body and adds timings, so byte identity was unobservable there | O.2 now compares `mpsim run` stdout directly, and moved from task 7.3 to task 6.1 |
| 4 | clarity | medium | P.1's "every commit on alice's branch" included the seed commit | D6 defines a `sim-seed` identity for the seed commit. P.1 now scopes to commits reachable from the change branch but not from `main` |
| 5 | clarity | medium | The pinned-baseline comment rule had no verifying scenario | Added scenario G.3, which scans the pack for `ri-06` / `ri-11` comments. The drift scenario became G.4, and tasks were renumbered |
| 6 | clarity | medium | D.1's "separate temporary directories" did not say how a test controls them | D.1 now runs with different `TMPDIR` values |
| 7 | completeness | low | `--tick-budget 0` or a negative budget was unhandled | Added exit 64 to D5, D8, the contract and task 6.1 |
| 8 | feasibility | low | A hung probe thread could keep the process alive | D4 runs probes in a daemon thread that is abandoned at timeout |

Quality checks after the fixes:

- `openspec validate --strict` passes.
- Scenario coverage is 27/27 IDs traced to tasks, with no orphans either way.
- The CLI contract validates, and all traceability citations resolve.
- The single uncited requirement, Archive-Stable, has no CLI surface. That is acceptable
  because reverse traceability is not opted in.

Remaining below threshold: none at medium or above.

## Iteration 3 (2026-10-05): convergence

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | medium | Fixture-declared status transitions and the intra-tick order were stated only in design D5, although the pinned baseline and ri-11's flip both depend on them | Added both as normative SHALL clauses in "Memory-Store Scenario Reports Time Blocked On Dependency" |
| 2 | testability | low | The 30-second suite budget is recorded at task 9.1, not asserted | Accepted. A wall-clock assertion would be flaky in CI |
| 3 | consistency | low | ri-06 and ri-11 deltas still reference the `multiplayer-collaboration` placeholder | Out of scope for this change. Recorded as an open question for those changes' own iteration |

Termination: all findings are below the medium threshold. `openspec validate --strict` passes.
