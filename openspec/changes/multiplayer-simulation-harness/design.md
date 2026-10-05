# Design: multiplayer-simulation-harness

## Context

`ri-06` and `ri-11` each have an acceptance outcome that only means something if a
simulation already exists with a recorded baseline. This harness has to satisfy three
conditions at once:

1. **Faithful enough to flip.** When a real capability lands, the measured result has to
   change, and that change has to come from the code under test, not from a harness edit.
2. **Honest about today.** The baseline records what the system actually does now, and it
   cannot pass vacuously.
3. **Cheap and offline.** It runs in the skills CI sweep with no coordinator, no network and
   no vendor CLI, and it is deterministic enough to pin exact values.

The roadmap names gen-eval as the scenario surface. gen-eval already has a CLI transport and
a contract-derived ToolDescriptor archetype, and its own dogfood pack
(`packages/gen-eval/evaluation/`) is the model to follow.

```
gen-eval (CLI transport) ──► bin/mpsim run --scenario <id> ──► JSON report on stdout
                                         │
                       ┌─────────────────┴──────────────────┐
                       ▼                                    ▼
                World builder                         Tick scheduler
    bare remote + N principals                    each tick: agents act, push;
    (identity, clone/worktree, agent id)          readiness = Roadmap.ready_items()
                       │                          over the remote's roadmap/checkpoint
                       ▼
          plan step ──► CollisionProbe registry ──► probes[] + collision_detected
                    └─► fixture oracle          ──► collision_present
```

## Decisions

### D1: New capability `multiplayer-simulation`, not the scaffold's `multiplayer-collaboration`

The scaffold put these requirements under `multiplayer-collaboration`. Every sibling item
uses that placeholder too. Mixing test-harness requirements with collaboration behaviour in
one capability spec would give the capability two kinds of content with different owners and
lifecycles. It would also put this change's spec delta in the same file as about 19 sibling
deltas, which is exactly the same-requirement collision the roadmap is trying to make visible.

- **Chosen**: a narrow capability `multiplayer-simulation` covering the simulation harness,
  its scenarios, its probe seam and its report contract.
- **Rejected**: `gen-eval-framework`. That capability specifies the framework itself, and a
  scenario pack is a consumer of gen-eval, not part of it.
- **Rejected**: keeping `multiplayer-collaboration`, for the collision and ownership reasons
  above.
- **Consequence**: the spec deltas of `ri-06` and `ri-11` that mention "the simulation
  harness's scenario" should reference `multiplayer-simulation` requirements. When those
  changes iterate, they will see this as a cross-capability reference rather than a
  duplicate.

### D2: Harness lives at `skills/tests/multiplayer-simulation/`, driven by the skills venv

The driver must import the systems it measures. The roadmap-runtime admission rule and the
future plan-feature collision scanner both live in `skills/`. Packages under `packages/` have
their own virtualenvs and no import path into `skills/`.

- **Chosen**: `skills/tests/multiplayer-simulation/`, holding:
  - `mpsim/`, the driver package: `world.py`, `agents.py`, `clock.py`, `oracle.py`,
    `report.py`, `errors.py`, `__main__.py`, plus two subpackages:
    - `probes/`, the collision probe seam (D4);
    - `scenarios/`, one module per scenario family. These are discovered with `pkgutil`, so
      adding a scenario never edits a shared list.
  - `bin/mpsim`, a launcher that runs `python -m mpsim` with the harness directory on
    `sys.path`
  - `fixtures/`, the seed capability spec, the memory-store roadmap and the durations
  - `evaluation/`, holding `descriptor.yaml` (generated) and `scenarios/*.yaml` (the gen-eval
    pack)
  - `test_*.py`
- `skills/tests/` is excluded from `install.sh`, so no consumer repository receives the
  harness. That also satisfies the roadmap constraint that installed payloads stay portable.
- Imports of skill scripts follow the existing `sys.path` pattern in
  `skills/tests/roadmap-runtime/conftest.py`.
