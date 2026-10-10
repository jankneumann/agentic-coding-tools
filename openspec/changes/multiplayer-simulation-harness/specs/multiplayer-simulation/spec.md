## ADDED Requirements

### Requirement: Simulated Principals Have Separate Identities, Worktrees, And Agents

The simulation harness SHALL build a world containing one local bare git repository as the
shared remote and two or more simulated principals. Each principal SHALL have a distinct git
author identity (name and an `@sim.invalid` email), its own clone of the shared remote, its
own git worktree per simulated change, and its own scripted agent with a distinct agent id.
A principal SHALL observe another principal's work only through commits pushed to the shared
remote.

#### Scenario: Two principals act under separate identities and worktrees

- **WHEN** a scenario with principals `alice` and `bob` runs and each principal's agent
  commits one simulated change
- **THEN** every commit reachable from `alice`'s change branch but not from `main` has
  author `alice <alice@sim.invalid>`
- **AND** every commit reachable from `bob`'s change branch but not from `main` has author
  `bob <bob@sim.invalid>`
- **AND** the two principals' worktree paths are different directories
- **AND** the report's `principals` array lists both principals with distinct `agent_id`
  values

#### Scenario: Unpushed work is invisible to other principals

- **WHEN** `alice` commits a change in her worktree without pushing it
- **AND** `bob` fetches from the shared remote
- **THEN** `bob`'s clone contains no ref or commit from `alice`'s unpushed change

#### Scenario: A world with three principals is supported

- **WHEN** a test builds a world with three principals
- **THEN** three distinct identities, clones and agent ids are created, and the world builds
  without error

#### Scenario: Fewer than two principals is rejected

- **WHEN** `mpsim run` is invoked with `--fixture-dir` pointing at a fixture that declares
  one principal
- **THEN** the process exits with code 64
- **AND** stderr names the minimum of two principals

### Requirement: Same-Requirement Collision Scenario Records Plan-Time Detection

The harness SHALL provide a scenario `same-requirement-collision`. In it, one principal pushes
a simulated OpenSpec change whose spec delta modifies requirement R of a seeded capability.
A second principal then plans a simulated change whose spec delta modifies the same
requirement R. At the second principal's plan step the harness SHALL record:

- `collision_present`: computed by a ground-truth oracle from fixture contents;
- `collision_detected`: true only when a registered collision probe reported a
  requirement-level collision against the first principal's change;
- `probes`: one entry per collision probe that ran.

The scenario SHALL pin the baseline in force at the time of this change: `collision_present`
is `true`, `collision_detected` is `false`, and `probes` is empty. A companion control scenario
`different-requirement-control` SHALL have the two principals modify different requirements.

#### Scenario: Baseline collision is present but not detected

- **WHEN** `mpsim run --scenario same-requirement-collision` runs with no collision probe
  registered
- **THEN** the process exits 0
- **AND** the report has `collision_present: true`, `collision_detected: false`, and
  `probes: []`

#### Scenario: Different requirements produce no collision

- **WHEN** `mpsim run --scenario different-requirement-control` runs
- **THEN** the process exits 0
- **AND** the report has `collision_present: false` and `collision_detected: false`

#### Scenario: A fixture that loses the shared requirement fails loudly

- **WHEN** `mpsim run --scenario same-requirement-collision` is invoked with `--fixture-dir`
  pointing at a copy of its fixture altered so the two spec deltas no longer name the same
  requirement heading
- **THEN** the process exits 1
- **AND** the report's `error` field states that the scenario's required collision is
  absent from the fixture

### Requirement: Plan-Time Detectors Attach Through A Probe Seam

The harness SHALL invoke plan-time collision detectors only through a `CollisionProbe`
interface. That interface SHALL consist of a `probe_id`, and a `detect` operation that
receives a read-only view of the planning principal's worktree and the shared remote URL and
returns a result with `status` (`ok` or `error`), `collisions` (each with `level`,
`other_change` and `requirement`), and an optional `error` message. Registering a new probe
SHALL NOT require editing any scenario definition other than its pinned expectations. A probe
that raises an exception or exceeds its timeout SHALL be recorded with `status: error`, and
the scenario SHALL still complete.

#### Scenario: A registered probe that reports a collision flips detection

- **WHEN** a test registers a stub probe that reports one requirement-level collision
  against the first principal's change
- **AND** runs the `same-requirement-collision` scenario
- **THEN** the report has `collision_detected: true`
- **AND** `probes` contains one entry with the stub's `probe_id` and `status: ok`

#### Scenario: A failing probe is recorded and does not abort the run

- **WHEN** a test registers a probe whose `detect` raises an exception
- **AND** runs the `same-requirement-collision` scenario
- **THEN** the process exits 0
- **AND** `probes` contains that probe with `status: error` and a non-empty `error`
- **AND** `collision_detected` is `false`

#### Scenario: A probe that exceeds its timeout is recorded as an error

