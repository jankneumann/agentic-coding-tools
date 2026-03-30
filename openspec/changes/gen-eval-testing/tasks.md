# Tasks: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`

## Task Breakdown

### Phase 1: Foundation (Core Data Models + Configuration)

- [ ] **T1.1**: Create `evaluation/gen_eval/__init__.py` with package exports
- [ ] **T1.2**: Create `evaluation/gen_eval/config.py` — `GenEvalConfig`, `BudgetConfig`, `BudgetTracker` with YAML loading and CLI arg parsing
- [ ] **T1.3**: Create `evaluation/gen_eval/descriptor.py` — `InterfaceDescriptor`, `ServiceDescriptor`, `StateVerifier`, `StartupConfig` Pydantic models with YAML parsing
- [ ] **T1.4**: Create `evaluation/gen_eval/models.py` — `Scenario`, `ActionStep`, `ExpectBlock`, `ScenarioVerdict`, `StepVerdict` data models
- [ ] **T1.5**: Write unit tests for config, descriptor, and model parsing (`tests/test_evaluation/test_gen_eval/test_config.py`, `test_descriptor.py`, `test_models.py`)
- [ ] **T1.6**: Update `pyproject.toml` — add optional `gen-eval` dependency group (httpx, asyncpg, pyyaml already present; add jinja2 for template parameterization)

### Phase 2: Transport Clients

- [ ] **T2.1**: Create `evaluation/gen_eval/clients/__init__.py` and `base.py` — `TransportClient` protocol and `TransportClientRegistry`
- [ ] **T2.2**: Create `evaluation/gen_eval/clients/http_client.py` — httpx-based HTTP client with auth injection, response capture, variable interpolation
- [ ] **T2.3**: Create `evaluation/gen_eval/clients/mcp_client.py` — MCP client using fastmcp SDK (SSE transport) with tool invocation and response parsing
- [ ] **T2.4**: Create `evaluation/gen_eval/clients/cli_client.py` — subprocess-based CLI client with JSON output parsing, exit code checking, timeout handling
- [ ] **T2.5**: Create `evaluation/gen_eval/clients/db_client.py` — asyncpg-based database verification client for state checking (SELECT only, no mutations)
- [ ] **T2.6**: Create `evaluation/gen_eval/clients/wait_client.py` — simple asyncio.sleep client for timing-dependent scenarios
- [ ] **T2.7**: Create `evaluation/gen_eval/clients/browser_client.py` — Playwright stub (raises NotImplementedError with guidance for future frontend projects)
- [ ] **T2.8**: Write unit tests for all clients with mocked backends (`tests/test_evaluation/test_gen_eval/test_clients.py`)

### Phase 3: Generator

- [ ] **T3.1**: Create `evaluation/gen_eval/generator.py` — `TemplateGenerator` that loads YAML templates, parameterizes with Jinja2, validates against Scenario schema
- [ ] **T3.2**: Create `evaluation/gen_eval/scenarios/` directory structure with category subdirs: `lock-lifecycle/`, `work-queue/`, `memory-crud/`, `guardrails/`, `auth-boundary/`, `cross-interface/`, `multi-agent/`, `handoffs/`, `audit-trail/`, `policy-engine/`, `feature-registry/`, `merge-queue/`
- [ ] **T3.3**: Write template scenarios for `lock-lifecycle` category (8 templates: acquire, release, conflict, TTL expiry, cross-interface verify, bulk check, agent-specific, re-acquire after release)
- [ ] **T3.4**: Write template scenarios for `work-queue` category (10 templates: submit, claim, complete, dependencies, priority ordering, claim filtering, error completion, get task, cross-interface)
- [ ] **T3.5**: Write template scenarios for `auth-boundary` category (8 templates: valid API key, missing key, invalid key, read-only no auth, profile trust levels, guardrail enforcement, policy denial, cross-interface auth)
- [ ] **T3.6**: Write template scenarios for `cross-interface` category (10 templates: lock via each interface, memory via each interface, work queue via each interface, mixed operations)
- [ ] **T3.7**: Write template scenarios for remaining categories: `guardrails` (5), `memory-crud` (6), `handoffs` (4), `audit-trail` (4), `policy-engine` (5), `feature-registry` (6), `merge-queue` (6)
- [ ] **T3.8**: Create `evaluation/gen_eval/llm_generator.py` — LLM-powered scenario generator that reads the interface descriptor, uses evaluator feedback, and produces validated Scenario objects
- [ ] **T3.9**: Create `evaluation/gen_eval/hybrid_generator.py` — combines template and LLM generation with budget-aware switching
- [ ] **T3.10**: Write unit tests for generators (`tests/test_evaluation/test_gen_eval/test_generator.py`)

### Phase 4: Evaluator

- [ ] **T4.1**: Create `evaluation/gen_eval/evaluator.py` — `Evaluator` class that executes scenarios step-by-step through transport clients, compares actual vs expected, produces `ScenarioVerdict`
- [ ] **T4.2**: Implement variable capture and interpolation — `capture` fields extract values from responses, `{{ var }}` syntax injects into subsequent steps
- [ ] **T4.3**: Implement cleanup step execution — always runs after scenario (even on failure), uses best-effort error handling
- [ ] **T4.4**: Implement cross-interface consistency checks — verify same state across multiple transport responses
- [ ] **T4.5**: Write unit tests for evaluator (`tests/test_evaluation/test_gen_eval/test_evaluator.py`)

