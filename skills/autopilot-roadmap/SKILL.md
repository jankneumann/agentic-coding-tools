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
- Shared runtime at `<skill-base-dir>/../roadmap-runtime/scripts/` (models, checkpoint, learning, context)
- At least one vendor CLI available for `/implement-feature` invocation

## Local CLI Mutation Boundary

`autopilot-roadmap` writes checkpoint, roadmap status, learning entries, and may
invoke implementation/validation skills for roadmap items. In local CLI
execution, every mutating run MUST start from a managed worktree unless
`--dry-run` is set.

Before loading or updating the roadmap workspace, run:

```bash
CHANGE_ID="roadmap-<workspace-name>"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID")"
cd "$WORKTREE_PATH"
python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation
```

`--dry-run` remains read-only and may run from the shared checkout.

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

**Refine the item's plan before implementing it.** `/plan-roadmap` already scaffolded every item into `openspec/changes/<change-id>/` with a proposal, tasks, and a spec delta sketched from its acceptance outcomes. That sketch validates, but its `WHEN` clauses are generic — the roadmap could not know each item's trigger at decomposition time.

So the first dispatch for a ready item is refinement, not implementation: run `/plan-feature` (and `/iterate-on-plan` where the item warrants it) against the existing change, seeded with what the item's completed dependencies taught. This is where the roadmap's central advantage is realised — an item planned after its dependencies land is planned against reality rather than against a forecast. Then dispatch `/implement-feature`.

**Pass the item's `change_id` explicitly — never let the planner choose its own slug.** `roadmap.yaml` records a `change_id` per item, and resume detection, dependency tracking and the learning log all key off it. If `/plan-feature` derives a different slug, it creates a second directory alongside the scaffolded one and the roadmap cannot find the work.

Roadmaps generated before `change_id` was persisted may omit it. In that case call `populate_change_ids(roadmap)` from `<skill-base-dir>/../plan-roadmap/scripts/scaffolder.py` on load and save the roadmap back, so the ids are fixed once rather than re-derived differently by each consumer.

For each ready item, the SKILL.md prompt layer invokes the existing skill workflow. The orchestrator provides a `dispatch_fn` callback interface:

```python
result = execute_roadmap(
    workspace=workspace,
    repo_root=repo_root,
    dispatch_fn=my_dispatch,  # Called for each item needing implementation
)
```

The `dispatch_fn` receives `(item_id, phase, context)` and returns an outcome string. The SKILL.md layer implements this by invoking `/implement-feature`, `/validate-feature`, etc.

#### Opt-in delegated lifecycle

Supervised execution uses the additive two-stage API; ordinary `execute_roadmap()` callers retain the four historical phases exactly. `prepare_delegated_batch(workspace, repo_root=..., isolation_resolver=..., context=...)` selects the deterministic scope-safe ready batch, resolves each item's isolation envelope, and persists every `prepared` generation before returning any request. It never invokes `dispatch_fn`. Invalid exact change IDs are returned as non-dispatched failures without failing the roadmap item.

The host owns child launch and the acknowledgement/go protocol. After it has advanced the persisted attempts to `launched` and collected schema-valid results, it calls `apply_delegated_batch(workspace, batch_id, results, dispatch_fn, repo_root=...)`. Apply rejects incomplete, duplicate, stale, or mismatched result sets before invoking the callback. Each unresolved generation is then presented exactly once as `dispatch_fn(item_id, "autopilot", context)`, where `context["dispatch_result"]` is the exact correlated result and the remaining context preserves router-owned keys plus dispatch, scope, and isolation identity. Success reuses the existing checkpoint and learning seam; a gate or policy `parked` result remains nonterminal and does not unblock dependents.

### 4. Handle Success

On item completion:
- Write a learning entry via `<skill-base-dir>/../roadmap-runtime/scripts/learning.py`
- Mark the item completed in the checkpoint
- Run adaptive reprioritization (`replanner.replan()`) to adjust pending items
- Advance to the next ready item

### 5. Handle Failure

