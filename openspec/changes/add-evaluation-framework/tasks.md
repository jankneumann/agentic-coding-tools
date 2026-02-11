## 1. Core Framework

- [x] 1.1 Create `evaluation/` module structure with `__init__.py`, `config.py`, `harness.py`, `metrics.py`
- [x] 1.2 Implement `EvalConfig` dataclass with task selection, agent config, ablation flags, and trial count
- [x] 1.3 Implement `MetricsCollector` class that instruments coordination primitives (lock/unlock timing, memory read/write, token usage)
- [x] 1.4 Implement `EvalHarness` that orchestrates: load config → select tasks → run trials → collect metrics → generate report
- [x] 1.5 Add pytest fixtures for evaluation runs in `conftest.py`

## 2. Task Suite

- [x] 2.1 Define task YAML schema (metadata: id, tier, source, description, difficulty, parallelizable_subtasks, affected_files, golden_patch, test_command)
- [x] 2.2 Select and adapt 5 Tier 1 tasks from SWE-bench Verified (isolated, single-file bug fixes and refactors)
- [x] 2.3 Select and adapt 5 Tier 2 tasks from OSS repos (parallelizable, multi-file: feature + tests + docs across independent files)
- [x] 2.4 Select and adapt 3 Tier 3 tasks from OSS repos (coordinated, dependent: schema migration + API + client with ordering constraints)
- [x] 2.5 Implement `TaskRegistry` for discovering and loading tasks from YAML files (supports both external-sourced and curated tasks)

## 3. Metrics and Reporting

- [x] 3.1 Implement timing instrumentation wrappers for coordination operations (lock, memory, queue, handoff)
- [x] 3.2 Implement token usage tracking via API response metadata
- [x] 3.3 Implement correctness scoring (test pass rate, patch match ratio)
- [x] 3.4 Implement statistical aggregation (mean, median, CI, effect sizes across trials)
- [x] 3.5 Implement multi-LLM consensus evaluator — submit outputs to 2-3 LLMs for qualitative assessment, report agreement rate and qualitative scores
- [x] 3.6 Implement report generator outputting markdown table + JSON (per-task results, per-config summary, ablation comparison, consensus eval summary)

## 4. Ablation Support

- [x] 4.1 Implement coordination mechanism toggles in `EvalConfig` (locking, memory, handoffs, parallelization, queue)
- [x] 4.2 Implement ablation runner that iterates over toggle combinations (full or fractional factorial)
- [x] 4.3 Implement ablation comparison report showing mechanism contribution (delta from baseline per mechanism)

## 5. External Benchmark Adapters

- [x] 5.1 Implement `SWEBenchAdapter` — load tasks from HuggingFace dataset, convert to internal task format, support subset sampling
- [x] 5.2 Implement `ContextBenchAdapter` — load Letta Context-Bench tasks, map to memory subsystem evaluation
- [x] 5.3 Implement `MARBLEAdapter` — load MultiAgentBench scenarios, map coordination topologies to Task() patterns

## 6. Agent Backend Adapters

- [x] 6.1 Define `AgentBackend` protocol (interface for submitting tasks and collecting results)
- [x] 6.2 Implement `ClaudeCodeBackend` — wraps Claude Code CLI / Task() invocations
- [x] 6.3 Implement `CodexBackend` — wraps Codex CLI for comparison runs
- [x] 6.4 Implement `GeminiJulesBackend` — wraps Gemini/Jules CLI for comparison runs

## 7. Documentation and Validation

- [x] 7.1 Write `evaluation/README.md` with usage guide (running a benchmark suite, interpreting reports, adding tasks)
- [x] 7.2 Add unit tests for metrics collection, task registry, and report generation
- [ ] 7.3 Run pilot evaluation: 3 Tier 1 tasks × 2 configs (with/without parallelization) × 3 trials
- [ ] 7.4 Validate pilot results against manual observation
