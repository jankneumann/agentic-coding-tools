# agent-scenarios

Agent **trajectory** scenario harness. Where [`gen-eval`](../gen-eval) validates a
deployed *service* via fixed transport-level step sequences, `agent-scenarios`
validates the *agents themselves* (attractor-style): give a task prompt + a
fixture repo state, run a skill headless per vendor, and score whether the agent
achieved the goal — plus an LLM-judge review of the trajectory.

## The model

A scenario YAML declares:

- `task_prompt` — what the agent is asked to do.
- `fixture` — starting repo state (`files`, `git_init`, optional setup `commands`).
- `skill_under_test` — the skill being exercised.
- `vendors` — the list of vendors to run it across (the parity matrix).
- `goal_gates` — expected/prohibited outcomes, split into `verify` / `prohibit`
  (mirroring gen-eval's `SideEffectsBlock`). Each gate checks `file`, `branch`,
  `commit`, `pr`, `artifact`, or `command` (the `command` check reuses
  gen-eval's `ExpectBlock`).

## Two-part score

1. **Deterministic goal-gate scorer** (`scorer.py`) — evaluates every gate
   against the post-run workspace with **no LLM**. This is the authoritative,
   reproducible signal.
2. **Injectable LLM-judge** (`judge.py`) — additive trajectory-quality review
   over the normalized `collect-transcripts` transcript. Skips cleanly when no
   backend is injected (like gen-eval's `SemanticBlock`); never overrides the
   deterministic verdict.

## Injection seams

- `ScenarioExecutor` protocol — `run(scenario, vendor, workdir) -> RunResult`.
  Ships `CLIVendorExecutor` (real, shells to a per-vendor CLI; wired for the
  GX10) and `FakeExecutor` (scripted, for tests). The runner loops
  `scenario.vendors`, so multi-vendor parity is **structural**.
- `TrajectoryJudgeBackend` protocol — `is_available()` / `complete(prompt, system)`.

## Usage

```python
from agent_scenarios import load_scenarios, run_scenarios, emit_findings, FakeExecutor

scenarios = load_scenarios("scenarios/")
matrices = run_scenarios(scenarios, my_executor, judge_backend=my_backend)
emit_findings(matrices=matrices, output_path="findings-agent-scenarios.json",
              target="my-change-id")
```

Findings conform to `openspec/schemas/review-findings.schema.json` and feed the
`/improve-harness` capability-gap pipeline.

## Live vs in-container

Live multi-vendor execution requires real vendor CLIs and keys and runs on the
**GX10** nightly. In-container tests use `FakeExecutor` and a fake judge backend
to prove the framework end-to-end without any vendor.
