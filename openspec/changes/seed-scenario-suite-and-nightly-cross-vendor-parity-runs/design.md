# Design: Seed scenario suite and nightly cross-vendor parity runs

## Context

ri-15 (`build-agent-trajectory-scenario-harness`) built the harness library in
`packages/agent-scenarios/`. Its learnings that constrain this design:

- The **deterministic goal-gate scorer is authoritative**; the LLM judge is additive
  and skip-never-fail. Nothing in this change lets a judge verdict create a
  capability gap or change a pass/fail.
- `command` gates resolve `python` to `sys.executable`.
- Live multi-vendor runs happen on the **GX10** with real CLIs; in-container and CI
  tests use `FakeExecutor`.
- `run_scenario` already distinguishes `deterministic_status` `pass | fail | error`,
  where `error` means the executor (CLI missing, non-zero exit, fixture failure)
  failed — that is infrastructure, not skill quality.

Data flow after this change:

```
nightly config ──► nightly.run()
                     │ 1. off-switch / kill-file / run lock
                     │ 2. flush gap spool (previous offline run)
                     │ 3. load suite, apply vendor allowlist, plan pairs
                     │ 4. cap check (max_pairs, per-vendor) — refuse if over
                     │ 5. run pairs (CLIVendorExecutor, skills_root, env scrub,
                     │    wall-clock budget → remaining pairs skipped_budget)
                     ├──► results_store.append(records)        (JSONL, trend)
                     ├──► findings_emitter.emit_findings(...)  (review-findings JSON)
                     └──► gap_emitter.emit(fail verdicts)      (memory API | spool)
                                          │
                       /improve-harness ◄─┘ (POST /memory/query, source:scenario-parity)
```

## Decisions

### D1 — Package-local runner and stores (Approach 1)

All new runtime code lives in `packages/agent-scenarios/` as library modules with
thin CLI subcommands. Rationale and rejected alternatives are in `proposal.md`
(Approaches Considered). The coordinator is only a *consumer-facing sink* for
capability gaps through an endpoint that already exists (`POST /memory/store`).

### D2 — Results store: append-only JSONL behind a `ResultsStore` interface

**Choice**: one JSONL file (default `$XDG_STATE_HOME/agent-scenarios/results.jsonl`,
override via config `results.path` or `--store`). Two record types, both carrying
`schema_version: 1` and `record_type`:

- `result` — one per (run_id, scenario_id, vendor): `recorded_at`, `run_id`,
  `scenario_id`, `skill_under_test`, `skill_family`, `vendor`,
  `deterministic_status` (`pass | fail | error | skipped_budget`), `failed_gates`
  (ids), `trajectory_status`, `duration_seconds`, `repo_sha`, `skills_sha`, `error`.
- `run` — one per nightly invocation: `run_id`, `started_at`, `finished_at`,
  `status` (`completed | disabled | cap_exceeded | budget_exhausted | locked`),
  `planned_pairs`, `executed_pairs`, `config_digest`, `vendors`.

**Why not SQLite**: SQLite would also work, but at ~12k records/year a full scan is
cheap; JSONL is append-only by construction (no in-place updates, no migrations),
diffable, greppable, trivially rotated/backed up, and readers can tolerate partial
last lines from a crash. **Why not a coordinator table**: no cross-host consumer
exists yet; a migration + API + throwaway-DB tests is disproportionate for a
single-writer dataset (gatekeeper guidance: simplest durable store). The
`ResultsStore` protocol (`append(records)`, `iter_records(filters)`) leaves room for a
coordinator-backed implementation later.

**Write safety**: appends take an exclusive `fcntl.flock` on the store file and write
whole lines with a trailing newline in one `write` + `fsync`; readers skip a
trailing partial line and records with an unknown `schema_version` (warning, not
error).

**Queries** (`agent-scenarios results ...`):
- `query --vendor V --skill S --family F --scenario ID --since ISO --until ISO
  [--status ...] [--format json|table]` — raw matching `result` records.
- `trend --group-by vendor,skill|vendor,family|scenario,vendor --bucket day|week
  [filters]` — pass rate, counts per bucket (errors and `skipped_budget` reported
  separately and excluded from the pass-rate denominator).
- `latest [filters]` — most recent result per (scenario, vendor); the signal a
  future dispatcher gate would read.

### D3 — Capability-gap emission: `source:scenario-parity` via the memory API, spool fallback

For every `VendorRunVerdict` with `deterministic_status == "fail"` the gap emitter
builds one entry:

