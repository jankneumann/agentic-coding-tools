# Tasks: Generator-Evaluator Testing Framework

**Change ID**: `gen-eval-testing`

## Task Breakdown

### Phase 1: Foundation (Core Data Models + Configuration)

- [ ] **T1.1**: Create `evaluation/gen_eval/__init__.py` with package exports
- [ ] **T1.2**: Create `evaluation/gen_eval/config.py` — `GenEvalConfig`, `BudgetConfig`, `TimeBudget`, `SDKBudget`, `BudgetTracker` with YAML loading and CLI arg parsing. Also update `pyproject.toml` to add optional `gen-eval` dependency group (add jinja2; httpx, asyncpg, pyyaml already present).
- [ ] **T1.3**: Create `evaluation/gen_eval/descriptor.py` — `InterfaceDescriptor`, `ServiceDescriptor`, `StateVerifier`, `StartupConfig` Pydantic models with YAML parsing and validation
- [ ] **T1.4**: Create `evaluation/gen_eval/models.py` — `Scenario`, `ActionStep`, `ExpectBlock`, `ScenarioVerdict`, `StepVerdict` data models. Includes `ScenarioGenerator` protocol definition.
- [ ] **T1.5**: Write unit tests for config, descriptor, and model parsing (`tests/test_evaluation/test_gen_eval/test_config.py`, `test_descriptor.py`, `test_models.py`). Also create `tests/test_evaluation/test_gen_eval/conftest.py` with shared fixtures (sample descriptors, sample scenarios, mock backends) — this file is owned by wp-foundation and read-only for other packages.

### Phase 2: Transport Clients

- [ ] **T2.1**: Create `evaluation/gen_eval/clients/__init__.py` and `base.py` — `TransportClient` protocol with `execute()`, `health_check()`, `cleanup()` methods, `TransportClientRegistry`, and `StepResult` dataclass
- [ ] **T2.2**: Create `evaluation/gen_eval/clients/http_client.py` — httpx-based HTTP client with auth injection, response capture, configurable per-step timeout (default: 30s)
- [ ] **T2.3**: Create `evaluation/gen_eval/clients/mcp_client.py` — MCP client using fastmcp SDK (SSE transport) with tool invocation and response parsing
- [ ] **T2.4**: Create `evaluation/gen_eval/clients/cli_client.py` — subprocess-based CLI client with JSON output parsing, exit code checking, configurable timeout
- [ ] **T2.5**: Create `evaluation/gen_eval/clients/db_client.py` — asyncpg-based database verification client for state checking (SELECT only, no mutations)
- [ ] **T2.6**: Create `evaluation/gen_eval/clients/wait_client.py` — simple asyncio.sleep client for timing-dependent scenarios
- [ ] **T2.7**: Write unit tests for all clients with mocked backends (`tests/test_evaluation/test_gen_eval/test_clients.py`)

### Phase 3: Generator

- [ ] **T3.1**: Create `evaluation/gen_eval/generator.py` — `TemplateGenerator` that loads YAML templates, parameterizes with Jinja2 (with configurable `max_expansions` cap, default: 100), validates against `Scenario` Pydantic schema. Invalid scenarios are logged and skipped.
- [ ] **T3.2**: Create `evaluation/gen_eval/scenarios/` directory structure with category subdirs: `lock-lifecycle/`, `work-queue/`, `memory-crud/`, `guardrails/`, `auth-boundary/`, `cross-interface/`, `multi-agent/`, `handoffs/`, `audit-trail/`, `policy-engine/`, `feature-registry/`, `merge-queue/`
- [ ] **T3.3**: Write template scenarios for `lock-lifecycle` category (8 templates: 4 success + 4 failure/edge — acquire, release, conflict, TTL expiry, cross-interface verify, re-acquire after release, acquire-already-held-fails, release-not-held-fails)
- [ ] **T3.4**: Write template scenarios for `work-queue` category (10 templates: 5 success + 5 failure — submit, claim, complete, dependencies, priority ordering, claim-no-tasks, complete-wrong-agent, dependency-not-met, duplicate-submit, get-nonexistent)
- [ ] **T3.5**: Write template scenarios for `auth-boundary` category (8 templates: 3 success + 5 failure — valid API key, missing key rejected, invalid key rejected, read-only-no-auth, profile trust enforcement, guardrail blocking, policy denial, cross-interface auth consistency)
- [ ] **T3.6**: Write template scenarios for `cross-interface` category (10 templates: 5 success + 5 failure — lock via HTTP→verify MCP→release CLI→verify DB, memory store→query cross-interface, work submit→claim cross, state-mismatch-detection, cleanup-across-interfaces)
- [ ] **T3.7**: Write template scenarios for remaining categories — each with both success AND failure/edge paths: `guardrails` (5: 2+3), `memory-crud` (6: 3+3), `handoffs` (4: 2+2), `audit-trail` (4: 2+2), `policy-engine` (6: 3+3), `feature-registry` (6: 3+3), `merge-queue` (6: 3+3)
- [ ] **T3.8**: Create `evaluation/gen_eval/cli_generator.py` — `CLIGenerator` class: builds prompt from interface descriptor + template examples + evaluator feedback, executes via `claude --print` or `codex` subprocess, parses YAML output into `Scenario` objects, validates against schema. Implements `ScenarioGenerator` protocol.
- [ ] **T3.9**: Create `evaluation/gen_eval/sdk_generator.py` — `SDKGenerator` class: same generation logic but via Anthropic/OpenAI SDK. Implements `ScenarioGenerator` protocol. Per-token cost, used in `sdk-only` mode or as `AdaptiveBackend` fallback.
- [ ] **T3.10**: Create `evaluation/gen_eval/hybrid_generator.py` — `HybridGenerator` class: composes `TemplateGenerator` + `CLIGenerator` + `SDKGenerator` with `AdaptiveBackend` for transparent CLI→SDK fallback. Detects rate limiting by checking: non-zero exit code + stderr matching configurable patterns (default: "rate limit", "too many requests", "quota exceeded", HTTP 429).
- [ ] **T3.11**: Write unit tests for all generators (`tests/test_evaluation/test_gen_eval/test_generator.py`, `test_cli_generator.py`, `test_sdk_generator.py`, `test_hybrid_generator.py`)

