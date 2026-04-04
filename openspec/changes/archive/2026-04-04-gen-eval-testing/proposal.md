# Proposal: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`
**Status**: Draft
**Author**: Claude Code
**Date**: 2026-03-30

## Summary

Adopt Anthropic's generator-evaluator pattern (from their [harness design blog post](https://www.anthropic.com/engineering/harness-design-long-running-apps)) as a **general-purpose evaluation capability** within the coordinator and skills framework. The framework enables any project using the coordinator to comprehensively evaluate its API, CLI, and frontend interfaces against live running services — using LLM-powered scenario generation and skeptical, independent evaluation.

We dogfood it on our own agent-coordinator (35 HTTP endpoints, 39 MCP tools, 31 CLI commands) as the first target project, but the design is project-agnostic.

## Motivation

### The Pattern

Anthropic's engineering team found that agents confidently praise their own work even when quality is mediocre. Their breakthrough: separate a **Generator** agent (which builds/tests) from a skeptical **Evaluator** agent (which independently verifies against the live system). The evaluator uses real tools — Playwright for frontends, HTTP clients for APIs, subprocess for CLIs — and provides specific, actionable feedback ("audio timing off by 12ms") that drives iterative improvement.

This maps naturally to the software development lifecycle where code review and QA serve the same structural role.

### Why General-Purpose

The generator-evaluator loop isn't specific to one application — it's a **pattern for building and verifying any software**. Our coordinator already orchestrates multi-agent collaboration (locks, memory, work queue, guardrails). Adding generator-evaluator as a first-class capability means any project coordinated by our system gets:

1. **Scenario generation** tailored to its interface surface (defined via OpenAPI specs, CLI help output, route manifests)
2. **Live-service evaluation** with skeptical verification (not just "did the API return 200?" but "is the database state correct?")
3. **Budget-aware progressive testing** that scales from cheap CI smoke tests to comprehensive production-grade evaluation
4. **Feedback loops** where evaluation findings guide the next round of generation toward under-tested areas

### Current Gaps (Dogfood Target)

Our own agent-coordinator has 105+ exercisable interfaces but:
- No cross-interface consistency testing (lock acquired via API never verified via MCP)
- No adversarial multi-agent scenarios (concurrent lock contention, race conditions)
- No live MCP server testing (only mocked)
- No LLM-generated edge cases beyond hand-written tests
- No budget-aware progressive evaluation

## Goals

### Primary Goals

1. **General-purpose framework** — project-agnostic generator-evaluator that works with any API/CLI/frontend defined via interface descriptors
2. **Interface descriptor format** — declarative way to describe a project's testable surface (endpoints, tools, commands, routes) that drives both generation and evaluation
3. **Pluggable transport clients** — HTTP, MCP (stdio/SSE), CLI (subprocess), browser (Playwright), database (asyncpg) — composable per project
4. **Skeptical evaluator** — independently verifies responses AND underlying state (DB, filesystem, external effects), catches cross-interface inconsistencies
5. **Budget-aware progressive execution** — prioritizes changed features, expands to full surface as budget allows; hard cost caps with early termination
6. **Feedback loops** — evaluator findings guide generator toward under-tested areas across iterations

### Secondary Goals

7. **Coordinator integration** — uses work queue for distributed evaluation tasks, memory for storing findings across runs, audit for traceability
8. **Skill integration** — available as a skill (`/gen-eval`) and as a phase within `validate-feature`
9. **Dogfood on agent-coordinator** — first interface descriptor covers all 105+ coordinator interfaces
10. **CI-friendly** — conservative template-only budget for automated runs; larger LLM-augmented budget for manual deep evaluation

### Non-Goals

