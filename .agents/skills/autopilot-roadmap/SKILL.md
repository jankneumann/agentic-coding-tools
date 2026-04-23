---
name: autopilot-roadmap
description: "Execute roadmap items iteratively with policy-aware vendor routing and learning feedback"
category: Automation
tags: [roadmap, execution, autopilot, multi-vendor]
triggers:
  - "autopilot-roadmap"
  - "autopilot roadmap"
  - "execute roadmap"
---

# Autopilot Roadmap

Execute roadmap items iteratively with policy-aware vendor routing and adaptive reprioritization. Manages the full lifecycle of each roadmap item from planning through completion, writing learning entries and adjusting priorities based on accumulated experience.

## Arguments

`<workspace-path>` - Path to a roadmap workspace directory containing `roadmap.yaml` (produced by `/plan-roadmap`).

Optional flags:
- `--repo-root <path>` - Repository root for schema validation (defaults to auto-detect)
- `--dry-run` - Report what would be executed without making changes

## Prerequisites

- A roadmap workspace with `roadmap.yaml` (from `/plan-roadmap`)
- Shared runtime at `skills/roadmap-runtime/scripts/` (models, checkpoint, learning, context)
- At least one vendor CLI available for `/implement-feature` invocation

## Input

A roadmap workspace path containing:
- `roadmap.yaml` - The roadmap with items, dependencies, policy, and status
- `checkpoint.json` (optional) - Existing execution state for resume
- `learnings/` (optional) - Previously written learning entries

## Steps

### 1. Load or Resume from Checkpoint

```python
from orchestrator import execute_roadmap
result = execute_roadmap(workspace=Path(workspace_path), repo_root=Path(repo_root))
```

If `checkpoint.json` exists, the orchestrator resumes from the saved position, skipping already-completed items. Otherwise, it creates a fresh checkpoint targeting the first ready item.

### 2. Select Next Ready Item

The orchestrator queries `roadmap.ready_items()` to find items whose dependencies are all completed and whose status is `approved`. Items are processed in priority order (lower number = higher priority).

### 3. Execute via /implement-feature

For each ready item, the SKILL.md prompt layer invokes the existing skill workflow. The orchestrator provides a `dispatch_fn` callback interface:

```python
result = execute_roadmap(
    workspace=workspace,
    repo_root=repo_root,
    dispatch_fn=my_dispatch,  # Called for each item needing implementation
)
```

The `dispatch_fn` receives `(item_id, phase, context)` and returns an outcome string. The SKILL.md layer implements this by invoking `/implement-feature`, `/validate-feature`, etc.

### 4. Handle Success

On item completion:
- Write a learning entry via `skills/roadmap-runtime/scripts/learning.py`
- Mark the item completed in the checkpoint
- Run adaptive reprioritization (`replanner.replan()`) to adjust pending items
- Advance to the next ready item

### 5. Handle Failure

On item failure:
- Record the failure in the checkpoint via `CheckpointManager.fail_item()`
- Propagate blocked status to dependent items
- Continue to the next available item (if any)

### 6. Apply Vendor Policy on Limits

When a vendor hits rate limits or budget constraints:
- The policy engine (`policy.py`) evaluates the roadmap's `policy` configuration
- Supports `wait_if_budget_exceeded` (wait for limit reset) and `switch_if_time_saved` (try alternate vendor)
- Cascading failover with `max_switch_attempts_per_item` guard
- All policy decisions are logged with structured events

### 7. Loop Until Complete or Blocked

The orchestrator continues until:
- All items are completed (status: `completed`)
- All remaining items are blocked or failed (status: `blocked_all`)
- No more ready items exist (status: `blocked_all`)

## Output

The `execute_roadmap()` function returns a summary dict:
```python
{
    "completed_count": 3,
    "failed_count": 1,
    "blocked_count": 2,
    "skipped_count": 0,
    "status": "completed" | "blocked_all" | "partial",
    "policy_decisions": [...]
}
```

Workspace artifacts updated:
- `checkpoint.json` - Final execution state
- `roadmap.yaml` - Updated item statuses
- `learnings/<item-id>.md` - Per-item learning entries
- `learning-log.md` - Index of all learning entries

## Shared Runtime

All data model operations use the shared runtime at `skills/roadmap-runtime/scripts/`:
- `models.py` - Roadmap, Checkpoint, LearningEntry dataclasses
- `checkpoint.py` - CheckpointManager for save/restore/advance
- `learning.py` - Learning entry write/read/compact
- `context.py` - Bounded context assembly

## Design Principle: Host-Assisted Only

**Autopilot-roadmap must not make direct LLM API calls.** All reasoning happens in one of two places:

1. **The orchestrating Claude Code agent**, via the `dispatch_fn` callback. `orchestrator.execute_roadmap()` hands `(item_id, phase, context)` tuples to the callback; the agent runs `/implement-feature` / `/validate-feature` / friends in response. The host agent is the LLM runtime; no external API key is required.
2. **Deterministic code** — `replanner.replan()` (regex text matching over learning entries), `policy.evaluate_policy()` (arithmetic/rule-based vendor decisions).

Any future work that needs semantic reasoning must be expressed as either (a) a new callback delegated to the host agent, or (b) a new dispatch phase routed through `/implement-feature`. Reaching for `llm_client.py` or an SDK like `anthropic` / `openai` / `google.generativeai` inside `skills/autopilot-roadmap/scripts/` is out of bounds and enforced by a guard test (`skills/tests/autopilot-roadmap/test_host_assisted_invariant.py`).

The same principle applies to `skills/autopilot/scripts/`. The invariant exists because autopilot is typically invoked from a Claude Code session that already has a paid-for model loaded; routing reasoning through a second external API would double-bill and fragment the session's context.

The one intentional exception elsewhere in the codebase is `skills/parallel-infrastructure/scripts/review_dispatcher.py` (used by `parallel-review-plan` and `parallel-review-implementation`), where vendor diversity is the feature — multi-vendor review requires calling *different* models to get independent findings. That's not host-assistable by construction.

## Next Step

After roadmap execution completes:
```
/cleanup-feature <change-id>
```
