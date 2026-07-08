# Design: Agent Trajectory Scenario Harness

> Change ID: `build-agent-trajectory-scenario-harness`

## Context

Phase 4 of `docs/proposals/always-on-agent-automation.md` asks for a harness that
validates the *agents* (attractor's cross-provider parity matrix), not the
system under test. gen-eval already validates the SUT via fixed transport-level
step sequences. This design reuses gen-eval's assertion vocabulary and its
injectable-judge pattern while introducing the genuinely new pieces: fixture
repos, deterministic goal gates over post-run workspace state, a per-vendor
executor loop, and a trajectory judge over normalized transcripts.

## Decision 1 — A new package, not a gen-eval extension

`agent-scenarios` is a separate `packages/<name>/` package rather than a module
inside `gen-eval`. Rationale:

- **Different unit of test.** gen-eval's `Scenario` is an ordered list of
  transport `ActionStep`s against a *live service*. An agent scenario is a
  *task prompt + fixture repo + goal gates* evaluated against *post-run
  filesystem/git state*. The transports don't overlap: gen-eval speaks
  HTTP/MCP/DB; the harness inspects files, branches, commits, PRs.
- **Different lifecycle.** gen-eval runs against a deployed target on demand; the
  harness runs headless agents per vendor and is CPU/time-heavy — it belongs on
  the GX10 nightly, not in the request path.
- **Convention.** `extract-gen-eval-package` established `packages/<name>/` with
  its own `pyproject.toml` precisely so sibling capabilities extract cleanly.
  This is the second package, validating the convention.

It is *not* a fork: the package takes a path dependency on `gen-eval` and imports
`ExpectBlock` directly, so the assertion contract is shared, not copied.

## Decision 2 — Reuse gen-eval's `ExpectBlock` / `SideEffectsBlock` vocabulary

The instruction is explicit: reuse, don't reinvent. Concretely:

- `GoalGatesBlock` mirrors `SideEffectsBlock` exactly — a `verify` list and a
  `prohibit` list. List placement is authoritative (`all_gates()` forces the
  `mode`), matching gen-eval's semantics where prohibited side effects must be
  absent.
- `GoalGate` mirrors `SideEffectStep`'s shape (`id` + `mode` + kind-specific
  fields + optional `expect`), but the "transport" is post-run workspace state.
- The `command` goal gate carries a genuine imported `gen_eval.models.ExpectBlock`
  and is scored against its `exit_code` / `error_contains` / `not_empty` fields.
  We reuse the real class (re-exported from `agent_scenarios`), not a copy.

## Decision 3 — Deterministic score vs. LLM judge (the core split)

This is the load-bearing architectural decision.

- **Deterministic goal-gate scorer** (`scorer.py`) is the authoritative signal.
  It evaluates every gate against the workspace with pure filesystem/git
  inspection and subprocess calls — **no model in the loop**. A scenario's
  pass/fail is fully reproducible and vendor-independent in its logic. This is
  what the parity matrix compares and what gates dispatch routing.
- **LLM judge** (`judge.py`) is strictly **additive**, mirroring gen-eval's
  `SemanticBlock` → `SemanticVerdict` contract: it returns `skip` (never `fail`)
  when no backend is injected, and its verdict/findings never override the
  deterministic status. It measures trajectory *quality* the scorer cannot see —
  inefficiency, unnecessary actions, and "wrong-but-passed" (goal gates hit by
  luck or a fragile path).

Keeping these separate means: (a) the harness produces a meaningful result with
no LLM at all (critical for a hermetic CI lane); (b) a flaky/absent judge can
never turn a green run red; (c) the judge's value — catching an agent that
passed the gates the wrong way — is captured as *additive* findings, not as a
gate.

## Decision 4 — Injectable executor seam (structural multi-vendor)

The runner depends only on the `ScenarioExecutor` protocol
(`run(scenario, vendor, workdir) -> RunResult`). Swapping vendors or swapping a
real CLI for a fake is a constructor argument. This makes the cross-vendor
parity matrix **structural**: `run_scenario` loops `scenario.vendors` and calls
the same seam for each, so the matrix falls out of the loop rather than being a
special mode.

