# Design — add-prime-agent-harness

## Decisions

### D1. `prime` is the single canonical provider key; `prime-agent` is only a binary name

Follows precedent D3 (`antigravity` vs `agy`): provider keys follow product names,
not binaries. `prime` is the one canonical string — used for the
`DEFAULT_PROVIDER_MODEL_MAP` key, the `archetypes.yaml` `model_aliases` key, the
`agents.yaml` entry `prime-local` and its `type:`, the profile `prime_local`, the
transcript adapter (`prime_cli.py`), the eval backend module (`prime.py`), the kanban
vendor label, and every allow-list. `prime-agent` appears **only** as `cli.command`.
No short form, no alias.

**Collision guard**: the existing vendor `pi` is a prefix-adjacent string. Every grep
gate in this change uses word-bounded patterns (`\bprime\b`, `\bpi\b`), and
`test_agents_config.py` gains an assertion that `pi` and `prime` are distinct
providers with disjoint `cli.command` values. Reviewers of gate scripts MUST reject
unanchored `pi` matches.

### D2. Subscription-lane policy: no Claude models through prime-agent

Operator policy is subscription maximization: Claude models run only on the
`claude_code` harness (flat-rate subscription); metered lanes carry everything else.
prime-agent's Claude Pro/Max OAuth path bills **per token against extra credits** —
it is metered Claude, which violates the policy on both sides (spends credits AND
bypasses the harness where Claude usage is prepaid).

Therefore:
- The `prime` provider tier map SHALL contain **no Anthropic model IDs**.
- `prime-local` SHALL declare `cli.api_key_env: PRIME_API_KEY`, while coordinator
  authentication remains a separately generated `prime_local_key` exposed as
  `--prime-local-key` and injected only as `COORDINATION_API_KEY`. Neither value
  may be substituted for, generated from, or serialized as the other.
- Operator setup documentation SHALL instruct authenticating prime-agent with
  `PRIME_API_KEY` (Prime Inference) only; `/login` OAuth to Anthropic/OpenAI/Copilot
  is documented as out of policy for dispatched use.
- This is config-and-docs enforcement, not runtime enforcement; the
  `add-coordinator-llm-gateway` change is the eventual runtime enforcement point.

### D3. Dispatch via `--mode json` (CliVendorAdapter), not ACP, not RPC

`--mode json` is a one-shot headless invocation with an NDJSON event stream —
exactly the shape the dispatcher already stream-parses for `pi` (archive §L7
precedent: final answer in `agent_end` / `message_end` assistant `content[]` where
`type == "text"`). ACP mode is one-session-per-connection and refuses concurrent
turns, which fights dispatcher fan-out; RPC mode adds a persistent service the
dispatcher doesn't need. ACP is recorded as a deferred spike, gated on a second
ACP-speaking harness joining the roster.

### D4. Tier models chosen for training-distribution diversity against `pi`

`pi` (OpenRouter) already covers Qwen (`qwen/qwen3-coder*` tiers) and Kimi
(`moonshotai/kimi-k3` frontier). If `prime` resolves to the same underlying models,
vendor diversity (worker ≠ validator) is nominally satisfied while
training-distribution diversity — the actual point of a metered lane — is not.
Tier selection in P4 therefore prefers model families `pi` does not carry (GLM,
DeepSeek, MiniMax) where the Prime Inference catalog and quality allow, and records
the overlap explicitly if any tier must share a family with `pi`.

### D5. Review-mode admission requires positive read evidence (blind-reviewer guard)

Per `agents.yaml:322-340`, a review vendor that returns `success=True` with
`{"findings": []}` having read nothing silently corrupts quorum. prime-agent's
single-tool design means "read-only" is a property of instructions and settings, not
of a tool allow-list. Admission rule for the `review` dispatch mode:

1. P6 must demonstrate a harness-native mechanism that prevents writes during a
   review dispatch (settings, mode flag, or equivalent), AND
2. the P6 validation transcript must show the harness actually read repository files
   named in the prompt (positive evidence, not absence of writes).

If either fails, `prime-local` ships without a `review` dispatch mode (still eligible
for `alternative` and `quick`), and the gap is filed as a follow-up. The unenforced
`isolation:` field is not an acceptable substitute (see
`add-dispatch-sandbox-enforcement`).

### D6. Daemon hygiene is part of the dispatch contract

prime-agent runs daemon-backed worker sessions that survive terminal detach — a
feature for interactive use, a leak for subprocess dispatch. The canonical `cli`
config therefore gains optional `cleanup: {args: [...], timeout_seconds: N}` support
regardless of the P7 result. P7 decides whether the `prime-local` entry populates the
field, not whether the config model and dispatcher understand it.

The cleanup contract is deliberately narrow and fail-closed:

- `args` is a non-empty string array appended to the configured `cli.command`; it is
  never a shell string and executes with `shell=False`.
- `timeout_seconds` is bounded and defaults to 10 seconds. Cleanup runs exactly once
  from the dispatcher's `finally` path after every launched synchronous attempt,
  including success, non-zero exit, parse failure, cancellation, and timeout. For an
  async mode it runs only after polling reaches a terminal outcome.
- The cleanup subprocess receives a minimal allowlisted environment. Coordinator
  credentials and unrelated vendor secrets are excluded; `PRIME_API_KEY` is included
  only if P7 proves the cleanup command requires it.
- Cleanup failure or timeout preserves the primary dispatch error, adds structured
  cleanup diagnostics, and makes the vendor result unsuccessful and ineligible for
  review quorum. A daemon-hygiene promise cannot be satisfied by a dirty success.
