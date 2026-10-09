# Tasks: multiplayer-simulation-harness

> Change ID: `multiplayer-simulation-harness`
> Tier: sequential by default. The groups marked *parallel-safe* below write disjoint files and
> may run concurrently under `/implement-feature` local-parallel.
> Harness root: `skills/tests/multiplayer-simulation/`. All paths below are relative to it
> unless they start with `openspec/`, `skills/` or `.github/`.
>
> **Scenario IDs** (numbered in the order they were authored in
> `specs/multiplayer-simulation/spec.md`; scenarios added during PLAN_FIX take the next free
> number in their group so earlier references stay valid):
> - `P.1`–`P.4`: Simulated Principals Have Separate Identities, Worktrees, And Agents
> - `C.1`–`C.3`: Same-Requirement Collision Scenario Records Plan-Time Detection
> - `S.1`–`S.5`: Plan-Time Detectors Attach Through A Probe Seam (`S.5`: Registering a
>   probe edits no scenario definition)
> - `B.1`–`B.6`: Memory-Store Scenario Reports Time Blocked On Dependency (`B.5`: Status
>   transitions reach only the integration ref; `B.6`: Status transitions are declared only
>   in fixture data)
> - `O.1`–`O.4`: Scenarios Run Offline Without A Shared Coordinator (`O.4`: The driver
>   imports no coordinator or transport modules)
> - `D.1`–`D.2`: Scenario Reports Are Deterministic
> - `G.1`–`G.4`: Scenario Pack Runs Through gen-eval
> - `A.1`–`A.3`: Scenario Tests Are Archive-Stable

## 1. Contracts and scaffolding

- [x] 1.1 Write failing contract tests in `test_contracts.py`. Read everything through
  `repo_root_from(__file__, 3)`. Four cases:
  - `openspec/contracts/multiplayer-simulation/cli/mpsim.yaml` validates against
    `openspec/contracts/gen-eval-framework/schemas/cli-contract.schema.json`.
  - `sim-report.schema.json` is a valid Draft 2020-12 schema.
  - Every `traceability` citation resolves to a requirement heading in this change's spec
    delta. Locate the delta with `change_dir()`.
  - Each promoted copy is byte-identical to its change-local copy. Locate the change-local
    copy with `change_dir()`.

  [S]
  **Spec scenarios**: G.4, A.1
  **Contracts**: contracts/cli/mpsim.yaml, contracts/schemas/sim-report.schema.json
  **Design decisions**: D8, D10
  **Dependencies**: 1.4
- [x] 1.2 Promote `contracts/cli/mpsim.yaml` and `contracts/schemas/sim-report.schema.json` to
  `openspec/contracts/multiplayer-simulation/{cli,schemas}/`, and add a row to the contents
  table in `openspec/contracts/README.md`. When this is done, 1.1 passes. [XS]
  **Dependencies**: 1.1
- [x] 1.3 Add `gen-eval` to the `test` extra in `skills/pyproject.toml`, add
  `gen-eval = { path = "../packages/gen-eval" }` under `[tool.uv.sources]`, and run `uv lock`
  in `skills/`. A scratch resolution during planning succeeded, resolving 56 packages. Verify
  that `uv run --project skills gen-eval --print-contract-version` exits 0. If resolution
  fails, stop and take the D3 fallback as a recorded design amendment, never silently. [XS]
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.4 Scaffold the harness directory:
  - `conftest.py`, which puts the harness root and `skills/roadmap-runtime/scripts` on
    `sys.path` using the pattern in `skills/tests/roadmap-runtime/conftest.py`, and adds an
    autouse fixture that makes `AF_INET`/`AF_INET6` `socket.connect` and `connect_ex` raise
    (D9).
  - `bin/mpsim`, an executable launcher that runs `python -m mpsim` with the harness root on
    `sys.path`.
  - `mpsim/__init__.py`.
  - `mpsim/scenarios/__init__.py`, a registry that discovers scenario modules in the package
    with `pkgutil`, so later tasks add scenarios without editing a shared list.
  - A `UsageError` exception in `mpsim/errors.py`.

  Add `tests/multiplayer-simulation` to the in-skill sweep list in `.github/workflows/ci.yml`.
  Add a sanity test proving the socket fixture is active, meaning a connect to `127.0.0.1:9`
  raises. [S]
  **Spec scenarios**: O.1, O.3
  **Design decisions**: D2, D9
  **Dependencies**: None
- [ ] Checkpoint: run `skills/tests/ci_coverage/` and the harness directory. Only the contract,
  scaffold, `pyproject.toml`/`uv.lock` and `ci.yml` should have changed.

## 2. World, agents, clock and report (sequential chain)