- Replacing existing unit/integration/E2E tests (this complements them)
- Load/performance testing (focused on correctness and completeness)
- Becoming a general-purpose test framework (this is specifically the generator-evaluator *pattern* — adversarial scenario generation + skeptical evaluation + feedback loops)

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                  GenEval Orchestrator                  │
│  (lifecycle, budget tracking, feedback loops,         │
│   coordinator integration)                            │
└──────────┬───────────────────────────┬───────────────┘
           │                           │
    ┌──────▼──────┐            ┌───────▼───────┐
    │  Generator   │◄──────────│   Evaluator   │
    │              │  feedback  │  (skeptical   │
    │ template +   │           │   judge)      │
    │ LLM-augmented│           │               │
    └──────┬──────┘            └───────┬───────┘
           │ scenarios                 │ verdicts
           ▼                           ▼
    ┌─────────────────────────────────────────┐
    │        Interface Descriptor              │
    │  (project-specific surface definition)   │
    │                                         │
    │  ┌─────────┐ ┌─────────┐ ┌──────────┐  │
    │  │ OpenAPI  │ │MCP Tool │ │CLI Help  │  │
    │  │ Spec     │ │Manifest │ │Schema    │  │
    │  └────┬────┘ └────┬────┘ └────┬─────┘  │
    │       └───────────┼───────────┘         │
    └───────────────────┼─────────────────────┘
                        ▼
    ┌─────────────────────────────────────────┐
    │        Transport Clients (pluggable)     │
    │  ┌──────┐ ┌─────┐ ┌─────┐ ┌─────────┐  │
    │  │ HTTP │ │ MCP │ │ CLI │ │Playwright│  │
    │  └──┬───┘ └──┬──┘ └──┬──┘ └────┬────┘  │
    │     └────────┼───────┘          │       │
    │              ▼                  ▼       │
    │  ┌────────────┐    ┌──────────────┐     │
    │  │ PostgreSQL  │    │  Browser     │     │
    │  │ (state      │    │  (frontend   │     │
    │  │  verifier)  │    │   verifier)  │     │
    │  └────────────┘    └──────────────┘     │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │     Coordinator (optional integration)   │
    │  work_queue │ memory │ audit │ guardrails │
    └─────────────────────────────────────────┘
```

### How It Works

1. **Define surface** — Project provides an interface descriptor (OpenAPI spec, MCP tool manifest, CLI schema, frontend route map). This is the "what can be tested" definition.

2. **Generate scenarios** — The generator produces multi-step coordination scenarios from templates and/or LLM generation. Each scenario is a sequence of interface calls with expected behaviors and cross-interface assertions.

3. **Execute against live services** — The orchestrator spins up services (docker-compose or process management), executes scenarios through pluggable transport clients.

4. **Evaluate skeptically** — The evaluator independently verifies:
   - Response correctness (schema, status codes, semantics)
   - State correctness (database queries, filesystem checks)
   - Cross-interface consistency (operation via API, verify via MCP)
   - Security boundaries (auth enforcement, trust level restrictions)

5. **Feedback loop** — Evaluator findings (failures, near-misses, coverage gaps) feed back to the generator to produce targeted follow-up scenarios.

6. **Report** — Structured verdict per interface/endpoint with pass/fail/degraded, coverage metrics, and cost accounting.

## Key Design Decisions

### D1: Interface Descriptors Drive Everything

A single declarative format describes the testable surface. The generator reads it to know what scenarios to produce. The evaluator reads it to know what responses to expect. This makes the framework project-agnostic.

```yaml
# Example: gen-eval-descriptor.yaml
project: agent-coordinator
version: "0.1.0"

services:
  api:
    type: http
    base_url: "http://localhost:8081"
    spec: "./openapi.yaml"           # OpenAPI 3.x
    auth:
      type: api_key
      header: X-API-Key
      env_var: COORDINATION_API_KEYS

  mcp:
    type: mcp
    transport: sse
    url: "http://localhost:8082/sse"
    tools_manifest: "./mcp-tools.json"  # or auto-discovered

  cli:
    type: cli
    command: "python -m src.coordination_cli"
    schema: "./cli-schema.json"       # or --help parsed
    json_flag: "--json"

  db:
    type: postgres
    dsn_env: POSTGRES_DSN
    tables: [file_locks, work_queue, memory_episodic, audit_log, ...]

startup:
  command: "docker-compose up -d"
  health_check: "http://localhost:8081/health"
  teardown: "docker-compose down -v"
