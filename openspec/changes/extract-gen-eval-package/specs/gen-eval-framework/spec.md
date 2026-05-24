# gen-eval-framework — Spec Delta

## ADDED Requirements

### Requirement: Distributable Python package

The gen-eval framework SHALL be distributed as a standalone, pip-installable Python package located at `packages/gen-eval/` within the `agentic-coding-tools` repository. The package SHALL declare a PEP 621-compliant `pyproject.toml` using `uv_build` (or compatible) as its build backend. Consumers SHALL install it via `uv add` from a relative path, git URL, or (in future) PyPI without needing to copy source files into their repositories.

#### Scenario: relative-path install from a sibling repository

- **WHEN** a consumer repository at `../<consumer-repo>` adds the dependency via `uv add ../agentic-coding-tools/packages/gen-eval`
- **THEN** `uv sync` SHALL install the package successfully without requiring network access to PyPI
- **AND** the consumer's Python environment SHALL be able to `import gen_eval` and resolve every public module declared in `packages/gen-eval/src/gen_eval/__init__.py`

#### Scenario: agent-coordinator consumes the package via uv path dependency

- **WHEN** `agent-coordinator/pyproject.toml` declares `gen-eval` as a path dependency with the `mcp` extra
- **AND** `uv sync` is run inside `agent-coordinator/`
- **THEN** the framework SHALL be importable as `from gen_eval import …` from anywhere within the coordinator's runtime
- **AND** no source code from `agent-coordinator/evaluation/gen_eval/` (the legacy in-tree location) SHALL remain in the tree

### Requirement: Canonical module name `gen_eval`

The framework's importable module name SHALL be `gen_eval` (underscore-separated, lowercase). The legacy import path `evaluation.gen_eval` SHALL be removed; consumers SHALL update their imports from `from evaluation.gen_eval import X` to `from gen_eval import X`. The CLI invocation form SHALL change from `python -m evaluation.gen_eval` to `python -m gen_eval`.

#### Scenario: CLI invocation under the new module name

- **WHEN** a consumer or skill runs `python -m gen_eval --descriptor <path>` inside a Python environment with `gen-eval` installed
- **THEN** the same evaluation pipeline that previously responded to `python -m evaluation.gen_eval --descriptor <path>` SHALL execute
- **AND** the exit code semantics, output artifacts (`gen-eval-report.{md,json}`, `findings-gen-eval.json`, `gen-eval-metrics.json`), and fail-threshold behavior SHALL be preserved bit-for-bit

#### Scenario: import path migration

- **WHEN** a downstream module imports `from evaluation.gen_eval import openspec_seed` (the legacy form)
- **THEN** after this change is applied, that import SHALL fail with `ModuleNotFoundError` (because the legacy path has been removed)
- **AND** the equivalent `from gen_eval import openspec_seed` SHALL resolve and provide the same API surface

### Requirement: Optional MCP service extra

The package SHALL provide an optional `[mcp]` extra that, when installed, adds the dependencies required to expose gen-eval as an MCP service (`fastmcp` and related). The base install (without the extra) SHALL be importable and runnable as a pure Python library / CLI without any MCP dependency present. The MCP service module (`gen_eval.mcp_service`) SHALL be conditionally importable: importing it without the `[mcp]` extra installed SHALL raise a clear `ImportError` instructing the consumer to install `gen-eval[mcp]`.

#### Scenario: base install lacks MCP dependencies

- **WHEN** a consumer installs `gen-eval` without specifying the `[mcp]` extra
- **AND** runs `python -c "import gen_eval; gen_eval.run_evaluation(...)"`
- **THEN** the import and call SHALL succeed without `fastmcp` being importable in the environment
- **AND** `python -c "from gen_eval.mcp_service import GenEvalMCPService"` SHALL raise `ImportError` with a message that names the missing `[mcp]` extra

#### Scenario: agent-coordinator installs the MCP extra and registers the service

- **WHEN** `agent-coordinator` declares its dependency as `gen-eval = { path = "../packages/gen-eval", extras = ["mcp"] }`
- **AND** `coordination_api.py` and `coordination_mcp.py` lazy-import `from gen_eval.mcp_service import get_gen_eval_service` at the request-handler level
- **THEN** the `/gen-eval/list-scenarios`, `/gen-eval/validate-scenario`, `/gen-eval/create-scenario`, and `/gen-eval/run` endpoints SHALL respond with the same payloads as before the extraction
- **AND** `mcp__coordination__create_scenario` (the existing MCP tool) SHALL continue to function with no caller-visible change

### Requirement: Framework / consumer data split

The package SHALL ship only framework-level artifacts (the Python source, its schemas/ directory, the dtu/ scaffolding templates, the test fixtures under `tests/fixtures/`, and the examples/ directory). Consumer-specific data — per-project interface descriptors, scenario libraries, and manifest YAMLs that describe a particular service under test — SHALL remain in the consumer repository. After this change, `agent-coordinator` SHALL keep its `descriptors/agent-coordinator.yaml`, all `manifests/*.manifest.yaml`, and the `scenarios/` tree relocated from `agent-coordinator/evaluation/gen_eval/` to `agent-coordinator/evaluation/{descriptors,manifests,scenarios}/`.

