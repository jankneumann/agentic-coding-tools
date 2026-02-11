## Context

The agent-coordinator project has implemented Phase 1 (locking, queue, MCP server) and adopted Agent Relay patterns for session continuity and discovery. Multiple coordination mechanisms exist (file locks, work queue, memory types, handoffs, verification tiers) but their effectiveness has never been measured empirically.

Recent research (2025-2026) provides relevant external benchmarks:
- **SWE-bench Verified** (500 human-validated GitHub issues) — the de facto standard for coding agent evaluation
- **MultiAgentBench / MARBLE** — evaluates coordination topologies (star, chain, tree, graph) with milestone-based KPIs
- **MAESTRO** — standardized multi-agent system evaluation with latency/cost/failure traces across 12 representative systems
- **Context-Bench** (Letta) — evaluates long-horizon context management and memory effectiveness
- **BFCL v4** (Berkeley) — tool use / function calling efficiency including multi-step agentic settings
- **ProjDevBench** — end-to-end project construction from specifications
- **"Towards a Science of Scaling Agent Systems"** (Google, 2025) — scaling laws showing tool-coordination tradeoffs, capability saturation at ~45%, topology-dependent error amplification

Key insight from the literature: architecture is the dominant driver of resource profiles and cost-latency-accuracy tradeoffs, often outweighing backend model choice. This validates measuring coordination mechanisms independently from agent backends.

## Goals / Non-Goals

**Goals:**
- Measure parallelization speedup and overhead for Task()-based coordination
- Compare agent backends (Claude Code, Codex, Gemini) on identical tasks
- Ablate coordination mechanisms to quantify individual value
- Evaluate memory effectiveness across session boundaries
- Adopt external benchmarks where feasible (SWE-bench, Context-Bench)
- Produce reproducible, statistically sound evaluation reports