```

### D2: CLI-First LLM Execution (Subscription-Covered)

Both the generator and evaluator use **CLI tools** (`claude --print`, `codex`) as their LLM engine rather than direct API calls. Since CLI usage is covered by subscription plans (Claude Pro/Team/Enterprise, Codex), this makes LLM-powered generation and evaluation effectively **zero marginal cost** — the only constraint is time and rate limits, not per-token charges.

This follows the same pattern as the existing evaluation harness backends (`ClaudeCodeBackend`, `CodexBackend`) which already shell out to CLI tools via subprocess.

- **Templates** (zero LLM, instant): YAML scenario files for known critical paths — deterministic, fast, CI-friendly.
- **CLI-augmented** (subscription-covered): Generator/evaluator agents run via `claude --print` or `codex` to produce novel edge-case scenarios and provide skeptical judgment. Guided by evaluator feedback.
- **SDK fallback** (per-token cost): Automatic fallback when CLI hits rate limits, session caps, or weekly caps. Also used for SDK-specific features (structured outputs, tool use) or CI environments without CLI access. The `AdaptiveBackend` detects CLI rate limiting and switches transparently.
- **Mode selection**: `template-only` (fastest, no LLM), `cli-augmented` (default, adaptive fallback to SDK when rate-limited), `sdk-only` (explicit opt-in for CI/cloud without CLI access).

### D3: Cross-Interface Consistency as First-Class Concern

Scenarios can span multiple transports in a single test:

```yaml
scenario: cross-interface-lock-lifecycle
steps:
  - action: http.post
    endpoint: /locks/acquire
    body: { file_path: "src/main.py", agent_id: "agent-1" }
    expect: { status: 200, body.success: true }

  - action: mcp.call
    tool: check_locks
    params: { file_paths: ["src/main.py"] }
    expect: { result[0].locked: true, result[0].locked_by: "agent-1" }

  - action: cli.run
    command: "lock status --file-paths src/main.py"
    expect: { exit_code: 0, json.locked: true }

  - action: db.query
    sql: "SELECT * FROM file_locks WHERE file_path = 'src/main.py'"
    expect: { rows: 1, row[0].agent_id: "agent-1" }
```

### D4: Progressive Scope Allocation with Time Budget

Since CLI-based LLM calls are subscription-covered, the primary constraint is **time** (wall-clock and rate limits), not dollars. Budget is expressed as a **time envelope** with scope tiers:

1. **Tier 1** (40% time): Changed features — deep adversarial evaluation on modified endpoints/tools
2. **Tier 2** (35% time): Critical paths — lock lifecycle, work queue, guardrails, auth
3. **Tier 3** (25% time): Full surface — comprehensive regression sweep

Template execution is instant (no LLM calls). CLI-augmented generation/evaluation uses subscription-covered CLI calls. An optional **USD budget cap** applies only when `api-fallback` mode is explicitly enabled for environments without CLI access.

### D5: Coordinator Integration (Optional)

When a coordinator is available:
- **Work queue**: Distribute evaluation scenarios as tasks for parallel execution by multiple agents
- **Memory**: Store findings across runs for trend analysis and regression detection
- **Audit**: Log all evaluation actions for traceability
- **Guardrails**: Ensure generated scenarios don't include destructive operations

When no coordinator is available, the framework runs standalone with local execution.

### D6: Dogfood First, Generalize Second

The first interface descriptor targets our own agent-coordinator. Implementation validates the general-purpose design against a real, complex project. The descriptor format and transport clients are designed for reuse but proven on our own codebase first.

## Impact Assessment

### New Files (in `agent-coordinator/evaluation/gen_eval/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `config.py` | GenEvalConfig: budget, thresholds, service endpoints, mode |
| `descriptor.py` | Interface descriptor parser (YAML → typed model) |
| `generator.py` | Scenario generation: template loader + LLM augmentation |
| `evaluator.py` | Skeptical evaluation: execute scenarios, verify, judge |
| `orchestrator.py` | Lifecycle: start services, run gen-eval loops, budget tracking, reporting |
| `clients/http_client.py` | HTTP transport client (httpx-based) |
| `clients/mcp_client.py` | MCP transport client (fastmcp SDK) |
| `clients/cli_client.py` | CLI transport client (subprocess) |
| `clients/db_client.py` | Database verification client (asyncpg) |
| `clients/browser_client.py` | Playwright browser client (stub, for future frontend projects) |
| `feedback.py` | Feedback synthesis: evaluator findings → generator guidance |
| `reports.py` | Structured verdict reports (markdown + JSON) |
| `scenarios/` | Template scenario YAML files |
| `schemas/` | Expected response schemas for validation |
| `descriptors/agent-coordinator.yaml` | Dogfood: our own interface descriptor |

### New Files (tests)

| File | Purpose |
|------|---------|
| `tests/test_evaluation/test_gen_eval/test_config.py` | Config parsing |
| `tests/test_evaluation/test_gen_eval/test_descriptor.py` | Descriptor loading |
| `tests/test_evaluation/test_gen_eval/test_generator.py` | Scenario generation |
| `tests/test_evaluation/test_gen_eval/test_evaluator.py` | Evaluation logic |
| `tests/test_evaluation/test_gen_eval/test_orchestrator.py` | Orchestration |
| `tests/test_evaluation/test_gen_eval/test_clients.py` | Transport clients |