- **Rejected**: a new `packages/multiplayer-sim/`. It would need its own CI job, which
  `test_every_package_suite_runs_in_ci` enforces, and it would have no way to import
  `skills/roadmap-runtime` without vendoring that code.
- **Rejected**: `agent-coordinator/evaluation/scenarios/`. The coordinator gen-eval job needs
  Postgres and a live HTTP service, which contradicts the offline requirement.

### D3: gen-eval runs in-process from pytest, with `gen-eval` added to the skills `test` extra

- **Chosen**: add `gen-eval = { path = "../packages/gen-eval" }` to the
  `[tool.uv.sources]` table in `skills/pyproject.toml`, and add `gen-eval` to the `test`
  extra. This follows the existing path-dependency pattern for `system-one-decisions` and
  `openbao-credentials`. A pytest test, `test_gen_eval_pack.py`, invokes the `gen-eval`
  console script by subprocess with `--descriptor evaluation/descriptor.yaml
  --fail-threshold 1.0`, with `bin/` prepended to `PATH` and the harness directory as the
  working directory. The pack therefore runs wherever the harness tests run.
- gen-eval's core dependencies are pydantic, pyyaml, jinja2, jsonpath-ng and httpx. The
  skills `test` extra already pulls pyyaml, httpx and, through fastapi, pydantic, so the
  added footprint is jinja2 and jsonpath-ng.
- **Feasibility evidence**: during planning, a scratch copy of `skills/pyproject.toml` with
  this dependency added resolved cleanly with `uv lock` (56 packages).
- **Rejected**: running the pack from the `gen-eval-tests` CI job, with `mpsim` shelling into
  the skills venv through `uv run --project ../../skills`. That is a cross-venv subprocess
  chain, fragile under PATH differences, and it splits one feature's CI signal across two
  jobs.
- **Fallback**: if `uv lock` cannot resolve the added dependency, task 1.3 stops and records
  the conflict. The fallback is the rejected option above, recorded as a design amendment
  rather than taken silently.

### D4: Collision detection is a probe seam, with a ground-truth oracle alongside it

Plan-time requirement-collision detection does not exist yet. `feature_registry.py` overlap
needs a coordinator and covers only locks and files. Asking "was a collision detected at plan
time?" today has one honest answer: nothing ran.

- **Chosen**: `mpsim.probes` (`mpsim/probes/__init__.py`) defines a `CollisionProbe` protocol and a module-level registry.
  - Protocol: `probe_id: str`, plus
    `detect(view: PrincipalView, change_id: str) -> ProbeResult`.
  - `PrincipalView` exposes the principal's worktree path and the shared remote's URL, so a
    probe can read git state but cannot mutate the world.
  - `ProbeResult` fields: `probe_id`, `status ∈ {ok, error}`, `collisions: list[{level,
    other_change, requirement}]`, `error: str | null`.
- At each principal's plan step, the driver calls every registered probe. It records
  `probes` (one entry per probe that ran) and sets `collision_detected` to true when any probe
  with status `ok` reported a collision at level `requirement` against the other principal's
  change.
- A probe that raises an exception, or runs longer than its per-probe timeout (default 10 s),
  is recorded with `status: error`. The run still completes. A probe runs in a daemon thread,
  so a hung probe is abandoned at its timeout rather than joined, and it cannot keep the
  process alive. This mirrors the roadmap
  constraint that advisory signals fail open.
- `mpsim.oracle` computes `collision_present` from fixture contents. It is true when the two
  simulated changes' spec deltas name the same `### Requirement:` heading of the same
  capability. It is a string comparison over files the fixture wrote, with no git history and
  no live scanning. It exists only so a broken fixture cannot make "not detected" trivially
  true. It is not a detector, and it is never registered as a probe.
- **Selection**: `mpsim run --probe <id>` restricts the run to the named probes. With no
  `--probe`, every registered probe runs. Registration happens in
  `mpsim/probes/__init__.py`. Adding a probe means adding one import line there, and the
  scenario files stay untouched.
