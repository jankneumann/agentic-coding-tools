# Tasks: Build agent trajectory scenario harness

> Change ID: `build-agent-trajectory-scenario-harness`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## 1. Package scaffold

- [x] Create `packages/agent-scenarios/` with `pyproject.toml` following the
      `packages/<name>/` convention (uv_build backend, path dependency on
      `gen-eval` for `ExpectBlock` reuse)
- [x] `README.md`, `.gitignore`, `src/agent_scenarios/` layout, `__main__.py` CLI

## 2. Scenario model + loader

- [x] `models.py`: `AgentScenario`, `FixtureSpec`, `GoalGate`, `GoalGatesBlock`
      (mirrors gen-eval `SideEffectsBlock` verify/prohibit), reusing imported
      `ExpectBlock`
- [x] Run-time models: `RunResult`, `WorkspaceState`, `PRRef`, verdicts,
      `ParityMatrix`
- [x] `loader.py`: YAML load + validation + source-path provenance

## 3. Deterministic goal-gate scorer

- [x] `scorer.py`: score `file`/`branch`/`commit`/`pr`/`artifact`/`command`
      gates with no LLM; verify/prohibit polarity; deterministic status rollup
- [x] `command` gate scored via reused gen-eval `ExpectBlock`

## 4. Injectable per-vendor executor

- [x] `executor.py`: `ScenarioExecutor` protocol; `materialize_fixture`
- [x] Real `CLIVendorExecutor` (shells to per-vendor CLI, observes post-run
      state + PR, injected transcript normalizer, degrades cleanly)
- [x] `FakeExecutor` + `Outcome` for tests

## 5. Injectable LLM-judge

- [x] `judge.py`: `TrajectoryJudgeBackend` protocol; `review_trajectory`
      skip-if-absent, additive; consumes normalized `collect-transcripts` events

## 6. Runner + findings emitter

- [x] `runner.py`: loop `scenario.vendors`, score, judge, build `ParityMatrix`
- [x] `findings_emitter.py`: `review-findings.schema.json`-conformant emit with
      producer-side validation + atomic write

## 7. Seed scenarios

- [x] `scenarios/plan-feature-basic.scenario.yaml` (planning skill)
- [x] `scenarios/implement-feature-basic.scenario.yaml` (implementation skill)

## 8. Tests

- [x] Scorer over pass/fail fixtures (all gate kinds, verify/prohibit polarity)
- [x] Scenario YAML validation (valid + invalid cases, ExpectBlock reuse)
- [x] Runner loops all vendors via `FakeExecutor`, per-vendor results
- [x] Findings conform to `review-findings.schema.json` (programmatic validation)
- [x] Judge skips with no backend, contributes with a fake backend
- [x] `CLIVendorExecutor` degradation path (not dead code)

## 9. OpenSpec artifacts + validation

- [x] `proposal.md` (Why / What Changes / Impact)
- [x] `design.md` (deterministic-vs-judge split, injection seams, parity model,
      reuse rationale, GX10 boundary)
- [x] Spec delta `specs/agent-trajectory-harness/spec.md` (ADDED requirements)
- [x] `openspec validate build-agent-trajectory-scenario-harness --strict` passes
- [x] `pytest` green in `packages/agent-scenarios/.venv`; `ruff` clean

## 10. Deferred (out of scope for this change)

- [ ] Live multi-vendor execution on the GX10 (real CLIs + keys) — nightly
- [ ] 10-scenario suite + nightly cadence + `/improve-harness` wiring
      (`seed-scenario-suite-and-nightly-cross-vendor-parity-runs`)
- [ ] Incident auto-seeding (`auto-seed-scenarios-from-incidents`)
