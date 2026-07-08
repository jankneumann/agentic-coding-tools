# Build agent trajectory scenario harness

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `build-agent-trajectory-scenario-harness`
> Effort: L
> Priority: 3

## Why

`gen-eval` validates a deployed **service**: it drives fixed transport-level
step sequences (HTTP/MCP/CLI/DB) against a running system and scores the
responses. Nothing in the repo validates the **agents themselves**. When a skill
changes — `plan-feature`, `implement-feature`, `validate-feature` — there is no
way to ask "did the agent, running headless, actually achieve the goal on a
realistic task, across vendors, without prohibited side effects?" The
always-on-agent-automation proposal (Phase 4) calls this out as the genuinely
new attractor-inspired capability: a **cross-vendor scenario parity matrix** that
gates whether the dispatcher routes real work through a changed skill.

This matters because every other validation layer assumes the agent already did
the right thing. The holdout gate checks the produced diff; gen-eval checks the
deployed service; playwright checks the rendered UI. But the agent's own
trajectory — whether it reached the goal, whether it wasted effort, whether it
"passed" by luck or via a forbidden path — is unmeasured. An agent that deletes
`main`, commits secrets, or hardcodes a test value to go green is invisible to
today's gates.

## What Changes

Add a new package `packages/agent-scenarios/` (following the `packages/<name>/`
monorepo convention established by `extract-gen-eval-package`) that validates
agents attractor-style:

1. **Scenario YAML model.** A scenario declares `task_prompt`, `fixture` (repo
   state + setup), `skill_under_test`, `vendors` (the parity list), and
   `goal_gates`. Goal gates **reuse gen-eval's vocabulary**: they mirror
   `SideEffectsBlock`'s `verify`/`prohibit` split and carry gen-eval's
   `ExpectBlock` for `command` assertions. Pydantic model + validation.
2. **Deterministic goal-gate scorer.** Given a post-run workspace, evaluate each
   gate (`file` / `branch` / `commit` / `pr` / `artifact` / `command`) to
   pass/fail with **no LLM**. This is the authoritative, reproducible score the
   parity matrix is built on.
3. **Injectable per-vendor executor** (`ScenarioExecutor` protocol,
   `run(scenario, vendor, workdir) -> RunResult`). Ships a real
   `CLIVendorExecutor` that shells to a per-vendor coding-agent CLI (wired for
   the GX10, degrades cleanly when the CLI is absent) and a `FakeExecutor` for
   tests. The runner loops `scenario.vendors`, so multi-vendor parity is
   **structural**, not bolted on.
4. **Injectable LLM-judge trajectory review.** Reviews the normalized
   `collect-transcripts` transcript for efficiency, unnecessary actions, and
   "wrong-but-passed". Skip-if-no-backend like gen-eval's `SemanticBlock`;
   strictly additive to the deterministic score.
5. **Findings emitter** conforming to `openspec/schemas/review-findings.schema.json`
   (deterministic gate failures + judge findings), feeding `/improve-harness`.
6. **Seed scenarios + tests.** Two seed scenarios (a `plan-feature` and an
   `implement-feature` scenario) plus a full test suite: scorer over pass/fail
   fixtures, YAML validation, the runner looping all vendors via the fake
   executor, findings schema conformance, and judge skip/contribute behavior.

**Out of scope (deliberately):**
- **Live multi-vendor execution.** Real vendor CLIs and keys are not available
  in-container, so live runs are proven structurally with an injected
  `FakeExecutor`. The real `CLIVendorExecutor` is wired and exercised for its
  degradation path but runs live only on the GX10 (nightly).
- **The nightly cadence, capability-gap wiring, and 10-scenario suite** — those
  belong to the follow-up `seed-scenario-suite-and-nightly-cross-vendor-parity-runs`
  (which depends on this change). This change ships the framework + 2 seeds.
- **Incident auto-seeding** (`auto-seed-scenarios-from-incidents`) — separate change.

## Impact

- **Affected specs**: new capability `agent-trajectory-harness` (ADDED
  requirements only). No existing spec is modified.
- **Affected code**: new `packages/agent-scenarios/` (source, 2 seed scenarios,
  tests). Adds a path dependency on `packages/gen-eval` to reuse `ExpectBlock`.
  No existing package or skill is modified by this change.
- **Enabled consumers** (not in this change): the dispatcher's pre-route parity
  gate, `/improve-harness`, and the nightly parity job all consume this package.
