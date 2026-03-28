---
name: parallel-infrastructure
description: "Shared parallel execution infrastructure: DAG scheduling, review dispatch, consensus synthesis, scope checking"
category: Infrastructure
tags: [parallel, infrastructure, dag, review, consensus]
user_invocable: false
---

# Parallel Infrastructure

Non-user-invocable infrastructure skill providing shared scripts for parallel execution workflows. Used by `implement-feature`, `auto-dev-loop`, `fix-scrub`, `merge-pull-requests`, and other skills that need DAG scheduling, multi-vendor review dispatch, or consensus synthesis.

## Scripts

### scripts/dag_scheduler.py

DAG computation and topological sort for work-packages.yaml.

### scripts/scope_checker.py

Post-execution scope verification — checks that agent changes stayed within declared `write_allow` / `deny` boundaries.

### scripts/package_executor.py

Work package execution protocol for coordinated-tier worker agents.

### scripts/review_dispatcher.py

Multi-vendor review dispatch — sends review prompts to configured vendor CLIs and collects findings.

### scripts/consensus_synthesizer.py

Synthesizes review findings from multiple vendors into a consensus report with confirmed/unconfirmed/disagreement classifications.

### scripts/integration_orchestrator.py

Cross-package integration management — tracks package completion, consensus recording, and integration gating.

### scripts/result_validator.py

Validates work-queue results against `work-queue-result.schema.json`.

### scripts/circuit_breaker.py

Fault tolerance for external service calls with configurable thresholds.

### scripts/escalation_handler.py

Escalation protocol for scope violations, resource conflicts, and review disagreements.

## Usage

Other skills reference these scripts via relative path:

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py" [args]
```

Or import programmatically:

```python
import sys, os
scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "parallel-infrastructure", "scripts")
sys.path.insert(0, scripts_dir)
from review_dispatcher import ReviewOrchestrator
from consensus_synthesizer import ConsensusSynthesizer
```