- **Rejected**: making the harness invoke a predetermined scanner CLI path. That would fix
  `ri-06`'s interface before `ri-06` designs it. The adapter belongs on the harness side, and
  `ri-06` writes a thin probe that wraps whatever entry point it ships.
- **Rejected**: pinning `collision_detected: false` without the oracle. A fixture regression
  that stopped writing the shared requirement would pass the baseline and then also break
  `ri-06`'s flip, with nothing to say why.

### D5: Blocked time is measured in logical ticks with the real admission rule

- **Clock**: a logical tick counter starting at 0. The fixture declares a duration in ticks
  for each step: `plan`, `contract`, `implement`. Nothing reads wall-clock time, which is
  what makes `blocked_ticks` reproducible enough to pin.
- **Readiness**: on every tick, the scheduler fetches the shared remote into the dependent
  principal's clone. It then loads the fixture world's `roadmap.yaml` through
  roadmap-runtime's `load_roadmap`. That call validates the file against the *real*
  repository's roadmap schema, located from the real repo root and not the temporary world,
  so a schema extension in `ri-11` is exercised too. Finally, the scheduler asks
  `Roadmap.ready_items()` whether the dependent's item is admitted. `ready_items()` decides
  from item statuses alone: a dependency counts as satisfied when its item `status` is
  `completed`, and only items whose status is `approved` are admitted.
- **Status transitions are fixture data, not harness code.** Each step in a principal's
  fixture script may declare `on_start.set_status` and `on_finish.set_status` for that
  principal's own roadmap item. The agent applies the change to `roadmap.yaml`, commits and
  pushes it. In the baseline fixture:
  - `plan` and `contract` change no status, so the item stays `approved` and remains
    admissible;
  - `contract` pushes the contract files to the owner's branch but sets no status, because
    today's roadmap schema has no contract-complete state. That absence is the baseline gap;
  - `implement` sets `in_progress` when it starts and `completed` when it finishes.
- **Intra-tick order.** The pinned value depends on it, so it is fixed. Within tick *t*:
  1. Every step that finishes at *t* applies its `on_finish` transition, commits and pushes,
     taking principals in fixture declaration order.
  2. Each waiting principal fetches and evaluates `ready_items()`.
  3. An admitted principal applies its implement step's `on_start` at the same tick *t*.

  A dependency completed at tick 11 therefore admits its dependent at tick 11, not tick 12.
- **Metric**: for each principal,
  `blocked_ticks = ready_tick − earliest_start_tick`.
  - `earliest_start_tick` is the tick at which that principal's own preceding steps finished
    (its plan).
  - `ready_tick` is the first tick at which `ready_items()` admits its implement step.
  - A principal with no dependency is ready at `earliest_start_tick`, so its value is 0.
- **Baseline fixture durations**:
  - `storage-owner`: plan 1, contract 2, implement 8. Its implementation completes at tick
    11.
  - `retrieval-owner`: plan 1, implement 4. Its earliest start is tick 1.
  - Today's bare `depends_on` keeps it blocked until tick 11, so the pinned baseline is
    `blocked_ticks: {retrieval-owner: 10, storage-owner: 0}`.
- **Termination**: `--tick-budget` (default 50) bounds the loop. If the dependency is not
  complete when the budget runs out, the run stops with that principal marked
  `unblocked: false` and `blocked_ticks = tick_budget − earliest_start_tick`. It never loops
  forever. A budget below 1 is a usage error and exits 64.
- **What `ri-11` changes**: `ri-11` extends the roadmap schema and the admission rule. Its
  flip is three fixture edits plus one expectation edit, and the harness code itself does not
  change. The fixture edits:
  1. the dependency becomes `{item: ri-storage, on: contract}`;
  2. the `contract` step gains `on_finish.set_status: contract_complete`, or whatever state
     name `ri-11` defines;
  3. the expectation in the scenario file changes to the new, lower `blocked_ticks`. Under
     the baseline durations that is 2.

  `ri-11` ships its own rule change alongside these.