- [x] 2.1 Write failing tests in `test_world.py`:
  - two principals get distinct identities (`<name>@sim.invalid`), clones, worktrees and agent
    ids (P.1);
  - an unpushed commit is invisible to the other principal after fetch (P.2);
  - three principals build (P.3);
  - one principal raises `UsageError` (P.4, at the API level);
  - commits use tick-derived fixed dates under `GIT_CONFIG_GLOBAL=/dev/null` and
    `GIT_CONFIG_NOSYSTEM=1`.

  [S]
  **Spec scenarios**: P.1, P.2, P.3, P.4
  **Design decisions**: D6
  **Dependencies**: 1.4
- [x] 2.2 Implement `mpsim/world.py`: a `World` that owns the temporary root, the `file://`
  bare remote, per-principal clones and worktrees, and a `PrincipalView` that is read-only for
  probes. [M]
  **Dependencies**: 2.1
- [x] 2.3 Write failing tests in `test_agents.py`:
  - `ScriptedAgent` writes the step's OpenSpec files under a `sim-` change id;
  - it commits as its principal and pushes to `refs/heads/sim/<principal>/<change>`;
  - it returns the step's declared status transitions and never modifies `roadmap.yaml` or
    pushes to `main` (operator decision A1);
  - `Clock` advances only when told to and never reads wall-clock time.

  [S]
  **Spec scenarios**: P.1
  **Design decisions**: D5, D7
  **Dependencies**: 2.2
- [x] 2.4 Implement `mpsim/agents.py` (the `Agent` protocol and `ScriptedAgent`) and
  `mpsim/clock.py`. [S]
  **Dependencies**: 2.3
- [x] 2.5 Write failing tests in `test_report.py`:
  - the report builder emits sorted-key JSON with every schema property present, using `null`
    for anything that does not apply;
  - it validates against the promoted `sim-report.schema.json`;
  - it rejects any value containing the world's temporary root or a 40-character hexadecimal
    string (D.2).

  [S]
  **Spec scenarios**: D.2
  **Design decisions**: D8
  **Dependencies**: 1.2, 2.4
- [ ] 2.6 Implement `mpsim/report.py`. [S]
  **Dependencies**: 2.5

## 3. Collision oracle (parallel-safe with section 2)

- [ ] 3.1 Write failing tests in `test_oracle.py`. Two spec deltas that name the same
  `### Requirement:` heading of the same capability give `collision_present: true`. Different
  headings, or the same heading in different capabilities, give `false`. [XS]
  **Spec scenarios**: C.1, C.2
  **Design decisions**: D4
  **Dependencies**: 1.4
- [ ] 3.2 Implement `mpsim/oracle.py`. It reads only the fixture files and no git history.
  [XS]
  **Dependencies**: 3.1

## 4. Probe seam and collision scenarios

- [ ] 4.1 Write failing tests in `test_probes.py`, against a registry that starts empty:
  - a stub probe reporting a requirement-level collision sets `collision_detected: true`
    (S.1);
  - a probe that raises is recorded as `status: error` with a non-empty `error`, and the run
    still completes (S.2);
  - a probe that sleeps past a reduced per-probe timeout is recorded as `error`, with the
    timeout named in the message (S.3);
  - an unknown `--probe` id raises `UsageError` (S.4);
  - registering a stub probe and running every built-in scenario modifies no file under
    `mpsim/scenarios/` or `evaluation/scenarios/` (compare content hashes before and after),
    and the stub appears in both collision scenarios' `probes` (S.5).

  Use a fixture that saves and restores the registry, so the stubs never leak into other
  tests. [S]
  **Spec scenarios**: S.1, S.2, S.3, S.4, S.5
  **Design decisions**: D4
  **Dependencies**: 2.6, 3.2
- [ ] 4.2 Implement `mpsim/probes/__init__.py`: the `CollisionProbe` protocol, `ProbeResult`,
  the module-level registry with register and select, and per-probe timeout enforcement.
  Leave no probe registered by default, and add a comment marking where `ri-06` adds its
  import line. [S]
  **Dependencies**: 4.1
- [ ] 4.3 Author fixtures under `fixtures/same-requirement-collision/` and
  `fixtures/different-requirement-control/`:
  - a seeded capability spec `openspec/specs/sim-notes/spec.md` with at least two
    requirements;
  - principals `alice` and `bob`;
  - deltas `sim-alice-notes` and `sim-bob-notes`, both modifying the same requirement in the
    first fixture and different requirements in the control.

  Write failing scenario tests in `test_collision_scenarios.py` for C.1, C.2, and C.3. C.3
  copies the fixture to `tmp_path`, breaks the shared heading, and expects exit 1 with
  `error`. [S]
  **Spec scenarios**: C.1, C.2, C.3
  **Design decisions**: D4, D6
  **Dependencies**: 4.2