#### Scenario: package does not ship coordinator-specific descriptors

- **WHEN** the published package's contents are inspected (e.g., `uv build` produces an sdist)
- **THEN** the sdist SHALL NOT contain `descriptors/agent-coordinator.yaml`, any file under `manifests/`, or any scenario file that names a coordinator-specific resource (e.g., `lock-lifecycle/*.yaml`)
- **AND** the sdist SHALL contain `schemas/`, `dtu/`, `tests/fixtures/`, and `examples/` directories

#### Scenario: consumer descriptor discovery is consumer-controlled

- **WHEN** a consumer invokes `python -m gen_eval --descriptor <path-to-descriptor>` with an absolute or repo-relative path
- **THEN** the framework SHALL load that descriptor regardless of its location
- **AND** the framework SHALL NOT hardcode any consumer-side path conventions (no implicit `*/evaluation/gen_eval/descriptors/*.yaml` glob)

### Requirement: Documented consumer adoption contract

The package SHALL ship a `packages/gen-eval/examples/agentic-assistant-quickstart.md` document that walks a new consumer through the complete adoption path: `uv add` command, descriptor template, optional MCP install, and a worked example of running one scenario end-to-end. The package SHALL also ship a `packages/gen-eval/README.md` summarizing the public API, the two install profiles (base and `[mcp]`), and a pointer to the quickstart.

#### Scenario: a new consumer can adopt the package using only the shipped docs

- **WHEN** a developer who has never seen gen-eval before clones a sibling repo and follows the quickstart end-to-end
- **THEN** they SHALL produce a working `evaluation/descriptors/<consumer>.yaml`, install the package, and execute at least one scenario whose verdict appears in `gen-eval-report.md`
- **AND** the quickstart SHALL NOT require the developer to read any other gen-eval source file to complete the task

## MODIFIED Requirements

### Requirement: Module discovery and import boundary

The framework's public API SHALL be discoverable solely through the `gen_eval` top-level Python module (this replaces the prior packaging-implicit assumption that gen-eval was an in-tree module under `agent-coordinator/evaluation/gen_eval/`). Internal modules (`gen_eval.evaluator`, `gen_eval.orchestrator`, `gen_eval.clients.*`, `gen_eval.generator`, `gen_eval.openspec_seed`, `gen_eval.metrics`, etc.) SHALL be importable directly. The framework SHALL NOT depend on any module under `agent_coordinator.*` or `src.coordination_*`. The previously existing reverse coupling (`gen_eval/reports.py` importing `GenEvalMetrics` from `agent-coordinator/evaluation/metrics.py`) SHALL be resolved by **surgical extraction**: the `GenEvalMetrics` dataclass SHALL be moved into the package as `gen_eval/metrics.py`, while the remaining classes in `evaluation/metrics.py` (`TimingMetric`, `TokenUsage`, `CorrectnessMetrics`, `CoordinationMetrics`, `SafetyMetrics`, `ParallelizationMetrics`, `TaskMetrics`, `AggregatedMetrics`, `TrialMetrics`, `MetricsCollector`) and `compute_effect_size` SHALL remain in `agent-coordinator/evaluation/metrics.py` because they are coordinator-domain symbols consumed by `evaluation/ablation.py`, `evaluation/reports/generator.py`, and coordinator test code — they have no gen-eval consumers and have no business in a shared library.

#### Scenario: framework has zero imports from agent-coordinator

- **WHEN** static analysis is run over `packages/gen-eval/src/gen_eval/**/*.py` (e.g., `grep -rE "from (agent_coordinator|src\.coordination_)"`)
- **THEN** zero matches SHALL be reported
- **AND** the package's `pyproject.toml` SHALL NOT list `agent-coordinator` or any coordinator-internal module as a dependency

#### Scenario: optional coordinator integration remains a runtime concern, not an import-time dependency

- **WHEN** `gen_eval.coordinator` is imported in an environment where the coordinator HTTP API is unreachable
- **THEN** the import SHALL succeed without raising
- **AND** any subsequent method calls on the coordinator integration object SHALL degrade gracefully (log a warning, return empty results) as they do today

#### Scenario: gen_eval.metrics exposes only the gen-eval-specific symbol

- **WHEN** the contents of `gen_eval.metrics` are inspected (e.g., `set(dir(gen_eval.metrics)) - {x for x in dir(gen_eval.metrics) if x.startswith("_")}`)
- **THEN** the set SHALL be exactly `{"GenEvalMetrics"}` — no coordinator-domain classes (`TimingMetric`, `TokenUsage`, `CorrectnessMetrics`, `CoordinationMetrics`, `SafetyMetrics`, `ParallelizationMetrics`, `TaskMetrics`, `AggregatedMetrics`, `TrialMetrics`, `MetricsCollector`) and no `compute_effect_size` helper SHALL be re-exported
- **AND** `agent-coordinator/evaluation/metrics.py` SHALL continue to define and export the 10 coordinator-domain classes plus `compute_effect_size`, so existing in-coordinator imports (`evaluation.ablation`, `evaluation.reports.generator`, coordinator tests) continue to resolve unchanged