- P7 must prefer a per-session stop derived from the parsed session identifier. If
  prime-agent exposes only global shutdown, Prime dispatches are serialized or the
  affected concurrent/review mode is withheld so one cleanup cannot terminate an
  unrelated session.

The field is currently rejected by `AGENTS_SCHEMA` and dropped by every parser and
projection. Task 3.4a lands it through the coordinator schema, canonical `CliConfig`,
`load_agents_config()`, and `get_dispatch_configs()` HTTP/MCP projection. Task 3.4
lands the consumer-side dispatcher dataclass/parser and lifecycle execution. If P7
finds no residue, `prime-local` omits `cleanup`; the generic capability and its tests
remain available for future daemon-backed harnesses.

### D7. Prime Inference HTTP lane is a follow-up under `add-adaptive-model-router`, not this change

Prime Inference is OpenAI-compatible (`https://api.pinference.ai/api/v1`,
`PRIME_API_KEY`) and structurally identical to OpenRouter. The right home for a
direct HTTP lane is the in-flight router change's `endpoint_kind` mechanism +
`OpenAICompatAdapter` (`skills/parallel-infrastructure/scripts/openai_compat_adapter.py`),
which is built but not yet wired into discovery. This change deliberately does not
duplicate that path; it files the follow-up instead. Scope here is the CLI harness
only.

## Empirical CLI findings (Phase 1 evidence table)

Each fact is recorded as `confirmed` or `refuted` with the exact command and output
excerpt before any package may hardcode a flag, slug, or parsing assumption
(precedent: archive design §L1–L7; human checkpoint required). Documentation-derived
expectations below are hypotheses, not evidence.

| # | Fact to establish | Expectation from docs (unverified) | Status |
|---|---|---|---|
| P1 | Installed version, full flag inventory (`prime-agent --help`), version pinning for reproducible dispatch | Versioned releases via install.sh, SHA-256 verified | pending |
| P2 | Headless prompt delivery under a subprocess pipe: `prime-agent --mode json "<prompt>"` trailing positional; stdin behavior | Trailing positional per docs/json.md | pending |
| P3 | NDJSON envelope shape: session header, event taxonomy, where final assistant text lands; JSON-findings extraction for `_parse_findings` | `{"type":"session",...}` header; `message_end` / `agent_end` events with assistant `content[]` | pending |
| P4 | Model selection flag; Prime Inference catalog slugs for premium/standard/economy (+optional frontier); per-D4 diversity vs `pi` tiers | `--model` matching configured names; catalog updates per release | pending |
| P5 | Auth: `PRIME_API_KEY` inheritance from subprocess env; `~/.prime/agent/auth.json` precedence; re-auth story for `_RELOGIN_COMMANDS` vs `_MANUAL_REAUTH` | auth.json > env var; OAuth `/login` exists but is out of policy (D2) | pending |
| P6 | Read-only review mode: harness-native write prevention + positive evidence of repository reads in a review dispatch (D5 gate) | No documented tool allow-list; single ipython tool executes arbitrary Python | pending |
| P7 | Daemon lifecycle: resident processes after a `--mode json` one-shot; `prime-agent shutdown` / `stop` semantics; concurrent dispatch behavior | Daemon-backed sessions persist by design | pending |
| P8 | `rlm()` child-agent policy: can child model selection be pinned/disabled via settings to prevent cost-policy bypass | Children inherit parent model by default; `model=` override exists | pending |
| P9 | Thinking/reasoning-effort flag existence (feeds the known unconsumed `ResolvedArchetype.thinking` gap) | Not documented as a CLI flag | pending |

Operator authorization for live billed calls: to be recorded here before Phase 1
execution, per precedent.

## Scope inventory

Enumerated edit sites (from repo survey, 2026-08-06):

- `agent-coordinator/agents.yaml` (new entry)
- `agent-coordinator/archetypes.yaml` `model_aliases`
- `agent-coordinator/src/agents_config.py` `DEFAULT_PROVIDER_MODEL_MAP`
- `openspec/schemas/provider-model-map.schema.json` (enum + required + minProperties + schema_version 3)
- `skills/autopilot/scripts/provider_dispatch.py` `_SUPPORTED_PROVIDERS`
- `skills/autopilot/scripts/token_budget_check.py` (choices + `_PROVIDER_MODEL_BY_TIER`)
- `skills/autopilot/scripts/smoke_provider_dispatch.py` (choices + fallback models)
- `skills/autopilot-roadmap/scripts/orchestrator.py` `available` list
- `skills/autopilot-roadmap/scripts/policy.py` `_STATIC_COST_TIERS`
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` (re-auth tables; possible `_parse_findings` branch)
- `openspec/schemas/consensus-report.schema.json` + `skills/parallel-infrastructure/install_assets/openspec/schemas/consensus-report.schema.json`
- `agent-coordinator/src/schemas/kanban_viz/saved-view.json`
- `agent-coordinator/scripts/seed_kanban_board.py` `VENDORS`
- `agent-coordinator/scripts/setup_cloud.py`
- `agent-coordinator/evaluation/backends/` (`prime.py` + `registry.py`)
- `skills/collect-transcripts/scripts/adapters/` (`prime_cli.py` + fixtures)
- `packages/agent-scenarios/src/agent_scenarios/executor.py` `vendor_commands`
- `apps/kanban-viz/src/__tests__/VendorSwimlanes.test.tsx`
- Docs/templates: `README.md`, `agent-coordinator/CLAUDE.md`, `docs/skills-workflow.md`,
  `docs/autopilot-provider-smoke.md`, `.secrets.yaml.example`, `config.yaml.example`,
  `openspec/config.yaml`, lifecycle SKILL.md files