### Phase 4: Evaluator

- [ ] **T4.1**: Create `evaluation/gen_eval/evaluator.py` — `Evaluator` class that executes scenarios step-by-step (sequentially) through transport clients, compares actual vs expected using JSONPath assertions, produces `ScenarioVerdict`
- [ ] **T4.2**: Implement variable capture (JSONPath `$.field.path` → variable) and interpolation (`{{ var }}` → value in subsequent steps). Invalid JSONPath expressions produce step-level `error` verdict, not crash.
- [ ] **T4.3**: Implement cleanup step execution — always runs after scenario (even on failure). Cleanup step failures are recorded as warnings in the verdict but do NOT change the scenario's pass/fail status.
- [ ] **T4.4**: Implement cross-interface consistency checks — verify same state across multiple transport responses. State mismatches produce structured diffs showing both responses.
- [ ] **T4.5**: Write unit tests for evaluator (`tests/test_evaluation/test_gen_eval/test_evaluator.py`) — include tests for: variable capture, cleanup failure handling, cross-interface mismatch detection, step timeout behavior

### Phase 5: Feedback + Change Detection

- [ ] **T5.1**: Create `evaluation/gen_eval/feedback.py` — `FeedbackSynthesizer` that analyzes `ScenarioVerdict` list to compute: failing interfaces (endpoint names with fail verdicts), under-tested categories (< 50% scenario coverage), near-miss scenarios (passed but > 500ms latency or partial matches), suggested focus areas. Output: `EvalFeedback` model.
- [ ] **T5.2**: Create `evaluation/gen_eval/change_detector.py` — `ChangeDetector` that parses `git diff --name-only <ref>` output and maps changed source files to interface endpoints using a file-to-interface mapping from the descriptor. Falls back to empty list if git diff fails or change-context.md is absent.
- [ ] **T5.3**: Write unit tests for feedback and change detection (`tests/test_evaluation/test_gen_eval/test_feedback.py`)

### Phase 6: Orchestrator

- [ ] **T6.1**: Create `evaluation/gen_eval/orchestrator.py` — `GenEvalOrchestrator` managing full lifecycle: service startup (with configurable retry + backoff on health check failure) → seed data → generation → prioritization by budget tier → evaluation → feedback → iteration → reporting → teardown. Aborts with clear error if health check fails after all retries.
- [ ] **T6.2**: Implement budget-aware progressive execution — tier 1 (changed, 40%) first, tier 2 (critical, 35%) second, tier 3 (full, 25%) third. Time-based for CLI mode, USD-based for SDK mode. Graceful termination: complete current scenario, skip rest, set `budget_exhausted: true` in report.
- [ ] **T6.3**: Implement parallel scenario execution — `asyncio.Semaphore(N)` with configurable concurrency limit (default: 5) to prevent overloading docker-compose services.
- [ ] **T6.4**: Implement service lifecycle management — `docker-compose up -d` with health check polling (configurable interval, timeout, retry count), `docker-compose down -v` on teardown.
- [ ] **T6.5**: Write unit tests for orchestrator (`tests/test_evaluation/test_gen_eval/test_orchestrator.py`)

### Phase 7: Reporting + Metrics Integration

- [ ] **T7.1**: Create `evaluation/gen_eval/reports.py` — generate markdown + JSON reports with: per-interface verdict (pass/fail/error), per-category summary, interface coverage % (= unique interfaces tested / total in descriptor × 100), time/cost summary, unevaluated interfaces list, `budget_exhausted` flag.
- [ ] **T7.2**: Extend `evaluation/metrics.py` — add `GenEvalMetrics` dataclass (scenario_id, interface, verdict, duration, category, backend_used) compatible with existing `MetricsCollector`. Declare `evaluation/metrics.py` as write target.
- [ ] **T7.3**: Write unit tests for reports and metrics (`tests/test_evaluation/test_gen_eval/test_reports.py`)

