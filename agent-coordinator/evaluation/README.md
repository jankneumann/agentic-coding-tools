# Evaluation Framework

Scenario-driven benchmarking infrastructure for measuring agent coordination effectiveness.

## Quick Start

```python
from evaluation import EvalConfig, EvalHarness
from evaluation.backends import ClaudeCodeBackend
from evaluation.tasks import TaskRegistry

# Load tasks
registry = TaskRegistry()

# Configure evaluation
config = EvalConfig(
    tiers=[TaskTier.TIER1, TaskTier.TIER2],
    num_trials=3,
    output_dir="evaluation/reports",
)

# Set up backend
backend = ClaudeCodeBackend()

# Run evaluation
harness = EvalHarness(config=config, registry=registry, backends=[backend])
result = await harness.run(working_dir="/path/to/repo")

print(f"Success rate: {result.overall_success_rate:.0%}")
print(f"Report: {result.markdown_report}")
```

## Configuration

Create a YAML configuration file:

```yaml
tiers: [1, 2]
num_trials: 3
temperature: 0.0
max_tasks: 10

backends:
  - name: claude_code
    command: claude
    args: ["--print"]
    timeout_seconds: 300
  - name: codex
    command: codex
    timeout_seconds: 300

ablation_configs:
  - locking: true
    memory: true
    handoffs: true
    parallelization: true
    work_queue: true
  - locking: false
  - memory: false
  - parallelization: false

output_dir: evaluation/reports
```

Load and run:

```python
config = EvalConfig.from_yaml("eval_config.yaml")
```

## Task Tiers

| Tier | Type | Description | Example |
|------|------|-------------|---------|
| 1 | Isolated | Single-file, no coordination needed | Bug fix, refactor |
| 2 | Parallelizable | Multi-file, independent subtasks | Feature + tests + docs |
| 3 | Coordinated | Multi-file, dependent subtasks | Schema migration cascade |

## Adding Tasks

Create a YAML file in the appropriate tier directory:

```yaml
# evaluation/tasks/tier1/my-task.yaml
id: tier1-my-task
tier: 1
source: curated
description: |
  Description of what the agent should do.
difficulty: easy  # easy, medium, hard
affected_files:
  - src/module.py
golden_patch: |
  --- a/src/module.py
  +++ b/src/module.py
  @@ -1,3 +1,3 @@
  -old line
  +new line
test_command: pytest tests/test_module.py -v
tags:
  - bug-fix
estimated_tokens: 500
```

For parallelizable tasks (Tier 2+), add subtasks:

```yaml
subtasks:
  - id: implement
    description: Implement the feature
    affected_files: [src/feature.py]
  - id: test
    description: Write tests
    affected_files: [tests/test_feature.py]
  - id: dependent-task
    description: Depends on implement
    affected_files: [src/integration.py]
    depends_on: [implement]
```

## External Benchmarks

### SWE-bench Verified

```python
from evaluation.adapters import SWEBenchAdapter

adapter = SWEBenchAdapter(registry, seed=42)
tasks = adapter.load_tasks(max_tasks=10)
```

Requires `pip install datasets`.

### Context-Bench

```python
from evaluation.adapters import ContextBenchAdapter

adapter = ContextBenchAdapter(registry)
tasks = adapter.load_tasks(max_tasks=5)
```

### MultiAgentBench/MARBLE

```python
from evaluation.adapters import MARBLEAdapter

adapter = MARBLEAdapter(registry)
tasks = adapter.load_tasks(topology_filter="star")
```

## Ablation Studies

Run with different coordination mechanism configurations:

```python
from evaluation.ablation import generate_ablation_configs, compare_ablations

# Generate 8 key configurations (fractional factorial)
configs = generate_ablation_configs(fractional=True)

eval_config = EvalConfig(
    ablation_configs=configs,
    num_trials=3,
)

# After running, compare results
result = await harness.run()
comparisons = compare_ablations(result.trial_metrics)

for comp in comparisons:
    print(f"{comp.mechanism}: effect={comp.effect_size:.2f} ({comp.interpretation})")
```

## Interpreting Reports

Reports include:

- **Summary table**: Per-task success rates, timing, token usage, cost
- **Ablation comparison**: Effect sizes showing mechanism contributions
- **Per-task breakdown**: Detailed metrics with confidence intervals
- **Consensus evaluation**: Multi-LLM qualitative scores (if enabled)

Effect size interpretation (Cohen's d):
- < 0.2: Negligible
- 0.2-0.5: Small
- 0.5-0.8: Medium
- > 0.8: Large

## Metrics

| Category | Metrics |
|----------|---------|
| Correctness | Task pass rate, test pass rate, patch match ratio |
| Efficiency | Wall-clock time, tokens, API cost, coordination overhead % |
| Parallelization | Speedup factor, Amdahl efficiency, merge conflict rate |
| Coordination | Lock contention rate, memory hit rate, handoff continuity |
| Scaling | Performance vs agent count, overhead growth rate |