```
event_type: "capability_gap"
summary:    "[<vendor>] scenario <scenario_id> failed gates: <gate ids>"
session_id: "<run_id>"
details:    {scenario_id, vendor, failed_gates:[{gate_id, detail}], skills_sha, repo_sha}
tags:
  - capability_gap                              # bare tag: what analyze_failures queries
  - capability_gap:scenario-parity/<scenario_id>/<first failed gate id>
  - failure_type:verification_failed
  - affected_skill:<skill_under_test>
  - severity:high
  - source:scenario-parity
  - vendor:<vendor>
  - scenario:<scenario_id>
```

Notes:
- **Bare `capability_gap` tag**: `analyze_failures.query_memory` posts
  `tags: ["capability_gap"]` and the coordinator's recall matches tags by exact array
  overlap (`tags && p_tags`), so a prefixed tag alone would not be returned. Adding
  the bare tag is harmless to `_extract_tag` (it only reads `prefix:`-tags).
- **Stable `capability_gap` value** (`scenario-parity/<scenario>/<gate>`) so
  `/improve-harness` groups repeated nightly failures of the same gate into one
  finding whose frequency rises night over night. Dedup key
  `(capability_gap, affected_skill, session_id)` with `session_id = run_id` keeps one
  entry per run.
- **Only `fail` emits gaps.** `error` (CLI missing, timeout, fixture failure) and
  `skipped_budget` are infrastructure outcomes: recorded in the results store and the
  run summary, never as skill capability gaps. Judge findings never emit gaps (D3 of
  ri-15: judge is additive).
- **Severity `high`** for every deterministic failure (gates are explicit contract
  violations); not `critical`, which the D4 schema reserves for incidents.
- **Sinks** (`MemorySink` protocol): `CoordinatorMemorySink` — stdlib `urllib` POST to
  `${COORDINATOR_URL}/memory/store` with `X-API-Key: ${COORDINATION_API_KEY}` and
  `agent_id` from config (default `agent-scenarios-nightly`); `SpoolMemorySink` —
  appends the identical payload to `<state>/gap-spool.jsonl`. The emitter tries the
  coordinator and spools any entry that fails. `agent-scenarios gaps flush` (also run
  at the start of every nightly) replays the spool and rewrites it with only the
  entries that still failed. No dependency on `skills/coordination-bridge` (the
  package must stay installable on its own).