### Phase 8: Dogfood Interface Descriptor

- [ ] **T8.1a**: Create `evaluation/gen_eval/descriptors/agent-coordinator.yaml` — descriptor structure, startup/teardown config, PostgreSQL state verifier, and all 35 HTTP API endpoint definitions with auth config
- [ ] **T8.1b**: Extend `agent-coordinator.yaml` with all 39 MCP tool definitions and all 31 CLI command definitions
- [ ] **T8.2**: Create `evaluation/gen_eval/schemas/` — JSON schemas for expected response shapes extracted from coordination_api.py Pydantic models
- [ ] **T8.3**: Verify docker-compose.yml against current agent-coordinator source — ensure all endpoints, auth, and startup config in descriptor match actual services

### Phase 9: CLI + Skill Entry Points

- [ ] **T9.1**: Create `evaluation/gen_eval/__main__.py` — CLI entry point with argparse for running gen-eval. Supports all three modes (`template-only`, `cli-augmented`, `sdk-only`), `--cli-command`, `--time-budget`, `--sdk-budget`, `--changed-features-ref` flags.
- [ ] **T9.2**: Create `skills/gen-eval/SKILL.md` — skill spec for `/gen-eval` invocation with parameter documentation
- [ ] **T9.3**: Update `skills/validate-feature/SKILL.md` — add gen-eval as optional validation phase between smoke and E2E (runs template-only by default)

### Phase 10: Integration Testing (Live Services)

- [ ] **T10.1**: Write integration test that runs template-only evaluation against docker-compose services for `lock-lifecycle` category (success + failure scenarios)
- [ ] **T10.2**: Write integration test that runs `cross-interface` scenarios verifying HTTP↔MCP↔CLI↔DB consistency
- [ ] **T10.3**: Write integration test for `auth-boundary` category — verify API key enforcement, trust levels, and policy denial against live services
- [ ] **T10.4**: Write integration test for `work-queue` category — submit, claim, complete, dependencies against live services
- [ ] **T10.5**: Write integration test that runs the full orchestrator with `template-only` mode and verifies: report output, coverage metric calculation, budget tracking accuracy
- [ ] **T10.6**: Write integration test for `AdaptiveBackend` fallback — mock CLI rate-limit response, verify SDK fallback triggers

### Phase 11: Coordinator Integration (Optional)

- [ ] **T11.1**: Create `evaluation/gen_eval/coordinator.py` — optional coordinator integration for distributed scenario execution via work queue, memory storage for findings, audit logging. When coordinator unavailable, log info and continue standalone.
- [ ] **T11.2**: Write unit tests for coordinator integration (with mocked coordinator client)

### Phase 12: CI Integration

- [ ] **T12.1**: Add `gen-eval` job to `.github/workflows/ci.yml` — `template-only` mode, runs against docker-compose services, 10-minute timeout, fail-fast on 3 consecutive failures, triggered only on PRs that modify `agent-coordinator/` files
- [ ] **T12.2**: Update `evaluation/__init__.py` — export gen_eval module

## Dependencies

```
T1.* → T2.* → T3.1 → T4.1 → T6.1 → T7.1
              T3.2-T3.7 (parallel with T4.*)
              T3.8-T3.10 → T5.1
              T5.2 (parallel)
T8.* (parallel with T3-T7)
T9.* (after T6.1 + T3.10)  ← needs hybrid generator for mode switching
T10.* (after T6.1 + T8.*)
T11.* (after T6.1, optional)
T12.* (after T10.*)
```

## Estimation

| Phase | Tasks | Complexity | Notes |
|-------|-------|-----------|-------|
| Phase 1: Foundation | 5 | Medium | Core models, well-defined; T1.6 merged into T1.2 |
| Phase 2: Clients | 7 | Medium | Most clients straightforward; MCP client needs care; browser stub removed |
| Phase 3: Generator | 11 | High | Template authoring is bulk of work (81 scenarios across 12 categories) |
| Phase 4: Evaluator | 5 | High | Variable capture + cross-interface is complex |
| Phase 5: Feedback | 3 | Medium | Analysis logic with concrete metric definitions |
| Phase 6: Orchestrator | 5 | High | Lifecycle management, budget, parallelism |
| Phase 7: Reporting | 3 | Low | Builds on existing report infrastructure |
| Phase 8: Dogfood | 4 | High | Descriptor for 105+ interfaces split into manageable chunks |
| Phase 9: Entry Points | 3 | Low | CLI + skill wiring |
| Phase 10: Integration | 6 | Medium | Expanded to cover 4 categories + orchestrator + adaptive fallback |
| Phase 11: Coordinator | 2 | Low | Optional, uses existing coordinator APIs |
| Phase 12: CI | 2 | Low | GitHub Actions config, triggered on agent-coordinator changes |
| **Total** | **56** | | |