### Modified Files

| File | Change |
|------|--------|
| `evaluation/__init__.py` | Export gen_eval module |
| `evaluation/metrics.py` | Add GenEvalMetrics (scenario_id, interface, verdict) |
| `pyproject.toml` | Add optional `gen-eval` dependency group |
| `skills/validate-feature/SKILL.md` | Add gen-eval as validation phase |

### New Skill

| File | Purpose |
|------|---------|
| `skills/gen-eval/SKILL.md` | Skill spec for `/gen-eval` invocation |

## Cost Considerations

### CLI-First Model (Subscription-Covered)

Since `claude` and `codex` CLI usage is covered by subscription plans (Pro/Team/Enterprise), the marginal cost of LLM-powered generation and evaluation is **$0** — the constraint is wall-clock time and rate limits, not per-token charges.

| Run Mode | Marginal Cost | Wall-Clock | Use Case |
|----------|--------------|------------|----------|
| `template-only` | $0 | ~2 min | CI per-PR, deterministic scenarios only |
| `cli-augmented` | $0 (subscription) | ~15-30 min | Default interactive: CLI-powered generation + evaluation |
| `cli-comprehensive` | $0 (subscription) | ~1-2 hr | Full surface, multi-iteration feedback loops |
| `cli-augmented` (rate-limited, SDK fallback) | SDK cost for overflow | ~15-60 min | CLI hits caps, transparently falls back to SDK for remaining calls |
| `sdk-only` | $5-50 (per-token) | ~10-60 min | CI without CLI access, or when CLI caps exhausted |

Service costs (PostgreSQL, API server) are local Docker containers — no cloud cost.

### Why CLI-First Works

The existing evaluation harness already uses this pattern — `ClaudeCodeBackend` runs `claude --print` as a subprocess. The gen-eval framework extends this:

- **Generator**: `claude --print "Given this interface descriptor, generate 5 edge-case scenarios for lock contention..."` → parsed as YAML Scenario objects
- **Evaluator (LLM judgment)**: `claude --print "Given this scenario verdict with these actual/expected mismatches, is this a real failure or a false positive? Explain..."` → structured judgment
- **Evaluator (programmatic)**: Schema validation, DB state checks, assertion matching → no LLM needed
- **SDK fallback**: If CLI returns rate-limit errors or the subscription hits session/weekly caps, the `AdaptiveBackend` transparently routes to the Anthropic/OpenAI SDK for remaining calls

Most evaluation is programmatic (free and instant). CLI-powered LLM is the default for generation and judgment. SDK kicks in only when CLI is exhausted or for SDK-specific features like structured outputs.

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM costs exceed budget | Hard budget cap with early termination; template-only CI default |
| Framework too complex for adoption | Minimal viable descriptor (just OpenAPI spec) gets value fast; full descriptor is progressive |
| Flaky from service startup timing | Health-check gates with retry; deterministic seed data; teardown between runs |
| Generator produces invalid scenarios | Schema validation on generated scenarios; fallback to templates on parse failure |
| Evaluator false positives | Confidence thresholds; deterministic checks preferred over LLM judgment; human review escape hatch |
| Scope creep beyond evaluation | Non-goal: not a general test framework. Stays focused on the gen-eval pattern. |

## Success Criteria

1. **Dogfood coverage**: Template scenarios achieve 80%+ interface coverage (unique interfaces exercised / total interfaces in descriptor × 100) across all 105+ agent-coordinator interfaces
2. **Template pass rate**: 95%+ of template scenarios pass against a clean docker-compose deployment (measured by `scenarios_passed / scenarios_executed`)
3. **Cross-interface consistency**: Cross-interface scenarios (category `cross-interface`) detect at least 1 state inconsistency across HTTP/MCP/CLI/DB that is not caught by existing unit or integration tests — verified by checking the inconsistency against `agent-coordinator/tests/` coverage
4. **CLI-augmented generation**: In `cli-augmented` mode, the generator produces at least 5 valid scenarios (passing Pydantic schema validation) per CLI invocation, and at least 1 generated scenario exercises an interface not covered by templates
5. **Time budget accuracy**: In `cli-augmented` mode, actual wall-clock time is within ±30% of `time_budget_minutes` configuration (measured across 3 runs)
6. **Reusable**: A second project can be onboarded by providing only an interface descriptor YAML — no Python code changes to the gen-eval framework needed. Verified by creating a minimal descriptor for a different service and running `template-only` mode.
