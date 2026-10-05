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