- **WHEN** a test registers a probe whose `detect` does not return within the per-probe
  timeout
- **THEN** the run completes, and that probe is recorded with `status: error` and an `error`
  that names the timeout

#### Scenario: Registering a probe edits no scenario definition

- **WHEN** a test registers a new stub probe through the registry
- **AND** runs every built-in scenario
- **THEN** no file under `mpsim/scenarios/` or `evaluation/scenarios/` was modified
- **AND** the stub's `probe_id` appears in `probes` of both collision scenarios

#### Scenario: Probe selection rejects unknown probe ids

- **WHEN** `mpsim run --scenario same-requirement-collision --probe does-not-exist` is invoked
- **THEN** the process exits 64
- **AND** stderr names the unknown probe id

### Requirement: Memory-Store Scenario Reports Time Blocked On Dependency

The harness SHALL provide a scenario `memory-store-blocked-dependency` that reproduces the
dependency half of the motivating memory-store incident. Principal `retrieval-owner` owns a
roadmap item that depends on an item owned by principal `storage-owner`. The scenario SHALL
advance a logical tick clock using step durations declared in the fixture. On each tick it
SHALL decide whether the dependent item is ready by calling the roadmap-runtime admission
rule (`Roadmap.ready_items`) on the `roadmap.yaml` at the shared remote's `main`, the
integration ref. The harness SHALL NOT use readiness logic of its own. Simulated principals
SHALL NOT edit `roadmap.yaml` on their change branches and SHALL NOT push to `main`; every
roadmap status change SHALL be committed to `main` by a simulated supervisor step (the status
applier) authored as `sim-supervisor`. Every status change SHALL be declared as data in the
fixture's step script, never in harness code. Within a tick, the status changes of steps
finishing at that tick SHALL be committed to `main` before any waiting principal evaluates
readiness. For each principal, the report SHALL
include `blocked_ticks`, defined as the first tick at which its implement step is admitted
minus the tick at which its own preceding steps finished, and `unblocked` (boolean). The
scenario SHALL pin the baseline in force at the time of this change:
`blocked_ticks.retrieval-owner` equals 10 and `blocked_ticks.storage-owner` equals 0, under
the fixture durations recorded in design D5. A companion control scenario
`independent-principals-control` SHALL have no dependency between the principals.

#### Scenario: Baseline dependent principal is blocked until the dependency is implemented

- **WHEN** `mpsim run --scenario memory-store-blocked-dependency` runs
- **THEN** the process exits 0
- **AND** the report has `blocked_ticks` of `{"retrieval-owner": 10, "storage-owner": 0}`
  and `unblocked` of `true` for both principals

#### Scenario: Independent principals are never blocked

- **WHEN** `mpsim run --scenario independent-principals-control` runs
- **THEN** every principal's `blocked_ticks` is 0

#### Scenario: A dependency that never completes is bounded by the tick budget

- **WHEN** the scenario runs with `--tick-budget 5`, which is lower than the dependency's
  completion tick
- **THEN** the process exits 0
- **AND** the report has `final_tick` equal to 5, `unblocked.retrieval-owner` equal to
  `false`, and
  `blocked_ticks.retrieval-owner` equal to 4 (the budget minus its earliest start tick)

#### Scenario: Status transitions reach only the integration ref

- **WHEN** `mpsim run --scenario memory-store-blocked-dependency` completes
- **THEN** no commit reachable from any `sim/*` branch but not from the seed commit modifies
  `roadmap.yaml`
- **AND** every commit on `main` after the seed is authored by `sim-supervisor`
- **AND** `roadmap.yaml` at `main` shows both items with status `completed`

#### Scenario: Status transitions are declared only in fixture data

- **WHEN** the harness driver package `mpsim/` is scanned statically
- **THEN** no module contains a roadmap status literal (`approved`, `in_progress`,
  `completed`) used as a `set_status` value
- **AND** running the scenario with a `--fixture-dir` copy whose implement step declares no
  `on_finish.set_status` leaves `unblocked.retrieval-owner` equal to `false`

#### Scenario: Readiness comes from the admission rule, not the harness

- **WHEN** the scenario is run with `--fixture-dir` pointing at a copy of its fixture whose
  roadmap gives the dependency item status `completed` at tick 0
- **THEN** `blocked_ticks.retrieval-owner` is 0, because `Roadmap.ready_items` admits the
  dependent as soon as its own plan step finishes

### Requirement: Scenarios Run Offline Without A Shared Coordinator

Every harness scenario SHALL complete with no network access and no coordinator. The shared
remote SHALL be a local `file://` bare repository. The harness SHALL NOT import
agent-coordinator or coordination-bridge modules, SHALL NOT use HTTP or MCP transports, and
SHALL produce the same report whether or not coordinator environment variables are set. The
harness test suite SHALL run in the skills CI sweep with no services started.

#### Scenario: Scenarios pass with network sockets blocked