- [ ] 4.4 Implement `mpsim/scenarios/collision.py`. It registers both collision scenarios.
  Alice plans, pushes and finishes. Bob fetches, then plans. At Bob's plan step it runs the
  oracle and the selected probes and fills `collision_present`, `collision_detected` and
  `probes`. [M]
  **Dependencies**: 4.3

## 5. Memory-store scenario (parallel-safe with section 4)

- [ ] 5.1 Author fixtures under `fixtures/memory-store-blocked-dependency/` and
  `fixtures/independent-principals-control/`. Each needs:
  - a `roadmap.yaml` that validates against the real roadmap schema. In the first fixture,
    `ri-retrieval` declares `depends_on: [ri-storage]`; in the control the two items are
    independent;
  - the durations from D5;
  - per-step `on_start.set_status` and `on_finish.set_status` data from D5: `implement` sets
    `in_progress` at start and `completed` at finish, and `plan` and `contract` set nothing;
  - principals `storage-owner` and `retrieval-owner`;
  - changes `sim-memory-store-core` and `sim-retrieval-api`.

  Write failing tests in `test_blocked_scenarios.py`:
  - baseline `{"retrieval-owner": 10, "storage-owner": 0}` with both principals unblocked
    (B.1);
  - the control gives all zeros (B.2);
  - `--tick-budget 5` gives `unblocked.retrieval-owner: false` and `blocked_ticks` of 4
    (B.3);
  - a `tmp_path` fixture whose dependency starts `completed` gives 0 (B.4);
  - after the baseline run, no commit on a `sim/*` branch beyond the seed touches
    `roadmap.yaml`, every post-seed commit on `main` is authored by `sim-supervisor`, and
    `roadmap.yaml` at `main` shows both items `completed` (B.5);
  - a static scan of `mpsim/` finds no status literal used as a `set_status` value, and a
    `tmp_path` fixture whose implement step declares no `on_finish.set_status` leaves
    `unblocked.retrieval-owner` false (B.6).

  [S]
  **Spec scenarios**: B.1, B.2, B.3, B.4, B.5, B.6
  **Design decisions**: D5, D7
  **Dependencies**: 2.6
- [ ] 5.2 Implement `mpsim/applier.py` (the status applier, which commits declared
  transitions to `roadmap.yaml` on `main` as `sim-supervisor` and pushes) and
  `mpsim/scenarios/blocked.py`, the tick scheduler:
  - follow the intra-tick order from D5 exactly: finishing steps push their work to their
    change branches, in declaration order; the applier commits their `on_finish`
    transitions to `main`; then each waiting principal fetches `main`, calls `load_roadmap`
    on `roadmap.yaml` from `origin/main` with the real repo root for schema lookup, and
    calls `Roadmap.ready_items()`; then the applier commits admitted principals'
    `on_start`;
  - apply status transitions only from fixture data, never from code;
  - compute `blocked_ticks` and `unblocked` exactly as D5 defines them.

  The scheduler must not contain readiness logic of its own. B.4 proves this behaviourally:
  a dependency that is already `completed` unblocks the dependent through the admission
  rule alone. [M]
  **Dependencies**: 5.1

## 6. CLI and determinism

- [ ] 6.1 Write failing tests in `test_cli.py`, running `bin/mpsim` by subprocess:
  - `list` prints the four scenario ids in sorted order;
  - `run` with an unknown scenario, an unknown probe, a `--fixture-dir` that does not exist,
    `--tick-budget 0`, or a one-principal `--fixture-dir` exits 64 and names the problem on
    stderr (P.4, S.4);
  - two runs of `memory-store-blocked-dependency` with different `TMPDIR` values are
    byte-identical (D.1);
  - each scenario run with `COORDINATION_API_URL` unset and with it set to
    `http://127.0.0.1:9` gives byte-identical stdout (O.2);
  - every scenario's stdout validates against the schema and contains no temporary path and no
    40-character hexadecimal string, and so does the exit-1 report from a fixture missing the
    shared requirement (D.2);
  - an `ast` scan of every module under `mpsim/` finds no import from `agent-coordinator`,
    `coordination_bridge`, `httpx`, `requests`, `urllib.request`, `http.client` or an MCP
    client package (O.4).

  [S]
  **Spec scenarios**: P.4, S.4, D.1, D.2, O.2, O.4
  **Contracts**: openspec/contracts/multiplayer-simulation/cli/mpsim.yaml
  **Design decisions**: D8, D9
  **Dependencies**: 4.4, 5.2
- [ ] 6.2 Implement `mpsim/__main__.py` exactly per the CLI contract: the `list` and `run`
  commands, the four `run` flags, and exit codes 0, 1, 2 and 64. [S]
  **Dependencies**: 6.1

## 7. gen-eval pack and offline guarantees

