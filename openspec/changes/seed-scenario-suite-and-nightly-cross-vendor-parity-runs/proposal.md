# Seed scenario suite and nightly cross-vendor parity runs

Roadmap: `roadmap-always-on-agent-automation`, item **ri-16** (depends on ri-15,
`build-agent-trajectory-scenario-harness`, merged).

## Why

ri-15 shipped the agent trajectory scenario harness (`packages/agent-scenarios/`):
scenario YAML model, deterministic goal-gate scorer, additive LLM judge, an
injectable `ScenarioExecutor` with `CLIVendorExecutor` and `FakeExecutor`, a runner
that builds a `ParityMatrix`, and a findings emitter. It deliberately stopped short of
the parts that make the harness *pay off* (its `tasks.md` §10 defers them here):

- **Coverage** — only two seed scenarios exist (`plan-feature-basic`,
  `implement-feature-basic`); nothing exercises validate or merge skills.
- **Cadence** — `python -m agent_scenarios` is a lister/validator. There is no
  command that runs the suite end-to-end, no schedule, and no guard rails
  (off-switch, spend/size cap) that an unattended nightly run needs.
- **Feedback** — findings are written to a JSON file that nobody reads. The
  `/improve-harness` capability-gap pipeline never sees a scenario failure, so a skill
  regression caught by the harness does not become an improvement signal.
- **Trend** — a parity matrix is produced and discarded. There is no way to ask
  "how has `validate-feature` been doing on `codex` over the last two weeks?", which
  is the signal the roadmap wants to eventually gate dispatcher routing on.
- **Sensitivity to skill changes** — the live executor runs a vendor CLI in a bare
  fixture repo; nothing puts the *skill under test* (from the checkout being
  evaluated) into that workspace, so a broken skill change would not reliably show up
  in the suite at all.

## What Changes

1. **Seed suite (11 scenarios)** — 9 new scenarios plus the 2 existing ones, covering
   the four skill families: plan (3), implement (3), validate (3), merge (2). Every
   scenario declares at least 2 vendors. Each scenario ships with a scripted *golden*
   and *broken* `FakeExecutor` outcome so the test suite proves its gates are both
   satisfiable and discriminating. A suite-coverage guard test enforces the ≥10 /
   all-four-families / ≥2-vendors floor. `implement-feature-basic` is revised to gate
   on a push to a local bare `origin` instead of a real GitHub PR.
2. **Harness extensions for live runs** — fixture `local_remote` (a sibling bare repo
   wired as `origin`, so push/merge skills never touch GitHub) with seeded `prs:`; a
   small `gh` shim on every live run's `PATH` backed by that local origin, so the
   merge-family skills (which require `gh`) run without GitHub and unsupported `gh`
   calls surface as infrastructure errors; materialization of the **whole skills
   tree** from a configurable `skills_root` (skills reference siblings via
   `<skill-base-dir>/../`) into the workspace's `.claude/skills/` and
   `.agents/skills/`; and a hermetic vendor environment — GitHub and coordinator
   credentials and every coordinator address/credential variable scrubbed by a
   built-in denylist that config can extend but not shrink, `COORDINATION_API_URL`
   forced to an unreachable sentinel so fixture agents run standalone and never write
   to the live coordinator; every seed prompt explicitly invokes its skill under test;
   a timeout reported distinctly from a missing CLI.
3. **Durable results store + query CLI** — an append-only, schema-versioned JSONL
   store (one record per run × scenario × vendor, plus a run-summary record) and
   `agent-scenarios results {query,trend,latest}` filtering by vendor, skill, skill
   family, scenario and time window.
4. **Capability-gap emission** — each deterministic scenario *failure* (not an
   executor/infra error) becomes an episodic-memory entry using the shared D4 tag
   schema with a new `source:scenario-parity` value, written through the coordinator
   `POST /memory/store` path with an offline JSONL spool fallback and a `gaps flush`
   replay command. `/improve-harness` needs no source-specific code, but its memory
   query is repaired to match the live `POST /memory/query` contract (`agent_id`, API
   key, `memories` envelope) — today it would never read the emitted gaps; the new
   source value is documented in the memory conventions and tag-convention tests.
5. **Nightly runner** — `agent-scenarios nightly --config <file>` orchestrating: spool
   flush → suite load → vendor allowlist → cap check → run → results append →
   findings file → capability gaps. Explicit off-switch (config `enabled: false` by
   default *and* a kill-file), per-run size/spend caps (max scenario×vendor pairs,
   max pairs per vendor, wall-clock budget, per-pair timeout), a run lock against
   overlapping runs, incremental result appends (a killed run keeps its completed
   pairs), bounded workspace retention, a `--dry-run` that works while still disabled,
   and exit codes that distinguish skill failures (1) from a non-green night without
   skill failures — infrastructure errors or a budget-exhausted, incomplete matrix
   (3) — and config/cap errors (2).
6. **Deploy templates, not deployments** — systemd user `.service`/`.timer`
   *templates* and an example config under `packages/agent-scenarios/deploy/`, plus a
   runbook. Nothing is installed or enabled by this change.

### Out of scope

- **Incident auto-seeding** (auto-rollback / ESCALATE / holdout failure → draft
  scenario) — roadmap item ri-17, `auto-seed-scenarios-from-incidents`.