On item failure:
- Record the failure in the checkpoint via `CheckpointManager.fail_item()`
- Propagate blocked status to dependent items
- Continue to the next available item (if any)
- If the dispatch result carried `{"replan": true}`, dependents are parked in
  `replan_required` instead and the replan gate runs — see
  "Re-decomposition on `replan_required`" below

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
    "superseded_count": 0,
    "replan_required_count": 0,
    "status": "completed" | "blocked_all" | "partial" | "replan_requested",
    "policy_decisions": [...],
    "gate_decisions": [...],
    # present only when status == "replan_requested"
    "replan_request": {"path": ..., "failed_item_id": ..., "replan_required_items": [...]},
}
```

Workspace artifacts updated:
- `checkpoint.json` - Final execution state (including `gate_decisions`)
- `roadmap.yaml` - Updated item statuses
- `learnings/<item-id>.md` - Per-item learning entries
- `learning-log.md` - Index of all learning entries
- `replan-request.json` - Written only when the replan gate proceeds; consumed and
  deleted by `/plan-roadmap --replan`

## Shared Runtime

All data model operations use the shared runtime at `<skill-base-dir>/../roadmap-runtime/scripts/`:
- `models.py` - Roadmap, Checkpoint, LearningEntry dataclasses
- `checkpoint.py` - CheckpointManager for save/restore/advance
- `learning.py` - Learning entry write/read/compact
- `context.py` - Bounded context assembly

## Design Principle: Host-Assisted Only

**Autopilot-roadmap must not make direct LLM API calls.** All reasoning happens in one of two places:

1. **The orchestrating Claude Code agent**, via the `dispatch_fn` callback. `orchestrator.execute_roadmap()` hands `(item_id, phase, context)` tuples to the callback; the agent runs `/implement-feature` / `/validate-feature` / friends in response. The host agent is the LLM runtime; no external API key is required.
2. **Deterministic code** — `replanner.replan()` (regex text matching over learning entries), `policy.evaluate_policy()` (arithmetic/rule-based vendor decisions).

Any future work that needs semantic reasoning must be expressed as either (a) a new callback delegated to the host agent, or (b) a new dispatch phase routed through `/implement-feature`. Reaching for `llm_client.py` or an SDK like `anthropic` / `openai` / `google.generativeai` inside `<skill-base-dir>/scripts/` is out of bounds and enforced by the **source-contribution-only** test `skills/tests/autopilot-roadmap/test_host_assisted_invariant.py`.

The same principle applies to `<skill-base-dir>/../autopilot/scripts/`. The invariant exists because autopilot is typically invoked from a Claude Code session that already has a paid-for model loaded; routing reasoning through a second external API would double-bill and fragment the session's context.

The one intentional exception elsewhere in the installed payload is `<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py` (used by `parallel-review-plan` and `parallel-review-implementation`), where vendor diversity is the feature — multi-vendor review requires calling *different* models to get independent findings. That's not host-assistable by construction.

## Re-decomposition on `replan_required`

An item whose failure the executing agent judges workaround-able returns
`{"outcome": "failed:<reason>", "replan": true}` from `dispatch_fn` instead of the
bare `"failed:<reason>"` string. That explicit signal — not a classifier — is what
makes the failure a re-planning event; the agent that saw the failure is the one that
knows. A vendor-policy `fail_closed` or an unrecognised outcome never carries it.

What the orchestrator does with it:

1. `CheckpointManager.fail_item(..., replan=True)` parks the failed item's
   `approved` / `candidate` dependents in `replan_required` (rather than `blocked`),
   with `blocked_by` set. Completed dependents are untouched.
2. The `replan_required` gate is evaluated **once per failure**, not once per parked
   dependent — one failure is one question. The disposition comes from
   `TRUST_POSTURE.md`; the decision is appended to `checkpoint.gate_decisions`. If
   nothing was parked (the failed item had no dependents) there is no subgraph to
   re-decompose, so the gate is not evaluated at all.
3. **BLOCKED** → nothing is written. The parked items stay in `replan_required`, so
   they are not ready and will not be dispatched, and the run continues with whatever
   else is ready. Fail closed.
4. **PROCEED** → the orchestrator writes `<workspace>/replan-request.json`
   (`contracts/events/replan-request.schema.json`: `roadmap_id`, `failed_item_id`,
   `failure_reason`, `replan_required_items`, the `gate_decision`, and the failed
   item's `learning_entry` path), saves `roadmap.yaml`, and **stops the run** with
   summary `status: "replan_requested"` plus a `replan_request` block naming the
   file. Dispatching anything else first would build on a plan just declared stale.

**The orchestrator never performs the replan itself.** Re-decomposition is semantic
work, so it belongs to the host under the host-assisted invariant above. On seeing
`replan_requested`, the host runs:

```
/plan-roadmap --replan <roadmap-id>
```

which reads the request file, re-decomposes only the affected subgraph, approves the
result, and deletes the request. See `plan-roadmap/SKILL.md` § "Replan Mode". The
file is the handoff medium — no network call leaves this package.

`replanner.replan()` is unrelated and unchanged: it nudges priorities of existing
items after a *success*, and never re-reads the source proposal.

## Next Step

After roadmap execution completes:
```
/cleanup-feature <change-id>
```