- [ ] 7.1 Generate `evaluation/descriptor.yaml` with
  `packages/gen-eval/scripts/generate_tool_descriptor.py --contract
  openspec/contracts/multiplayer-simulation/cli/mpsim.yaml --out
  skills/tests/multiplayer-simulation/evaluation/descriptor.yaml`. Add a test that runs the
  same command with `--check` and expects exit 0 on the committed file and non-zero on a
  mutated copy in `tmp_path` (G.4). [S]
  **Spec scenarios**: G.4
  **Design decisions**: D3, D8
  **Dependencies**: 1.2, 1.3
- [ ] 7.2 Author `evaluation/scenarios/*.yaml` as gen-eval CLI-transport scenarios:
  - one for each of the four named scenarios. Each pins its baseline in `expect.body` and
    carries a comment naming `ri-06` (collision) or `ri-11` (blocked ticks) as the item that
    flips it;
  - usage-error scenarios that exercise `--probe`, `--tick-budget` and `--fixture-dir`, so
    every contracted flag is a covered unit.

  Add `evaluation/coverage-exclusions.yaml` only if a unit genuinely cannot be exercised, and
  give that unit a written reason. [M]
  **Spec scenarios**: G.1, C.1, C.2, B.1, B.2
  **Design decisions**: D8
  **Dependencies**: 6.2, 7.1
- [ ] 7.3 Write `test_gen_eval_pack.py`:
  - run the `gen-eval` console script on `evaluation/descriptor.yaml` with
    `--fail-threshold 1.0`, with `bin/` prepended to `PATH` and the harness root as the
    working directory, and expect exit 0 (G.1);
  - copy the pack to `tmp_path`, flip the collision expectation to `true`, and expect exit 1
    with the scenario named in the report (G.2);
  - scan the scenario files and check that every file pinning `collision_detected` names
    `ri-06` in a comment, and every file pinning `blocked_ticks` names `ri-11` (G.3).

  [M]
  **Spec scenarios**: G.1, G.2, G.3
  **Design decisions**: D3, D8
  **Dependencies**: 7.2

## 8. Archive stability and documentation

- [ ] 8.1 Write `test_archive_stability.py`. Every `sim-` change id used by any fixture must be
  absent from the repository's real change ids, active and archived, read the same way
  `skills/tests/openspec_paths/test_change_path_stability.py` reads them (A.2). Run that guard
  and expect no violation under `skills/tests/multiplayer-simulation/` (A.1). A.3 holds by
  construction: harness tests read change artifacts only through `change_dir()` and contracts
  only from promoted paths. Record that in the test module docstring. [S]
  **Spec scenarios**: A.1, A.2, A.3
  **Design decisions**: D10
  **Dependencies**: 7.3
- [ ] 8.2 Write `skills/tests/multiplayer-simulation/README.md`. It should cover:
  - what the harness measures and why baselines are characterisations, not targets;
  - how `ri-06` registers a probe (one import line plus flipping `collision_detected`);
  - where `ri-11` must look: the `Roadmap.ready_items` call site in `scenarios/blocked.py`,
    the fixture dependency form, and the pinned `blocked_ticks`;
  - how to add a scenario module and fixture;
  - how to run the suite locally.

  Do not edit `docs/guides/multiplayer-collaboration.md`, which belongs to `ri-01`. [S]
  **Design decisions**: D4, D5
  **Dependencies**: 7.3

## 9. Verification

- [ ] 9.1 Run the following and record their results in the validation report:
  - the harness directory with `pytest`, recording its wall time against the 30-second
    budget;
  - `skills/tests/ci_coverage/` and `skills/tests/openspec_paths/`;
  - `ruff check` over the harness;
  - `openspec validate multiplayer-simulation-harness --strict`.

  [XS]
  **Dependencies**: 8.1, 8.2

## Dependency Graph Summary

```
1.3 ─────────────────────────────────────┐
1.4 ─► 1.1 ─► 1.2 ─┬───────────────────► 7.1 ─┐
 │                 │                          │
 ├─► 2.1 ─► 2.2 ─► 2.3 ─► 2.4 ─► 2.5 ─► 2.6 ─┬─► 4.1 ─► 4.2 ─► 4.3 ─► 4.4 ─┐
 │                                            └─► 5.1 ─► 5.2 ──────────────┴─► 6.1 ─► 6.2 ─► 7.2 ─► 7.3 ─┬─► 8.1 ─┬─► 9.1
 └─► 3.1 ─► 3.2 ─────────────────────────────────► (4.1)                                                └─► 8.2 ─┘
```

Independent roots: 1.3, 1.4. Max parallel width: 3, reached twice: {2.x chain, 3.x, 1.1→1.2}
early, and {4.x, 5.x, 7.1} mid-change. File overlap: none between parallel-safe groups.
Scenario modules self-register through `pkgutil` discovery (1.4), so 4.4 and 5.2 never edit
the same file.