- **Dispatcher routing gate** on parity results ("skill changes must pass the parity
  suite before the dispatcher routes real work through them") — this change provides
  the queryable signal (`results latest`) but does not wire any gate.
- Installing/enabling the timer on the GX10, and the first live nightly run — operator
  tasks, listed unchecked in `tasks.md`.
- Running paid vendor matrices during implementation or CI — all tests use
  `FakeExecutor`.
- Any change to trust posture (`TRUST_POSTURE.md`).

## Approaches Considered

### Approach 1: Package-local nightly runner + JSONL results store + memory-path gaps (Recommended)

Everything lives in `packages/agent-scenarios/`: a `nightly` subcommand driven by a
YAML config, an append-only JSONL results store with a query CLI, and a gap emitter
that writes D4-tagged entries via the coordinator HTTP memory API (spool on failure).
Scheduling is a systemd user timer template.

- **Pros**: no DB migration and no coordinator change; the store is a plain file that
  survives coordinator outages and is trivially backed up/inspected; `/improve-harness`
  consumes the gaps through the path it already queries; scale is tiny
  (~11 scenarios × 2–3 vendors × 365 nights ≈ 12k records/year, a full scan is
  milliseconds); fits the ri-15 "library is the product" shape; fully testable with
  `FakeExecutor`.
- **Cons**: trend queries are local to the GX10 host that owns the file; no SQL;
  concurrent writers need a lock (a single nightly writer makes this moot).
- **Effort**: M

### Approach 2: Coordinator-owned results table + API endpoints

Add a `scenario_results` table (migration), `POST/GET /scenario-results` endpoints,
and have the nightly runner write through the coordinator.

- **Pros**: queryable from any host and from other coordinator features (status
  surface, dispatcher gate); SQL aggregation.
- **Cons**: a migration, API contract, auth/policy work and throwaway-DB migration
  tests for a single-writer, low-volume dataset; nightly results are lost whenever the
  coordinator is down unless a spool is added anyway; widens the change across two
  architectural boundaries.
- **Effort**: L

### Approach 3: CI-hosted nightly workflow (GitHub Actions `schedule:`) with artifacts

A scheduled workflow runs the suite and uploads results as workflow artifacts.

- **Pros**: no host configuration; run history visible in the Actions UI.
- **Cons**: needs vendor CLI credentials in CI secrets (trust-posture change);
  hosted runners lack the GX10 vendor setup; artifact retention is time-boxed and not
  queryable; self-hosted GX10 runners (the roadmap's CI-migration item) are not in place yet.
- **Effort**: M

### Selected Approach

**Approach 1** (autonomous planning, recorded in `design.md` → "Assumptions
(autonomous planning)"). It satisfies "queryable per vendor per skill over time" with
the simplest durable store, avoids a DB migration and any trust-posture change, and
keeps every moving part testable in-container. The store is behind a small
`ResultsStore` interface so a later change can add a coordinator-backed implementation
(Approach 2) if a cross-host consumer (operator status surface, dispatcher gate)
materialises; the JSONL file would then become its import source. Approach 3 is
rejected primarily on trust posture (vendor keys in CI).

## Impact

- **Code**: `packages/agent-scenarios/` (new modules `suite.py`, `materialize.py`,
  `gh_shim.py`, `results_store.py`, `results_cli.py`, `gap_emitter.py`, `nightly.py`; extensions to `models.py`,
  `executor.py`, `__main__.py`; new `schemas/`; new `deploy/`; 9 new scenarios).
- **Skills/docs**: `skills/improve-harness/scripts/analyze_failures.py` (memory query
  repaired to the live API contract),
  `docs/guides/memory-conventions.md` (new `source:scenario-parity`),
  `skills/session-log/tests/test_memory_tag_conventions.py` (vocabulary constant),
  `skills/improve-harness/SKILL.md` (data-sources table row),
  `skills/tests/improve-harness/` (consumer test of the new source),
  `docs/guides/agent-scenarios-nightly.md` (runbook).
- **Specs**: `agent-trajectory-harness` (ADDED requirements), `harness-engineering`
  (ADDED requirement for the scenario-parity source; the in-flight
  `add-a-judged-first-stage-to-coordinator-audit-triage` MODIFIES
  "Capability Gap Detection", so this change adds rather than modifies to avoid a
  delta collision).
- **No** database migration, coordinator API change, CI workflow change, or trust
  posture change.
- **Archive order**: ri-15 (`build-agent-trajectory-scenario-harness`) is merged but
  not archived; it must archive first so its `agent-trajectory-harness` capability
  spec exists before this change's ADDED requirements merge into it (task 6.4).

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Cost control | scenario×vendor pairs launched per nightly run | ≤ `caps.max_pairs` (default 30); over-cap plan refuses to start | unit tests (wp-nightly), validate-feature |
| Cost control | wall-clock per nightly run | stops launching new pairs after `caps.max_wall_clock_minutes` (default 240) | unit tests with fake clock |
| Operability | off-switch | `enabled: false` or kill-file present → exit 0, no executor call, a `disabled` run record | unit tests |
| Resilience | coordinator unreachable during gap emission | 0 gaps lost: all spooled, replayed by next run | unit tests |
| Resilience | run killed mid-way | every completed pair's `result` record retained | unit tests (simulated kill) |
| Hermeticity | vendor subprocess environment | no GitHub/coordinator credential or address variable (built-in denylist, not removable by config); `COORDINATION_API_URL` = sentinel always; `gh` resolves to the shim | unit tests |
| Operability | infrastructure-only failure or budget-exhausted night | exit 3 (unit marked failed), 0 capability gaps | unit tests |
| Resource bound | kept workspaces | ≤ `retain_failed_runs` (default 7) run directories | unit tests |
| Performance | `results trend` over 15k records | < 2 s on the GX10 | integration test with synthetic 15k-record store (< 2 s budget on CI hardware) |
| Compatibility | record schema | every record carries `schema_version`; readers skip unknown future versions with a warning | unit tests |