- **Shared tag schema**: `source:scenario-parity` is a *new vocabulary value*. It is
  documented in `docs/guides/memory-conventions.md` and added to the
  `SOURCE_VOCABULARY` constant in `skills/session-log/tests/test_memory_tag_conventions.py`
  (the doc's own rule for adding prefixes/values). `vendor:` and `scenario:` are
  auxiliary tags documented there too. The spec delta is an **ADDED** requirement in
  `harness-engineering` rather than a MODIFIED "Capability Gap Detection", because
  the in-flight `add-a-judged-first-stage-to-coordinator-audit-triage` already
  modifies that requirement and two MODIFIED deltas on one requirement collide at
  archive time.
- `/improve-harness` needs **no code change**: it aggregates arbitrary `source:`
  values. A consumer test in `skills/tests/improve-harness/` feeds the emitter's
  example payload (`contracts/capability-gap-entry.example.json`) through
  `normalize_memory_entries` / `rank_findings` and asserts `scenario-parity` appears
  in the source set. The SKILL.md data-sources table gains a row.

### D4 — Nightly runner with an explicit off-switch and caps

`agent-scenarios nightly --config <path> [--dry-run]`. Config (validated by a pydantic
model; JSON schema in `contracts/nightly-config.schema.json`):

```yaml
enabled: false                       # off by default — must be flipped by the operator
disable_file: ~/.config/agent-scenarios/DISABLED   # kill-file: presence disables
scenarios_dir: packages/agent-scenarios/scenarios
repo_root: ~/agentic-coding-tools    # checkout under test (repo_sha, skills_root base)
skills_root: skills                  # relative to repo_root
vendors: [claude, codex]             # allowlist ∩ scenario.vendors; must be ≥ 2
vendor_commands: {claude: "claude -p {prompt} ...", codex: "codex exec {prompt} ..."}
env_scrub: [GH_TOKEN, GITHUB_TOKEN]
caps:
  max_pairs: 30
  max_pairs_per_vendor: 15
  max_wall_clock_minutes: 240
  per_pair_timeout_seconds: 1200
results: {path: ~/.local/state/agent-scenarios/results.jsonl}
findings: {path: ~/.local/state/agent-scenarios/findings/{run_id}.json}
gaps: {enabled: true, spool_path: ~/.local/state/agent-scenarios/gap-spool.jsonl, agent_id: agent-scenarios-nightly}
judge: {enabled: false}
```

Ordered guards (each writes a `run` record with the matching status and exits 0
unless noted):

1. `enabled: false` → `disabled`; **no executor constructed**.
2. `disable_file` exists → `disabled`.
3. Run lock (`flock` on `<state>/nightly.lock`) held → `locked`, exit 0 (overlap is
   expected-benign; systemd also prevents it).
4. Planned pairs = Σ over scenarios of |scenario.vendors ∩ config.vendors|. If
   `> max_pairs` or any vendor `> max_pairs_per_vendor` → `cap_exceeded`, **exit 2,
   nothing launched** (fail-closed rather than silently truncating coverage).
5. Fewer than 2 vendors effective → config error, exit 2.
6. During the run, once elapsed ≥ `max_wall_clock_minutes`, remaining pairs are not
   launched and are recorded `skipped_budget`; run status `budget_exhausted`, exit 0.

**Spend cap rationale**: vendor CLIs do not expose dollar cost synchronously, so the
cap is expressed in launched pairs, wall clock and per-pair timeout — the levers the
runner controls. Dollar accounting belongs to the model-usage-ledger work.

`--dry-run` prints the planned pair list and cap evaluation and exits without
executing (used by the operator before enabling the timer).

Exit codes: 0 success/benign skip, 1 one or more scenario `fail` (so systemd marks
the unit failed and `OnFailure=` hooks can notify), 2 config/cap error.

The runner calls the ri-15 `run_scenario` per scenario but passes a *filtered copy*
of the scenario (vendors ∩ allowlist) and checks the wall-clock budget between
pairs. To check budget between vendors of the same scenario it iterates scenarios ×
vendors itself and builds each `ParityMatrix` from single-vendor runs (the runner's
public API is unchanged).

### D5 — Skill-under-test materialization and sandboxing in the executor

A broken skill change can only fail the suite if the agent actually runs the changed
skill. `CLIVendorExecutor` gains:

- `skills_root: Path | None` — when set, after fixture materialization it copies
  `skills_root/<skill_under_test>/` into `workdir/.claude/skills/<skill>/` and
  `workdir/.agents/skills/<skill>/` (the project-local skill locations the vendor CLIs
  read), plus any skills listed in a new optional scenario field
  `support_skills: [..]`. The copied skills are added to the fixture's
  `.git/info/exclude` so they never appear in agent commits or gate checks.
  `skills_sha` (git HEAD of the repo containing `skills_root`, `+dirty` if modified)
  is recorded on every result.
- `env_scrub: list[str]` — removed from the vendor subprocess environment.
- `timeout_seconds` is fed from `caps.per_pair_timeout_seconds`.

`FixtureSpec` gains `local_remote: bool = false`: create a bare repo at
`<workdir>.origin.git` (sibling, outside the workspace), `git remote add origin`, and
push the base branch. Push/merge skills then operate against a local origin and never
reach GitHub. Gates for these scenarios use `command` checks such as
`git ls-remote origin <branch>` or `git -C ... merge-base --is-ancestor`.

These are model/executor extensions with backward-compatible defaults; existing
scenarios and tests are unaffected.

### D6 — Seed suite composition and self-test

Skill families (constant `SKILL_FAMILIES` in `suite.py`; unknown skills map to
`other`, which does not count toward coverage):

| Family | Skills |
|---|---|
| plan | `plan-feature`, `iterate-on-plan` |
| implement | `implement-feature`, `iterate-on-implementation` |
| validate | `validate-feature` |
| merge | `merge-pull-requests`, `cleanup-feature` |

Suite (11 scenarios, all with `vendors: [claude, codex]` at minimum):

| # | Scenario id | Skill | Discriminating gates (sketch) |
|---|---|---|---|
| 1 | `plan-feature-basic` (existing) | plan-feature | proposal/tasks exist on change branch; source untouched |
| 2 | `plan-feature-spec-delta` | plan-feature | `specs/<cap>/spec.md` has `## ADDED Requirements`, `#### Scenario:`; no `## Requirements` header |
| 3 | `iterate-on-plan-split-fused-task` | iterate-on-plan | fused "X and Y" task in fixture `tasks.md` is split; proposal untouched outside tasks; no source edit |
| 4 | `implement-feature-basic` (revised) | implement-feature | fix + test passes + commit on feature branch + branch pushed to local origin (replaces the GitHub `pr` gate) |
| 5 | `implement-feature-tdd-new-function` | implement-feature | new test file exists and passes; implementation exists; existing tests unmodified |
| 6 | `implement-feature-respects-scope` | implement-feature | change confined to `write_allow` from fixture `work-packages.yaml`; denied path untouched |
| 7 | `validate-feature-flags-failing-test` | validate-feature | validation report records a FAIL status; source NOT modified to make tests pass |
| 8 | `validate-feature-clean-pass` | validate-feature | report has machine-readable `## <Phase>` + `**Status**:` sections and a PASS verdict |
| 9 | `validate-feature-spec-gap` | validate-feature | report names the unimplemented spec scenario; no source edit |
| 10 | `merge-pull-requests-local-merge` | merge-pull-requests | feature commit is ancestor of `origin/main`; original main commit still ancestor (no force-push/rewrite) |
| 11 | `cleanup-feature-archive` | cleanup-feature | change dir moved under `openspec/changes/archive/`; feature branch deleted locally and on origin; main contains the merge |

Each scenario has a **golden** and a **broken** `Outcome` in
`tests/scenario_outcomes/<scenario_id>.py`. The parametrized test asserts golden →
all gates pass and broken → at least one *named* gate fails. This proves every gate
set is satisfiable and discriminating without a vendor. Exact gate regexes and
fixture contents are authored during implementation and pinned by these tests.

Guard test `test_seed_suite.py`: ≥ 10 scenarios; each of the four families has ≥ 2
scenarios; every scenario declares ≥ 2 vendors; every scenario has a golden/broken
outcome module; scenario ids are unique; no scenario uses a `pr` gate (GitHub side
effect) unless it also sets `local_remote` — enforced so live runs never need GitHub.

### D7 — Deploy templates, never deployments

`packages/agent-scenarios/deploy/`:
- `systemd/agent-scenarios-nightly.service.template` — `Type=oneshot`,
  `ExecStart=<uv> run --project <repo>/packages/agent-scenarios agent-scenarios nightly --config %h/.config/agent-scenarios/nightly.yaml`,
  `TimeoutStartSec` = wall-clock cap + margin, `Nice=10`.
- `systemd/agent-scenarios-nightly.timer.template` — `OnCalendar=*-*-* 02:30`,
  `Persistent=false` (a missed night is skipped, not burst-replayed),
  `RandomizedDelaySec=15m`.
- `nightly.example.yaml` — `enabled: false`.
- A runbook `docs/guides/agent-scenarios-nightly.md`: install, dry-run, enable,
  disable (three ways: `systemctl --user disable --now`, kill-file, `enabled: false`),
  query examples, broken-skill drill.

A test asserts the templates contain the placeholder tokens and that the example
config parses with `enabled: false`. Nothing in the change, its tests, or CI calls
`systemctl`.

### D8 — CLI shape

`__main__.py` becomes a subcommand dispatcher while keeping the current flags working:
`agent-scenarios validate --scenarios DIR` (and the legacy
`--scenarios DIR [--validate-only]` form, unchanged behaviour), `nightly`,
`results {query,trend,latest}`, `gaps flush`. Subcommand modules own their own
`add_parser(subparsers)` so packages can be built in parallel without both editing
argument parsing in one file (only `wp-nightly` edits `__main__.py`).

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Coordinator `scenario_results` table + API (Approach 2) | Migration/API/policy surface for a single-writer, low-volume dataset; loses data when coordinator is down unless spooled anyway. Kept as a future `ResultsStore` implementation. |
| GitHub Actions `schedule:` (Approach 3) | Requires vendor keys in CI secrets (trust-posture change); hosted runners lack vendor CLIs. |
| SQLite results file | Viable; rejected for JSONL's append-only/diffable simplicity at this volume. Revisit if records exceed ~1M or ad-hoc SQL is needed. |
| Emit gaps via session-log `### Capability Gaps Observed` | Session logs are per-change markdown in the repo; a nightly host job writing into `openspec/changes/**` would create commits/noise and break `openspec validate` (cf. PhaseRecord incident). |
| Emit gaps via `skills/coordination-bridge` `try_remember` | Would couple the standalone package to the skills tree layout; a 30-line stdlib client is simpler. |
| Truncate the matrix to fit the cap | Silently drops coverage and makes trends incomparable night to night; fail-closed is explicit. |
| Judge findings as capability gaps | Violates ri-15's "judge is additive, never authoritative"; they still go to the findings file. |
| Executor errors as capability gaps | Would blame skills for missing CLIs/keys/timeouts; recorded as `error` in the store instead. |

## Assumptions (autonomous planning)

This plan was produced non-interactively by the supervised autopilot PLAN phase.
Discovery questions were answered from the roadmap item, ri-15's artifacts and the
codebase:

| # | Question | Assumed answer | Basis |
|---|---|---|---|
| A1 | Which skills count as "plan / implement / validate / merge"? | Families in D6; merge = `merge-pull-requests` + `cleanup-feature`. | Skill inventory; roadmap acceptance wording. |
| A2 | Which ≥ 2 vendors nightly? | `claude` + `codex` as the default allowlist (both already declared by the ri-15 seeds); others opt-in via config. | ri-15 seeds; vendor-status availability. |
| A3 | Trend store: file or coordinator table? | Append-only JSONL with query CLI (D2). | Gatekeeper preference for simplest durable store. |
| A4 | How do failures reach `/improve-harness`? | Memory API with new `source:scenario-parity` + spool fallback (D3). | improve-harness data sources; D4 tag schema doc rule for new values. |
| A5 | What is the "spend cap" unit? | Launched pairs, per-vendor pairs, wall clock, per-pair timeout (D4). | CLIs expose no synchronous cost. |
| A6 | Off-switch semantics? | `enabled: false` default **and** a kill-file; timer not installed by the change. | Gatekeeper notes. |
| A7 | Should scenarios touch real GitHub? | No. `local_remote` bare origin; `pr` gates disallowed without it; `GH_TOKEN`/`GITHUB_TOKEN` scrubbed. | Safety; unattended runs. |
| A8 | How is "a deliberately broken skill change fails the suite" proven? | In-container: an acceptance test with a skill-reading fake executor over a temp `skills_root` whose skill is mutated → `fail` → gap entry → improve-harness ranking. Live: operator drill on the GX10 (operator task). | No paid runs in tests. |
| A9 | Schedule time? | 02:30 local, randomized 15 min, non-persistent. | Off-peak for an always-on box; avoid replay bursts. |
| A10 | Dispatcher gating on parity results? | Out of scope; `results latest` provides the signal. | Roadmap item text lists no gating outcome. |
| A11 | Incident auto-seeding? | Out of scope (ri-17). | Caller instruction; ri-15 §10. |

Gate 1 (direction) was resolved autonomously to Approach 1. Gate 2 (plan approval) is
handled by the autopilot orchestrator's recorded `proposal_approval` gate.

## Risks / Trade-offs

- **Live scenario flakiness** — LLM agents are nondeterministic; one failing night is
  weak evidence. Mitigation: stable gap keys so `/improve-harness` ranks by
  frequency; `trend` shows rates, not single results.
- **Skill materialization fidelity** — vendor CLIs may also load user-global skills
  (`~/.claude/skills`), shadowing or supplementing the project copy. Runbook
  instructs running the nightly under a dedicated user/HOME with no global skills;
  `skills_sha` makes attribution explicit.
- **Store locality** — trends are only queryable on the host that owns the file.
  Accepted (single GX10 host); `ResultsStore` seam allows a coordinator backend.
- **New tag vocabulary value** — consumers that enumerate sources (export of shared
  learnings, skill-audit evidence join) will see a new value; they treat `source:` as
  open-ended today (verified in `analyze_failures.rank_findings`). Shared-learnings
  export keeps its own allowlist of prefixes, which includes `source:`.

## Testing strategy

- All unit/integration tests use `FakeExecutor` (or a test subclass); no vendor CLI,
  no network: `CoordinatorMemorySink` is tested against a local
  `http.server` stub; the spool path is tested by pointing at a closed port.
- No DB is touched (no migration in this change), so the `migrated_database`
  throwaway-DB rule does not apply.
- Tests that read change artifacts (e.g. contract example payloads) resolve the change
  directory with `change_dir()` from a vendored `tests/_shared/openspec_paths.py`;
  preferred is to promote schemas into the package (`src/agent_scenarios/schemas/`)
  and test against the package copy.
- `skills/` edits run the skills gate set (pytest for touched skill tests,
  `install.sh --check`, sync of runtime copies).