**Non-Goals:**
- Building a general-purpose agent benchmark framework (we optimize for our coordination layer)
- Running the full SWE-bench suite (500 tasks at ~$5-50/task is expensive; we'll support subset sampling)
- Evaluating non-coding agent scenarios (web browsing, computer use)
- Real-time monitoring dashboards (batch evaluation only for now)
- Comparing raw LLM capabilities without coordination (HumanEval/MBPP already cover this)

## Decisions

### Task Suite Design

**Decision**: Create a 3-tier task suite with increasing coordination requirements.

- **Tier 1 — Isolated tasks** (10-15 tasks): Single-file changes that test raw agent capability without coordination. Baseline measurement. Examples: bug fixes, refactors, adding a function.
- **Tier 2 — Parallelizable tasks** (10-15 tasks): Multi-file changes where subtasks are independent. Tests Task() parallelization benefit. Examples: add feature + tests + docs across 3 files.
- **Tier 3 — Coordinated tasks** (5-10 tasks): Multi-file changes with dependencies requiring locking, handoffs, or sequential execution. Tests coordination mechanism value. Examples: schema migration + API update + client update.

**Task sourcing**: Start with external OSS tasks — SWE-bench Verified subsets provide well-tested, reproducible tasks with golden patches. Supplement with curated tasks from open-source repos that exercise multi-file coordination patterns. Add internal curated tasks over time.

**Rationale**: This mirrors our actual usage pattern (skill workflow → parallel exploration → coordinated implementation). The tiers let us measure parallelization benefit (T2 vs T1 sequential) and coordination overhead (T3 with/without mechanisms). Starting with external tasks avoids the cold-start problem of authoring quality benchmark tasks.

### Metrics Framework

**Decision**: Capture 5 metric categories, inspired by MAESTRO and "Scaling Agent Systems".

| Category | Metrics |
|----------|---------|
| **Correctness** | Task pass rate, test pass rate, spec compliance score |
| **Efficiency** | Wall-clock time, total tokens consumed, API cost, coordination overhead (time in lock/unlock, memory read/write vs productive work) |
| **Parallelization** | Speedup factor (parallel/sequential), Amdahl efficiency, merge conflict rate |
| **Coordination** | Lock contention rate, memory hit rate, handoff continuity score, dead agent recovery time |
| **Scaling** | Performance vs agent count curve, coordination overhead growth rate |

### External Benchmark Adapters

**Decision**: Build thin adapters for 3 external benchmarks, prioritized by relevance.

1. **SWE-bench Verified adapter** (high priority): Load task definitions from HuggingFace dataset, run through our coordination layer, compare with published baselines. Supports subset sampling for cost control.
2. **Context-Bench adapter** (medium priority): Evaluates memory effectiveness using Letta's multi-step context tasks. Maps to our episodic/working memory.
3. **MultiAgentBench/MARBLE adapter** (lower priority): Tests coordination topology variations. Our Task() pattern maps to their "star" topology; useful for comparing against graph/chain patterns.

**Rationale**: SWE-bench is the industry standard and lets us compare against published results. Context-Bench directly tests our memory subsystem. MultiAgentBench is less directly applicable but provides topology comparison data.

### Ablation Design

**Decision**: Use a factorial design with coordination mechanisms as binary factors.

Factors to toggle:
- File locking: ON/OFF (OFF = no lock acquisition, rely on file scope isolation)
- Memory: ON/OFF (OFF = no episodic/procedural memory between tasks)
- Handoffs: ON/OFF (OFF = agents start cold each task)
- Parallelization: ON/OFF (OFF = sequential execution only)
- Work queue: ON/OFF (OFF = direct task assignment, no queue)

Run each configuration on the full Tier 2 + Tier 3 suite. Full factorial = 32 configs × ~25 tasks = ~800 runs. At $1-2 budget per extensive eval, use fractional factorial (e.g., 8 key configs) as default; full factorial only on explicit request.

### Execution Architecture

**Decision**: Python-based harness using existing agent-coordinator infrastructure.

```
evaluation/
├── __init__.py
├── harness.py          # Orchestrates evaluation runs
├── metrics.py          # Collects and aggregates metrics
├── config.py           # Evaluation configuration (task selection, agent config, ablation flags)
├── tasks/
│   ├── __init__.py
│   ├── registry.py     # Task discovery and metadata
│   ├── tier1/          # Isolated tasks (YAML + golden patches)
│   ├── tier2/          # Parallelizable tasks
│   └── tier3/          # Coordinated tasks
├── adapters/
│   ├── __init__.py
│   ├── swebench.py     # SWE-bench Verified adapter
│   ├── contextbench.py # Context-Bench adapter
│   └── marble.py       # MultiAgentBench adapter
├── reports/
│   ├── __init__.py
│   └── generator.py    # Report generation (markdown + JSON)
└── conftest.py         # Pytest fixtures for evaluation
```

**Rationale**: Python matches our tech stack. The harness wraps existing coordination primitives, so we measure the real system, not a mock. Tasks are defined as YAML metadata + golden patches (similar to SWE-bench format) for reproducibility.

## Risks / Trade-offs

- **Cost**: Target $1-2 per extensive eval run. Mitigation: subset sampling (default 5-10 tasks per run), cache intermediate results, avoid full factorial unless explicitly requested. Reuse existing Claude/Gemini/Codex accounts.
- **Reproducibility**: LLM outputs are non-deterministic. Mitigation: run N trials per config (default 3), report effect sizes with confidence intervals, use temperature=0 where possible.
- **Task quality**: Poorly designed tasks may not discriminate between configurations. Mitigation: start with proven external tasks (SWE-bench subsets), pilot test before including in suite.
- **Consensus eval subjectivity**: LLM judges may disagree or exhibit bias. Mitigation: use 2-3 different LLMs as judges, report agreement rate, weight by known judge quality.

## Resolved Questions

1. **Budget per full evaluation run**: Target $1-2 per extensive evaluation run. Reuse existing accounts for Claude, Gemini, and Codex. This constrains the suite to ~13-25 tasks per run depending on complexity. Subset sampling and caching are essential.
2. **Gemini/Jules access**: Available via CLI — implement as a full backend adapter (not a stub). All three backends (Claude Code, Codex, Gemini/Jules) are CLI-accessible.
3. **Statistical rigor**: Use effect sizes with confidence intervals, plus qualitative consensus evaluations using multiple LLMs as judges. No p-value thresholds — instead, have 2-3 LLMs independently assess output quality and report agreement rate. This gives both quantitative (effect size) and qualitative (consensus) signals.
4. **Task sources**: Use both external OSS source code tasks and curated internal tasks. Start with external tasks (SWE-bench subsets, open-source repos) since internal tasks aren't available yet. Add curated tasks over time as the coordination system matures.
