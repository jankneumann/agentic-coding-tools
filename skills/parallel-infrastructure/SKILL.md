---
name: parallel-infrastructure
description: "Shared parallel execution infrastructure: DAG scheduling, review dispatch, consensus synthesis, scope checking"
category: Infrastructure
tags: [parallel, infrastructure, dag, review, consensus]
user_invocable: false
---

# Parallel Infrastructure

Non-user-invocable infrastructure skill providing shared scripts for parallel execution workflows. Used by `implement-feature`, `autopilot`, `fix-scrub`, `merge-pull-requests`, and other skills that need DAG scheduling, multi-vendor review dispatch, or consensus synthesis.

## Scripts

### `<skill-base-dir>/scripts/dag_scheduler.py`

DAG computation and topological sort for work-packages.yaml.

### `<skill-base-dir>/scripts/scope_checker.py`

Post-execution scope verification — checks that agent changes stayed within declared `write_allow` / `deny` boundaries.

### `<skill-base-dir>/scripts/package_executor.py`

Work package execution protocol for coordinated-tier worker agents.

### `<skill-base-dir>/scripts/review_dispatcher.py`

Multi-vendor review dispatch — sends review prompts to configured vendor CLIs and collects findings.

Every `review`-mode dispatch wraps caller-supplied review context with a strict output contract generated from the skill-owned `review-findings.schema.json`. Callers provide only the target-specific context and focus; they do not hand-author JSON examples or required-field lists.

Vendor stdout is saved as `raw-<vendor>-<review-type>.txt`. Parsed findings are atomically persisted before canonical-schema validation. Invalid files remain on disk for recovery, while the dispatch is marked failed and excluded from quorum.

### `<skill-base-dir>/scripts/review_prompt.py`

Standalone schema-derived prompt generator. Use this instead of hand-writing a review output contract:

```bash
python3 "<skill-base-dir>/scripts/review_prompt.py" \
  --review-type plan \
  --target "$CHANGE_ID" \
  --context "Review the OpenSpec plan artifacts under openspec/changes/$CHANGE_ID/." \
  --focus "Specification completeness, contract consistency, architecture, and security." \
  --output "openspec/changes/$CHANGE_ID/reviews/review-prompt.md"
```

### `<skill-base-dir>/scripts/consensus_synthesizer.py`

Synthesizes review findings from multiple vendors into a consensus report with confirmed/unconfirmed/disagreement classifications.

### `<skill-base-dir>/scripts/integration_orchestrator.py`

Cross-package integration management — tracks package completion, consensus recording, and integration gating.

### `<skill-base-dir>/scripts/result_validator.py`

Validates work-queue results against `work-queue-result.schema.json`.

### `<skill-base-dir>/scripts/circuit_breaker.py`

Fault tolerance for external service calls with configurable thresholds.

### `<skill-base-dir>/scripts/escalation_handler.py`

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