- **WHEN** the harness test suite runs with `AF_INET` and `AF_INET6` socket connections
  patched to raise
- **THEN** every scenario test passes

#### Scenario: The driver imports no coordinator or transport modules

- **WHEN** every module under `mpsim/` is parsed with `ast`
- **THEN** none imports a module from `agent-coordinator`, `coordination_bridge`, an HTTP
  client (`httpx`, `requests`, `urllib.request`, `http.client`) or an MCP client

#### Scenario: Coordinator environment variables do not change the outcome

- **WHEN** `mpsim run` is executed for every scenario once with `COORDINATION_API_URL`
  unset, and once with it set to `http://127.0.0.1:9`
- **THEN** each scenario's two stdout payloads are byte-identical

#### Scenario: The harness test directory is reached by CI

- **WHEN** the CI coverage guard `skills/tests/ci_coverage/test_ci_test_coverage.py` runs
- **THEN** it passes with `tests/multiplayer-simulation` listed in the in-skill sweep of
  `.github/workflows/ci.yml`

### Requirement: Scenario Reports Are Deterministic

The harness SHALL emit each scenario report as a single JSON object on stdout that validates
against `openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json`. The JSON
SHALL be serialized with sorted keys. Fields that do not apply to a scenario SHALL be present
with value `null`. Reports SHALL NOT contain absolute paths, temporary directory names,
commit SHAs or wall-clock timestamps. Two runs of the same scenario with the same arguments
SHALL produce byte-identical output.

#### Scenario: Repeated runs are byte-identical

- **WHEN** `mpsim run --scenario memory-store-blocked-dependency` runs twice, each time with
  a different `TMPDIR`, so that the two simulated worlds live in different directories
- **THEN** the two stdout payloads are byte-identical

#### Scenario: Reports leak no host-specific values

- **WHEN** any scenario report is produced, including an exit-1 report with a non-null
  `error`
- **THEN** it validates against `sim-report.schema.json`
- **AND** it does not contain the temporary world directory path, nor any 40-character
  hexadecimal string

### Requirement: Scenario Pack Runs Through gen-eval

The harness scenarios SHALL be declared as gen-eval CLI-transport scenarios under
`skills/tests/multiplayer-simulation/evaluation/scenarios/`. They SHALL run against a
ToolDescriptor generated from the CLI contract
`openspec/contracts/multiplayer-simulation/cli/mpsim.yaml`. The pack SHALL run at
`--fail-threshold 1.0`. Each pinned baseline value in a scenario file SHALL carry a comment
naming the roadmap item expected to change it.

#### Scenario: The pack passes against the baseline

- **WHEN** the harness test `test_gen_eval_pack.py` runs gen-eval on
  `evaluation/descriptor.yaml` at `--fail-threshold 1.0`
- **THEN** gen-eval exits 0
- **AND** its report shows every scenario in the pack passing, including
  `same-requirement-collision`, `different-requirement-control`,
  `memory-store-blocked-dependency` and `independent-principals-control`

#### Scenario: A changed measurement fails the pack

- **WHEN** a pinned expectation in a scenario file is changed to a value the driver does not
  produce (for example `collision_detected: true` while no probe is registered)
- **THEN** gen-eval exits 1 and its report names the failing scenario

#### Scenario: Every pinned baseline names the item that flips it

- **WHEN** the pack's scenario files are scanned for pinned `collision_detected` or
  `blocked_ticks` expectations
- **THEN** each file that pins `collision_detected` contains a comment naming `ri-06`
- **AND** each file that pins `blocked_ticks` contains a comment naming `ri-11`

#### Scenario: The descriptor cannot drift from the contract

- **WHEN** `generate_tool_descriptor.py --check` runs with the harness contract and
  descriptor paths
- **THEN** it exits 0 on the committed descriptor and non-zero if the descriptor differs
  from what the contract generates

### Requirement: Scenario Tests Are Archive-Stable

Harness tests SHALL NOT hold a literal path to any real OpenSpec change directory. Tests that
read this change's artifacts SHALL resolve them with `change_dir()` from `openspec_paths`. The
harness SHALL read its CLI contract and report schema from their promoted paths under
`openspec/contracts/multiplayer-simulation/`. Simulated changes inside fixture worlds SHALL
use synthetic change ids prefixed `sim-` that are not real change ids of the repository.

#### Scenario: The path-stability guard passes

- **WHEN** `skills/tests/openspec_paths/test_change_path_stability.py` runs with the harness
  present
- **THEN** it reports no violation in `skills/tests/multiplayer-simulation/`

#### Scenario: Fixture change ids are synthetic

- **WHEN** the harness test that compares fixture change ids against the repository's real
  change ids (active and archived) runs
- **THEN** no fixture change id matches a real change id

#### Scenario: Harness tests survive archival of this change

- **WHEN** this change's directory is moved to `openspec/changes/archive/<date>-multiplayer-simulation-harness/`
- **THEN** the harness tests still pass without edits