- `CLIVendorExecutor` (real) materializes the fixture, shells to a per-vendor
  CLI argv template (`claude -p {prompt}`, `codex exec …`, `gemini …`), then
  observes post-run state (working branch, PR via `gh`) and collects the
  transcript through an *injected* normalizer (so the package doesn't hard-depend
  on the `collect-transcripts` skill layout). It degrades to an error
  `RunResult` — never raises — when a vendor is unconfigured or its CLI is
  absent, so one broken vendor can't crash the parity loop.
- `FakeExecutor` (tests) applies a scripted `Outcome` (files, branch, commit, PR,
  synthetic transcript) so the full runner → scorer → judge → emitter path is
  provable without any vendor.

## Decision 5 — Judge input is the normalized transcript

The judge consumes the `collect-transcripts` normalized event shape
(`role` + `content` blocks of `text`/`tool_use`/`tool_result`). This is the same
schema `collect-transcripts` adapters already produce for every vendor, so on the
GX10 the `CLIVendorExecutor`'s injected normalizer is literally
`collect-transcripts`' `normalize`. The judge backend is the injectable
`TrajectoryJudgeBackend` protocol (`is_available()` / `complete(prompt, system)`)
— the same shape as gen-eval's `LLMBackend`, kept synchronous to match the
subprocess-driven runner.

## Decision 6 — Findings map onto `review-findings.schema.json`

The emitter produces a document conforming to
`openspec/schemas/review-findings.schema.json`, exactly like gen-eval's emitter
(same producer-side validation + atomic write). Mapping:

- **Deterministic gate failure** → `type: behavioral_failure`, `axis:
  correctness`, `severity: critical`, `disposition: fix`. A failed gate is a hard
  behavioral defect.
- **Judge finding** → nearest enum type: `inefficiency`/`unnecessary_action` →
  `performance`; `wrong_but_passed`/`other` → `behavioral_failure`. Judge
  findings carry lower severity (`fyi`/`optional`) and `disposition: accept` so
  they never mask a deterministic failure. `behavioral_failure` is already in the
  schema's `type` enum, so no schema change is required.

Findings set `file_path` to the scenario YAML so `/improve-harness` can trace a
capability gap back to the scenario that surfaced it.

## Multi-vendor parity model

For each scenario, `run_scenario` produces a `ParityMatrix` with one
`VendorRunVerdict` per declared vendor. `all_vendors_pass` is the parity signal
the follow-up nightly job and the dispatcher pre-route gate consume: a skill
change is only routed real work if it passes the parity suite across all
configured vendors. Because the scorer is deterministic and vendor-agnostic in
its logic, a per-vendor divergence is a real signal about that vendor's agent,
not scorer noise.

## How this differs from gen-eval (summary)

| dimension | gen-eval | agent-scenarios |
|---|---|---|
| validates | deployed **service** | the **agent** |
| unit | ordered transport steps | task prompt + fixture repo |
| "transport" | HTTP/MCP/CLI/DB (live) | post-run files/branch/commit/PR |
| execution | drive a running target | run a skill headless per vendor |
| parity | single target | cross-vendor matrix (structural) |
| judge | `SemanticBlock` per step | trajectory review over transcript |
| shared | — | imports gen-eval `ExpectBlock`; same findings schema + judge pattern |

## Testing strategy and GX10 boundary

In-container tests use `FakeExecutor` + a fake judge backend to prove every seam
end-to-end (scorer over pass/fail fixtures, YAML validation, the vendor loop,
findings schema conformance, judge skip-vs-contribute, and the real
`CLIVendorExecutor`'s degradation path). **Live multi-vendor execution with real
CLIs and keys is out of scope for in-container tests and is exercised on the
GX10** (aarch64, nightly), where the injected executor is the real
`CLIVendorExecutor` and the injected judge backend is a real vendor model. A
`gx10` pytest marker flags the live-only test so it skips cleanly here.