### Phase 5: Feedback + Change Detection

- [ ] **T5.1**: Create `evaluation/gen_eval/feedback.py` — `FeedbackSynthesizer` that analyzes verdicts to identify failing interfaces, under-tested categories, and near-misses
- [ ] **T5.2**: Create `evaluation/gen_eval/change_detector.py` — detect changed endpoints/tools/commands from git diff and/or OpenSpec change-context.md
- [ ] **T5.3**: Write unit tests for feedback and change detection (`tests/test_evaluation/test_gen_eval/test_feedback.py`)

### Phase 6: Orchestrator

- [ ] **T6.1**: Create `evaluation/gen_eval/orchestrator.py` — `GenEvalOrchestrator` managing full lifecycle: service startup → generation → prioritization → evaluation → feedback → iteration → reporting → teardown
- [ ] **T6.2**: Implement budget-aware progressive execution — tier 1 (changed) first, tier 2 (critical) second, tier 3 (full) third; early termination when budget exhausted
- [ ] **T6.3**: Implement parallel scenario execution — asyncio.gather with configurable concurrency limit
- [ ] **T6.4**: Implement service lifecycle management — docker-compose up/down with health check gates and retry logic
- [ ] **T6.5**: Write unit tests for orchestrator (`tests/test_evaluation/test_gen_eval/test_orchestrator.py`)

### Phase 7: Reporting + Metrics Integration

- [ ] **T7.1**: Create `evaluation/gen_eval/reports.py` — generate markdown + JSON reports with per-interface/per-category verdicts, coverage metrics, cost summary
- [ ] **T7.2**: Extend `evaluation/metrics.py` — add `GenEvalMetrics` dataclass (scenario_id, interface, verdict, duration, category) compatible with existing `MetricsCollector`
- [ ] **T7.3**: Write unit tests for reports and metrics (`tests/test_evaluation/test_gen_eval/test_reports.py`)

### Phase 8: Dogfood Interface Descriptor

- [ ] **T8.1**: Create `evaluation/gen_eval/descriptors/agent-coordinator.yaml` — full interface descriptor covering all 35 HTTP endpoints, 39 MCP tools, 31 CLI commands, PostgreSQL state verifier, docker-compose startup
- [ ] **T8.2**: Create `evaluation/gen_eval/schemas/` — JSON schemas for expected response shapes extracted from coordination_api.py Pydantic models

### Phase 9: CLI + Skill Entry Points

- [ ] **T9.1**: Create `evaluation/gen_eval/__main__.py` — CLI entry point with argparse/click for running gen-eval from command line
- [ ] **T9.2**: Create `skills/gen-eval/SKILL.md` — skill spec for `/gen-eval` invocation
- [ ] **T9.3**: Update `skills/validate-feature/SKILL.md` — add gen-eval as optional validation phase

### Phase 10: Integration Testing (Live Services)

- [ ] **T10.1**: Write integration test that runs template-only evaluation against docker-compose services for lock-lifecycle category
- [ ] **T10.2**: Write integration test that runs cross-interface scenarios verifying HTTP↔MCP↔CLI↔DB consistency
- [ ] **T10.3**: Write integration test that runs the full orchestrator with template-only mode and verifies report output

### Phase 11: Coordinator Integration (Optional)

- [ ] **T11.1**: Create `evaluation/gen_eval/coordinator.py` — optional coordinator integration for distributed scenario execution via work queue, memory storage for findings, audit logging
- [ ] **T11.2**: Write unit tests for coordinator integration

### Phase 12: CI Integration

- [ ] **T12.1**: Add `gen-eval` job to `.github/workflows/ci.yml` — template-only mode, runs against docker-compose services, conservative budget
- [ ] **T12.2**: Update `evaluation/__init__.py` — export gen_eval module

## Dependencies

```
T1.* → T2.* → T3.1 → T4.1 → T6.1 → T7.1
              T3.2-T3.7 (parallel with T4.*)
              T3.8-T3.9 → T5.1
              T5.2 (parallel)
T8.* (parallel with T3-T7)
T9.* (after T6.1)
T10.* (after T6.1 + T8.*)
T11.* (after T6.1, optional)
T12.* (after T10.*)
```

## Estimation

| Phase | Tasks | Complexity | Notes |
|-------|-------|-----------|-------|
| Phase 1: Foundation | 6 | Medium | Core models, well-defined |
| Phase 2: Clients | 8 | Medium | Most clients straightforward; MCP client needs care |
| Phase 3: Generator | 10 | High | Template authoring is bulk of work (80 scenarios) |
| Phase 4: Evaluator | 5 | High | Variable capture + cross-interface is complex |
| Phase 5: Feedback | 3 | Medium | Analysis logic |
| Phase 6: Orchestrator | 5 | High | Lifecycle management, budget, parallelism |
| Phase 7: Reporting | 3 | Low | Builds on existing report infrastructure |
| Phase 8: Dogfood | 2 | Medium | Descriptor for 105+ interfaces |
| Phase 9: Entry Points | 3 | Low | CLI + skill wiring |
| Phase 10: Integration | 3 | Medium | Requires docker-compose services |
| Phase 11: Coordinator | 2 | Low | Optional, uses existing coordinator APIs |
| Phase 12: CI | 2 | Low | GitHub Actions config |
| **Total** | **52** | | |
