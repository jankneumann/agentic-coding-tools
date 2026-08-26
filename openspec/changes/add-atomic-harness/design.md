# Design — add-atomic-harness

## Context

Atomic (`bastani-inc/atomic`, MIT) is a fork of the pi harness that adds a durable
TypeScript workflow engine (DBOS-backed checkpointing, schema-validated stage handoffs,
resumable headless runs). This change registers it as the first **experimental** vendor —
a new provider class introduced here — and pilots its workflow engine through one opt-in
seam. Approach 2 of `proposal.md` was selected at Gate 1; discovery-gate parameters:
Level 1 + scoped Level 2 pilot, experimental-vendor tier, OpenRouter with slugs distinct
from pi, sequenced after `add-frontier-model-tier`.

Affected architecture layers: **Coordination** (agents.yaml / agents_config.py /
provider-model map), **Execution** (review_dispatcher, workflow dispatch adapter,
fix-scrub, collect-transcripts), **Governance/Observability** (vendor surfaces, docs).

## Empirical CLI findings

Per the probe-before-config discipline established by
`2026-07-24-add-agy-grok-pi-harnesses`: no package may hardcode a CLI flag, model slug,
or output-parsing assumption until the row below reads `confirmed` with evidence.
Probed 2026-08-12 against `atomic` v0.9.12 (npm `@bastani/atomic`, `--ignore-scripts`,
Node ≥ 22.19) in the cloud planning container. Raw outputs archived in the planning
session; table is authoritative.

| ID | Claim | Status |
|----|-------|--------|
| A1 | Installs clean with `--ignore-scripts`; single `atomic` binary | confirmed |
| A2 | Non-interactive mode `-p`/`--print`; prompt accepted as trailing positional AND via stdin | confirmed |
| A3 | `--mode json` emits NDJSON events (`session`, `agent_start`, `turn_start`, `message_start/end`, `turn_end`, `agent_end`, `agent_settled`), LF-delimited | confirmed |
| A4 | Prompt echoed back as `role:"user"` message events → parser MUST take the last assistant terminal message (same fold hazard as pi backend bug, coordinator issue 035ffd93) | confirmed |
| A5 | Failures embed in-stream as assistant message with `stopReason:"error"` + `errorMessage`; process exit 1 | confirmed |
| A6 | Missing API key → stderr `No API key found for <provider>` + `/login` hint, exit 1 | confirmed |
| A7 | `--api-key <key>` flag exists (divergence from pi E3); env vars remain default source | confirmed |
| A8 | `atomic auth print-api-key\|print-bearer-token` prints one credential on stdout; exit codes 0/1/2/3/9 | confirmed |
| A9 | `--provider <name>`, `--model <pattern>` (`provider/id` + `:<thinking>` suffix), separate `--thinking off…max`; `--list-models` works `--offline` | confirmed |
| A10 | Provider auto-detection is ambient (unpinned run selected `amazon-bedrock` from container env despite documented default `google`) → adapter MUST always pin `--provider` + `--model` | confirmed |
| A11 | Workflow engine bundled: 9 builtins incl. `adversarial-verification`, `ralph`, `loop-until-done`; `/workflow list` headless exit 0 | confirmed |
| A12 | Custom `.atomic/workflows/*.ts` auto-discovered when project trusted (`--approve`); tool-only workflows valid | confirmed |
| A13 | First discovery of a new TS workflow can exceed 90 s (compile warm-up); later runs fast → dispatch timeout ≥ 300 s on first run | confirmed |
| A14 | Headless dispatch `atomic -p --mode json '/workflow <name> k=v'` waits for terminal snapshot; emits `entry_appended` custom events `workflow.run.start`/`workflow.run.end` with `{runId, status, result, endedAt, durationMs}`; exit 0 on completed | confirmed |
| A15 | Durable engine runs offline; tool-only run completed in 73 ms | confirmed |
| A16 | Session store `~/.atomic/agent/sessions/<cwd-slug>/<ISO-ts>_<uuid>.jsonl`, header `{"type":"session","version":3}` | confirmed |
| A17 | Workflow-only run (zero model stages) persisted no session file under `--session-dir` | confirmed (this path) |
| A18 | Live model calls through any provider | **unconfirmed — environment-blocked** (egress proxy 403; no keys). Live dispatch enablement gates on re-probe (task 1.x) |
| A19 | No sandbox / permission gate; tools run with user permissions (upstream docs) → worktree isolation mandatory | from docs, not probed |
| A20 | Claude subscription via third-party harness bills per-token extra usage (upstream docs) → do not pin atomic to Anthropic subscription models | from docs, not probed |

## Key Decisions

### D1 — Experimental provider class, not a sixth roster key

