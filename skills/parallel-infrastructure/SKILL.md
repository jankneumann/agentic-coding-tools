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

### Deterministic review preprocessing

Ported from alibaba/open-code-review (Apache-2.0), a deterministic pass now
runs ahead of every review round — see openspec change
`add-deterministic-review-preprocessing` (design.md D1–D9) for the full
rationale.

- **`file_selection.py`** — five-gate file selection (binary, user_exclude,
  user_include, generated_path, deleted, too_large) applied to the round's
  diff before it is ever rendered into a prompt. Every excluded file gets a
  reason recorded in the packet metadata; nothing is silently dropped.
- **`review_rules.py`** — path-glob rule resolution over a two-layer sidecar
  (embedded default plus an optional repo-root `.review-rules.json`
  project override), grouping selected files by the rule text that applies
  to them so the packet states each rule once per group, not once per file.
  Also carries `coverage_quorum_threshold` (default `0.8`).
- **`review_packet.py`** — `build_review_packet()`/`preview()` run selection
  and rule grouping before rendering (schema `v2`: metadata carries
  `selection` and `rule_groups`), so a preview and a real build can never
  diverge on which files were sent.
- **`line_resolver.py`** — resolves a finding's verbatim `existing_code`
  snippet to a `line_range` against the packet diff (new-side, old-side,
  then whole-file), called from `review_dispatcher._ingest_stdout` right
  after schema validation. A snippet that cannot be matched is kept with
  `line_resolution: "unresolved"`, never dropped.
- **Per-vendor coverage** (`review_dispatcher.py` / `consensus_synthesizer.py`)
  — a vendor may report which selected files it actually reviewed as an
  optional `coverage` block; the dispatcher scores it against the packet's
  selected list and, below `coverage_quorum_threshold`, the synthesizer
  excludes that vendor from a finding's `eligible_vendors` count for files
  it skipped. Absent or full coverage never narrows anything — this can
  only ever tighten what a panel already counted.
- **`fact_check.py`** — a diff-grounded fact-check pass (ported from OCR's
  `REVIEW_FILTER_TASK`) that runs after checkpoint and before consensus
  synthesis, at each vendor's economy model tier. Removes a finding only
  when the diff proves it wrong (the code is absent, or a line contradicts
  the claim); findings on a protected subject (memory safety, concurrency,
  declaration consistency, behavioral/compatibility change, unused
  parameter) are never removed regardless of verdict. Any call failure or
  unparsable response removes nothing. On by default; `converge(fact_check=False)`
  disables it for A/B comparison.
- **`ocr_adapter.py`** — an optional `ocr-local` reviewer vendor (declared
  in `agent-coordinator/agents.yaml`) that shells out to the `ocr` binary
  when present and rewrites its `comments[]` into a review-findings
  payload. Absent from PATH, it is simply Tier 3 (not dispatched) — no
  other vendor's behavior changes.

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
