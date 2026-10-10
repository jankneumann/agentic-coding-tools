# Change: multiplayer-simulation-harness

> Parent roadmap: `multiplayer-collaboration` (item `ri-05`, Phase 1)
> Change ID: `multiplayer-simulation-harness`
> Effort: M
> Priority: 2
> Capability: `multiplayer-simulation` (new)

## Why

This toolkit is built by one developer and installed into team repositories. The
`multiplayer-collaboration` roadmap exists because single-principal assumptions break in
team use. Its motivating incident was a memory store planned by a small team: two
developers' specs collided, and one developer sat blocked waiting for another's
implementation when only the contract was needed.

None of that can be observed in this repository today. There is one principal, one
coordinator (or none), and one person planning at a time, so team failure modes never
happen here. Later roadmap items need a measurable before/after to prove they work:

- `ri-06` (`plan-time-collision-detection`) says "the simulation harness's same-requirement
  scenario flips from not-detected to detected".
- `ri-11` (`contract-dependencies`) says "the memory-store simulation scenario shows reduced
  time-blocked-on-dependency compared with its baseline".

Both outcomes need a harness that already exists, records an honest baseline, and changes its
measured result when the real capability lands, without the scenario itself being rewritten.
This change builds that harness. It does not build either capability.

## What Changes

- **A deterministic, offline simulation driver, `mpsim`**, at
  `skills/tests/multiplayer-simulation/`. It builds a temporary world: one local bare git
  repository acting as the shared remote, plus two or more simulated principals. Each
  principal has its own git identity, its own clone and worktree, and its own scripted agent.
  Principals see each other's work only through pushes to that remote. Time is a logical tick
  clock rather than wall-clock time. The driver writes one JSON report per scenario run.
- **A plan-time collision probe seam.** At each principal's plan step the driver calls every
  registered `CollisionProbe` and records which probes ran and what they reported. No probe
  is registered today, so the baseline result is "not detected". `ri-06` registers its scanner
  as a probe. A ground-truth oracle, computed from fixture contents, also records whether a
  collision actually exists, so a "not detected" baseline cannot pass because of a broken
  fixture.
- **Readiness from the real admission rule.** The driver decides when a dependent principal
  becomes unblocked by calling the roadmap-runtime admission rule (`Roadmap.ready_items`) on
  the `roadmap.yaml` visible on the shared remote. It does not carry its own readiness
  logic. When `ri-11` changes that rule, the metric moves with it.
- **Two scenarios, each with a control case:**
  - `same-requirement-collision`: principal A pushes a change that modifies requirement R.
    Principal B then plans a change that modifies R. The control case
    `different-requirement-control` has B modify a different requirement.
  - `memory-store-blocked-dependency`: reproduces the dependency half of the incident.
    `retrieval-owner` depends on a memory-store API owned by `storage-owner`. The driver
    reports `blocked_ticks` per principal. The control case `independent-principals-control`
    has no dependency between them.
- **A gen-eval scenario pack.** The four scenarios above are gen-eval CLI-transport
  scenarios. They run against a ToolDescriptor derived from a new CLI contract for `mpsim`,
  promoted to `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml`. Each scenario pins
  its baseline values. A later change that flips a baseline does so with a visible,
  reviewed edit to the scenario's expectation.
- **CI wiring.** The harness test directory joins the skills in-skill sweep in
  `.github/workflows/ci.yml`. It runs with no services, no coordinator, and network sockets
  blocked inside the test process.
- **A small README** in the harness directory. It explains how a downstream change registers
  a probe, flips a pinned baseline, or adds a scenario.

## Non-Goals

- **Building collision detection or contract-level dependencies.** Those belong to `ri-06`,
  `ri-07` and `ri-11`. This change only records today's behaviour.
- **The competing-spec half of the incident.** Reconciling two divergent specs is
  `ri-16` (`reconcile-skill`), which can add its own scenario to this pack.
- **Live LLM agents.** The agents here are scripted and deterministic, because CI must be
  reproducible and offline. Running a live agent per principal (for example through
  `packages/agent-scenarios`' `CLIVendorExecutor`) is a possible later extension, not part of
  this change.
- **Registered human principals and `owners.yaml`.** Simulated identities are local to the
  harness. Once `ri-02` (`ownership-map`) lands, a scenario may seed an `owners.yaml`. This
  change does not anticipate its schema.
- **Coordinator-backed scenarios.** Coordinator claims, locks and queue entries are not
  simulated. `ri-07` and `ri-08` may add a coordinator-backed variant, but the offline pack
  stays the CI baseline.
- **Durable state.** Reports are ephemeral test output written under a temp or `.reports/`
  directory. They are not canonical state, so they are not registered in
  `docs/guides/state-artifacts.md`.
- **Editing the principles guide.** `docs/guides/multiplayer-collaboration.md` belongs to
  `ri-01` (`multiplayer-principles-guide`), which is in flight. Linking the harness from that
  guide is left to whichever change lands second.

## Impact

- **New capability spec delta**: `specs/multiplayer-simulation/spec.md` (ADDED requirements
  only). The scaffold's placeholder capability `multiplayer-collaboration` is not used. See
  design D1.
- **New code**: `skills/tests/multiplayer-simulation/`, which holds the `mpsim` driver
  package, its `bin/mpsim` launcher, fixtures, the gen-eval `evaluation/` pack and tests.
  It sits under `skills/tests/`, which `install.sh` does not ship, so consumer repositories
  receive nothing.
- **New contract**: `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml` (authored in
  `contracts/cli/mpsim.yaml` in this change, then promoted), plus
  `openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json`.
- **Modified**: `skills/pyproject.toml` adds `gen-eval` as a path dependency of the `test`
  extra, which also updates `skills/uv.lock`. `.github/workflows/ci.yml` adds
  `tests/multiplayer-simulation` to the in-skill sweep list.
  `openspec/contracts/README.md` gains a row in its contents table.
- **Read-only dependencies (systems under test)**:
  `skills/roadmap-runtime/scripts/models.py` (`Roadmap.ready_items`, `load_roadmap`, and
  the roadmap schema it validates against), `packages/gen-eval` (ToolDescriptor, CLI transport,
  `scripts/generate_tool_descriptor.py`), and `skills/tests/_shared/openspec_paths.py`.
- **Downstream contract**: `ri-06` and `ri-11` consume the probe seam, the pinned baselines,
  and the report fields `collision_detected` and `blocked_ticks`. Their spec deltas should
  cite `multiplayer-simulation` requirements instead of restating them.

## Acceptance Outcomes

Each outcome from the roadmap item maps to a requirement in the spec delta:

| Roadmap acceptance outcome | Requirement |
|---|---|
| Two principals modifying the same requirement; records whether a collision was detected at plan time (baseline: not detected) | Same-Requirement Collision Scenario Records Plan-Time Detection; Plan-Time Detectors Attach Through A Probe Seam |
| Memory-store scenario reports time-blocked-on-dependency for the dependent principal | Memory-Store Scenario Reports Time Blocked On Dependency |
| Scenarios run in CI without network access to a shared coordinator | Scenarios Run Offline Without A Shared Coordinator |
| Scenario tests resolve change paths with `change_dir()` and pass the path-stability guard | Scenario Tests Are Archive-Stable |
