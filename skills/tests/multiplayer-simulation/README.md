# multiplayer-simulation harness

A deterministic, offline simulation of several principals sharing one git remote. It gives
`ri-06` (plan-time collision detection) and `ri-11` (contract-level dependencies) a recorded
baseline to flip. Spec: capability `multiplayer-simulation`; design decisions D1-D10 in the
change's `design.md`.

## What it measures, and why baselines are characterisations

Two questions, each with a scenario and a control:

| Scenario | Question | Baseline pinned today |
|---|---|---|
| `same-requirement-collision` | Two principals modify the same requirement. Was it detected at plan time? | `collision_present: true`, `collision_detected: false`, `probes: []` |
| `different-requirement-control` | Same, but different requirements. | no collision, none detected |
| `memory-store-blocked-dependency` | How many ticks is the dependent principal blocked? | `blocked_ticks` `{retrieval-owner: 10, storage-owner: 0}` |
| `independent-principals-control` | Same, with no dependency edge. | all zeros |

The pinned values record what the system does **now**. They are characterisations, not
targets: "not detected" and "10 ticks blocked" are not claims that the behaviour is right,
only that a later change moves them on purpose. Every pinned expectation in
`evaluation/scenarios/` carries a comment naming the roadmap item that flips it, and a test
enforces that.

## How `ri-06` registers a probe

1. Write a probe class with a `probe_id` and `detect(view, change_id) -> ProbeResult`
   (see `mpsim/probes/__init__.py`). `view` is read-only.
2. Add **one import line** at the bottom of `mpsim/probes/__init__.py` (the marked spot) that
   registers it.
3. Edit the pinned expectation in `evaluation/scenarios/collision.yaml`:
   `collision_detected: true` for `same-requirement-collision` and a non-empty `probes`.
   No scenario module under `mpsim/scenarios/` changes.

`collision_present` comes from the oracle (`mpsim/oracle.py`), which only compares fixture
files. It is never a probe.

## Where `ri-11` must look

- The call site: `Roadmap.ready_items()` in `mpsim/scenarios/blocked.py`. The scheduler holds no
  readiness logic of its own.
- The fixture dependency form: `fixtures/memory-store-blocked-dependency/seed/roadmap.yaml`
  (today a bare `depends_on`).
- Status transitions are fixture data: `on_start` / `on_finish` `set_status` in
  `fixtures/*/scenario.yaml`. A `contract` step that declares a new status needs only a fixture
  edit.
- The pinned `blocked_ticks` in `evaluation/scenarios/blocked.yaml` (10 today, 2 under the
  baseline durations once dependents may start on contract completion).

## Layout

```
mpsim/            driver: world, agents, clock, oracle, report, applier, runner, CLI
  probes/         collision probe seam
  scenarios/      one module per scenario family, discovered with pkgutil
bin/mpsim         launcher (python -m mpsim)
fixtures/         per-scenario data: scenario.yaml, seed/, per-step file trees
evaluation/       descriptor.yaml (generated) and scenarios/*.yaml (the gen-eval pack)
test_*.py         the suite
```

`roadmap.yaml` has one authoritative copy: `main` on the shared remote. Principals never edit it
or push to `main`; `mpsim/applier.py` (a simulated supervisor, committing as `sim-supervisor`
from its own clone) writes every status change a fixture declares.

## Adding a scenario

1. Add a fixture directory under `fixtures/<scenario-id>/` with `scenario.yaml`, a `seed/` tree
   and any `files_from` directories.
2. Add a module under `mpsim/scenarios/` exposing a module-level `SCENARIOS` mapping of
   `Scenario` objects. Nothing else lists it.
3. Add a gen-eval scenario under `evaluation/scenarios/` with a comment naming the item that
   flips each pinned value.
4. Fixture change ids must start with `sim-` and never match a real change id.

## Running locally

```bash
cd skills
uv run pytest tests/multiplayer-simulation          # the whole suite
uv run ruff check tests/multiplayer-simulation
PATH=tests/multiplayer-simulation/bin:$PATH uv run python -m mpsim list   # from the harness dir
```

Regenerate the descriptor after editing the CLI contract:

```bash
python packages/gen-eval/scripts/generate_tool_descriptor.py \
  --contract openspec/contracts/multiplayer-simulation/cli/mpsim.yaml \
  --out skills/tests/multiplayer-simulation/evaluation/descriptor.yaml
```