- **Rejected**: a harness-local readiness function. It would freeze the measured behaviour at
  whatever the harness author wrote and never move when `ri-11` lands.
- **Rejected**: hard-coding status transitions in `ScriptedAgent`. `ri-11` would then
  have to edit harness code to emit its new state, which breaks the condition that the
  harness does not change when a capability lands.
- **Rejected**: wall-clock timing of real agent runs. It is non-deterministic, slow, and
  needs vendor access.

### D6: Principals are harness-local identities with real git isolation

- Each principal has:
  - a `name`, used as the git `user.name`;
  - an email in the form `<name>@sim.invalid`. The `.invalid` TLD is reserved, so the address
    can never route anywhere;
  - an `agent_id` (`<name>-agent-1`);
  - its own clone of the shared bare remote under `<world>/principals/<name>/clone`, with its
    work in a `git worktree` at `<world>/principals/<name>/wt-<change>`.
- **Visibility**: principals see each other's work only through `git fetch` from the shared
  remote. Unpushed commits are invisible to everyone else. That models the roadmap
  constraint that planning-time capabilities must work with the git remote alone.
- **Determinism**: commits use fixed `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` values
  derived from the tick, `-c init.defaultBranch=main`, and no global git config
  (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`). Ignoring global config also
  keeps a developer's hooks, commit signing (`commit.gpgsign`) and credential helpers out of
  the simulated world.
- **Seed commit**: the world builder makes one seed commit on `main`, authored by
  `sim-seed <sim-seed@sim.invalid>`, containing the fixture's seeded `openspec/specs/` and
  `roadmap.yaml`. Identity assertions apply to commits reachable from a principal's change
  branch but not from `main`.
- **Size**: the world supports N ≥ 2 principals. Fewer than 2 is a usage error with exit
  code 64.
- **Rejected**: registering the simulated principals in the
  `principal-credential-architecture` registry. That registry belongs to `ri-02` and is out
  of scope. The harness would also be coupled to a schema that does not exist yet.

### D7: Scripted agents behind an `Agent` protocol

- `Agent.act(view: PrincipalView, step: Step) -> None` performs one step's file edits and
  git operations.
- `ScriptedAgent` replays the fixture's step script deterministically:
  - write the OpenSpec change files under a synthetic change id;
  - commit;
  - push to `refs/heads/sim/<principal>/<change>`, which models an open PR branch.
- **Rejected**: live vendor agents. They are non-deterministic and need network access, so
  they are a non-goal here. The protocol leaves room for a later `ExecutorAgent` that adapts
  `packages/agent-scenarios`' `ScenarioExecutor`.

### D8: CLI surface, report contract and determinism

The CLI surface is contracted in `contracts/cli/mpsim.yaml`. It validates against
`gen-eval-framework/schemas/cli-contract.schema.json` and cites `multiplayer-simulation.*`
requirements in `traceability:` blocks.

| Command | Flags | Purpose |
|---|---|---|
| `mpsim list` | (none) | Print the built-in scenario ids as a JSON array. |
| `mpsim run` | `--scenario <id>` (required), `--probe <id>` (repeatable), `--tick-budget <int>` (default 50), `--fixture-dir <path>` | Run one scenario and print its report. `--fixture-dir` replaces the scenario's built-in fixture directory. Tests use it to supply altered fixtures, such as a lost shared requirement, an already-completed dependency, or one principal, without touching the shipped fixtures. |

- `mpsim run` prints one JSON object to stdout. It validates against
  `sim-report.schema.json` and is written with sorted keys and no trailing whitespace.
- Fields:
  - `schema_version`, `scenario_id`, `principals[]` (name, agent_id, change_id)
  - `collision_present`, `collision_detected`, `probes[]`
  - `blocked_ticks{principal: int}`, `unblocked{principal: bool}`, `final_tick`
  - `timeline[]` of `{tick, principal, step, event}`
- Fields that do not apply to a scenario are `null`, not omitted, so gen-eval `body`
  assertions stay uniform across the pack.
- The report never contains absolute paths, temp directory names or commit SHAs. Only
  ref names, change ids and ticks appear. That keeps two runs byte-identical, and the
  determinism test asserts it.

**Exit codes**:

| Code | Meaning |
|---|---|
| 0 | The scenario ran to completion and a report was emitted. This holds whatever was or was not detected, and whatever the blocked time was. |
| 1 | The harness could not establish the scenario, for example when the oracle finds that the fixture's required collision is missing, or a git operation failed. A report with an `error` field is still printed when possible. |
| 64 | Usage error: an unknown scenario, an unknown probe, a missing `--fixture-dir`, a `--tick-budget` below 1, or a fixture declaring fewer than 2 principals (`EX_USAGE`). |

Pinned expectations live in the gen-eval scenario YAML, not in the driver. The driver
measures and the scenario decides what is expected.

### D9: Offline enforcement is tested, not assumed

- The driver imports nothing from `agent-coordinator` and nothing from
  `coordination_bridge`. It has no HTTP or MCP transport.
- An autouse fixture in the harness `conftest.py` replaces `socket.socket.connect` (and
  `connect_ex`) so that any `AF_INET` or `AF_INET6` connection raises. That turns an
  accidental network call into an immediate test failure instead of a CI-only hang.
- Subprocesses such as `git` and `bin/mpsim` do not inherit that patch. For them:
  - the shared remote is a `file://` path, so git never opens a socket;
  - the gen-eval pack test sets `COORDINATION_API_URL=http://127.0.0.1:9`, a discard port
    that would fail fast, and asserts the reports are byte-identical to a run without that
    variable.
- **Rejected**: relying on the CI runner having no coordinator. The runner does have network
  access, so the absence of a coordinator proves nothing about the harness.

### D10: Archive stability

- Fixture worlds use synthetic change ids prefixed `sim-`, for example
  `sim-memory-store-core` and `sim-retrieval-api`.
- A test asserts that no fixture change id is a real repository change id. It reads the ids
  the same way the path-stability guard does, through `openspec_paths`, so a future real
  change named `sim-…` cannot quietly turn a fixture into a guard violation.
- Any test that reads this change's own artifacts goes through
  `change_dir(repo_root_from(__file__, 3), ...)`. The CLI contract is read from its promoted
  path under `openspec/contracts/multiplayer-simulation/`, never from the change directory.

## Risks and Trade-offs

| Risk | Mitigation |
|---|---|
| Adding `gen-eval` to the skills venv conflicts with existing pins | D3 fallback, plus task 1.3 runs `uv lock` first and stops if it fails |
| Git-heavy scenarios make the skills sweep slower | Four scenarios, each creating only a handful of commits. Budget is under 30 s for the whole harness directory, checked in task 6.2. |
| `Roadmap.ready_items` signature changes under `ri-11` | That is the intended coupling: the harness should move with the rule. Task 4.2 documents the call site in the README as the place `ri-11` must look. |
| Pinned baselines read as asserting that the bug should exist | Each pinned value carries a YAML comment naming the roadmap item that flips it. The README states that baselines are characterisations. |
| The oracle and a future probe diverge in what they call a "collision" | The oracle is deliberately narrow: same capability and same requirement heading. `ri-06` may detect more levels. The flip assertion is only `collision_detected`, not equality with the oracle. |

## Open Questions

None block implementation. These are recorded for downstream items:

- Should `ri-06`'s probe also be exercised at the coordinator level by `ri-07`? Out of scope
  here, and the probe seam allows either.
- Once `ri-02` lands, should the fixture seed an `owners.yaml` so reports can name owners?
  That is deferred to `ri-06`, which needs owners in its collision report.