An experimental provider: (a) is declared in `agents.yaml` with `experimental: true`;
(b) is dispatchable via `CliVendorAdapter` and eligible for review rotation and
`/quick-task`; (c) MAY declare a provider tier map, resolved through the same
`resolve_provider_model_spec` path, but its key is NOT added to the closed
`provider-model-map.schema.json` enum — experimental tier maps live in a sibling
`experimental_providers` mapping validated by the same tier-entry shape; (d) is exempt
from eval-backend parity and from the first-class provider selector list of the manual
smoke path (it is accepted there only with an explicit experimental warning); (e) is
excluded from vendor-diversity *quorum counting* by default (`counts_toward_quorum:
false`) so an unproven reviewer cannot manufacture consensus — the pi `--no-tools`
false-consensus lesson (agents.yaml:322) applied preemptively. Unknown non-experimental
providers still fail loudly everywhere. Promotion to first-class is a separate future
change (schema enum + four specs + eval backend); retirement is deleting the entry.

### D2 — Always pin provider and model (A10)

Every atomic invocation constructed by adapters SHALL pass `--provider openrouter` and
an explicit `--model <slug>`. Ambient credential auto-detection is treated as a defect
surface, not a convenience.

### D3 — Reuse the pi NDJSON parsing path (A3/A4/A5)

`review_dispatcher._parse_ndjson_findings` / last-assistant-terminal-message selection
applies to atomic unchanged. Reauth hint (A6/A7): "set OPENROUTER_API_KEY in the
environment or run interactive `/login`" — never fabricate a login subcommand.

### D4 — Workflow-executor dispatch contract (A11–A15, A19)

`workflow_dispatch.py` (parallel-infrastructure) SHALL: build
`atomic -p --mode json --approve '/workflow <name> key=value …'`; run it inside a
managed worktree (A19) with cwd = worktree root; treat the `workflow.run.end` event as
the authoritative result (`status` ∈ completed/failed/blocked; `result` carries the
workflow's typed outputs); surface `runId` in the audit trail; time out at ≥ 300 s for
first-run compile warm-up (A13) and per-mode config thereafter; classify `blocked`
status as retryable-with-reauth, `failed` as terminal for the attempt. Workflows
dispatched headlessly MUST NOT contain interactive `ctx.ui.*` gates (upstream: headless
runs fail at the prompt); the adapter rejects known-HIL workflow names at build time.

### D5 — One pilot seam: fix-scrub opt-in

The only consumer of `workflow_dispatch.py` in this change is `fix-scrub`, behind
`--executor atomic-workflow` (default unchanged). It maps a fix batch onto Atomic's
builtin `adversarial-verification` workflow (worker → fresh-context verifiers → bounded
repair) or a repo-authored definition under `.atomic/workflows/`. Autopilot phases do
not change executors here; promotion of the executor into other skills is future work
gated on pilot results.

### D6 — Transcript adapter `atomic_cli` (A16/A17)

`HARNESS_ID="atomic_cli"`, `SCHEMA_VERSION="atomic-jsonl-v3"`, source glob
`~/.atomic/agent/sessions/*/<ts>_<uuid>.jsonl`. Fails soft when the directory is absent.
Written against the `build-structured-vendor-result-channel` envelope contract where it
lands first; workflow-only runs may have no session file (A17) — the adapter documents
this gap rather than erroring.

### D7 — Live re-probe gate (A18)

All live-dispatch enablement (review rotation eligibility, pilot activation) is gated on
re-running the probe rows A18 + model-slug confirmation in a network-permitted
environment, recorded by updating this design table. Until then atomic ships
dry-run/smoke-only (`smoke_provider_dispatch.py --dry-run` passes without network).

### D8 — Model slugs: distinct from pi, candidates unverified

pi owns the qwen3-coder lineup. Atomic tier-map **candidates** (all UNVERIFIED until the
A18 re-probe; do not hardcode downstream): frontier `moonshotai/kimi-k3` alternates,
`z-ai/glm-*`, `deepseek/deepseek-*`, `minimax/minimax-*` families. The re-probe task
fixes final slugs and updates `agents.yaml` + the experimental tier map in one commit.

## Alternatives rejected

- **Sixth first-class provider now** (Approach 1): four-spec reopening + eval backend for
  a trial; repeats for every future harness experiment.
- **Workflow-executor only** (Approach 3): unmanaged dispatch path outside vendor
  diversity/health/audit machinery; no reviewer-rotation learning.
- **Anthropic models via atomic**: rejected on A20 cost semantics.
- **Counting atomic toward review quorum immediately**: rejected on the pi
  false-consensus precedent; revisit at promotion.

## Risks

| Risk | Mitigation |
|------|------------|
| `add-adaptive-model-router` rewrites the tier/mapping layer mid-flight | Sequencing decision: land after `add-frontier-model-tier`; keep experimental tier map in a sibling structure (D1c) so the router change composes instead of colliding |
| Atomic CLI surface changes upstream (v0.x) | Pin probed version in design; re-probe row discipline on upgrade |
| Workflow runs hang (HIL prompt, provider block) | D4: HIL rejection at build time; `blocked` classification; hard timeout |
| False consensus from an unproven reviewer | D1e: `counts_toward_quorum: false` until promotion |
| Live behavior diverges from container probe | D7 gate before any live enablement |
