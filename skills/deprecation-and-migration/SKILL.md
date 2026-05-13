---
name: deprecation-and-migration
description: |
  Manage the lifecycle of removing systems, APIs, features, and dependencies. Use when sunsetting
  a capability, replacing one implementation with another, consolidating duplicates, killing
  zombie code, or planning the eventual deprecation of something new at design time. Covers the
  Churn Rule (owners fund migration cost), the strangler / adapter / feature-flag patterns, the
  five-question decision matrix, advisory-vs-compulsory deprecation, and how to drive it through
  an OpenSpec change.
category: Lifecycle
tags:
  - deprecation
  - migration
  - lifecycle
  - refactoring
  - tech-debt
  - openspec
  - strangler
  - adapter
  - feature-flags
  - zombie-code
triggers:
  - "deprecate"
  - "deprecation"
  - "migrate users"
  - "migrate consumers"
  - "sunset feature"
  - "remove old api"
  - "kill switch"
  - "strangler pattern"
  - "feature flag migration"
  - "zombie code"
  - "is this still used"
user_invocable: true
related:
  - update-specs
  - cleanup-feature
---

# Deprecation and Migration

Adapted from [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills) under its upstream license; localized to this repo's OpenSpec workflow and Python defaults.

## Overview

Code is a liability, not an asset. Every line has ongoing cost — bugs, dependency upgrades, security patches, mental overhead, onboarding tax. Deprecation is the discipline of removing code that no longer earns its keep; migration is the process of moving users safely from the old surface to the new one.

Most teams are good at adding things. Few are good at removing them. This skill closes that gap and ties the discipline to OpenSpec changes so deprecations ship with the same rigor as new features.

## When to Use

- Replacing an old system, API, library, or model with a new one
- Sunsetting a feature or experiment that is no longer needed
- Consolidating duplicate implementations (two libraries, two endpoints, two pipelines)
- Removing dead code that nobody owns but several teams import
- Designing a *new* capability — plan its eventual deprecation now, while you have the freedom
- Deciding whether to maintain a legacy system or invest in migration

## Core Principles

### Code Is a Liability

The value of code is the functionality it provides, not the code itself. When the same functionality can be delivered with less code, fewer dependencies, or sharper abstractions, the old code should go.

### Hyrum's Law Makes Removal Hard

> With enough users of an API, every observable behavior — including bugs, timing quirks, and undocumented side effects — becomes depended upon.

This is why deprecation requires *active migration*, not just announcement. Consumers can't "just switch" when they depend on behavior the replacement does not replicate.

### Deprecation Planning Starts at Design Time

When building something new, ask: *"How would I remove this in three years?"* Systems designed with clean interfaces, feature flags, and minimal surface area are easy to deprecate. Systems that leak implementation details everywhere become permanent.

### The Churn Rule

> If you own the infrastructure being deprecated, you fund the migration cost.

You either migrate consumers yourself, or you ship a backward-compatible adapter so consumers don't have to act. You do not announce a deadline and walk away. The owner's budget pays for the churn.

## The Deprecation Decision (5-Question Matrix)

Run every deprecation candidate through this matrix before writing a line of code:

| # | Question | If "yes" / high | If "no" / low |
|---|----------|-----------------|---------------|
| 1 | **Value** — Does it still provide unique value users would miss? | Maintain it. Stop here. | Continue to Q2. |
| 2 | **Consumers** — How many users / call sites / dependents are there? | Quantify scope before promising a date. | Removal is cheap; just do it. |
| 3 | **Replacement** — Does a production-proven replacement exist? | Continue to Q4. | Build the replacement first. Do not deprecate without an alternative. |
| 4 | **Migration cost** — What is the per-consumer cost to switch? | If automatable, automate; if manual + high, weigh against Q5. | Migrate now; trivial cases lose to inertia if delayed. |
| 5 | **Maintenance cost of NOT deprecating** — Security, ops, opportunity cost, complexity tax. | Justifies forcing migration (advisory → compulsory). | Stay advisory; let consumers move on their own timeline. |

Document the answers in the OpenSpec proposal (see *Deprecating in OpenSpec* below). A reviewer should be able to check the math without re-doing the analysis.

## Advisory vs Compulsory Deprecation

| Type | When to use | Mechanism | Owner obligation |
|------|-------------|-----------|------------------|
| **Advisory** | Old system is stable; migration is optional; cost of carrying both is bounded. | Warnings, docs, deprecation banners, type-level `@deprecated`. Users migrate on their own timeline. | Provide a guide; respond to migration questions. |
| **Compulsory** | Security risk, blocks platform progress, or maintenance cost is unsustainable. | Hard removal date. Migration tooling. Active consumer outreach. | Migrate the long tail yourself; do not just announce a deadline. |

**Default to advisory.** Compulsory mode requires a budget for tooling, docs, and hand-holding — the Churn Rule applies in full.

## The Migration Process

### Step 1 — Build the Replacement

Do not deprecate without a working alternative. The replacement must:

- Cover all critical use cases of the old system (write the matrix down).
- Have a migration guide *before* announcement, not after.
- Be proven in production traffic, not just "theoretically better".

### Step 2 — Announce and Document

```markdown
## Deprecation Notice: OldService

**Status:** Deprecated as of 2025-03-01
**Replacement:** NewService (see migration guide below)
**Removal date:** Advisory — no hard deadline yet
**Reason:** OldService requires manual scaling and lacks observability.
            NewService handles both automatically.

### Migration Guide
1. Replace `from old_service import client` with `from new_service import client`
2. Update configuration (see examples)
3. Run the verification script: `python -m new_service.migrate_check`
```

### Step 3 — Migrate Incrementally

Move consumers one at a time. For each:

1. Identify every touchpoint with the deprecated system (grep, dependency graph, call traces).
2. Switch to the replacement.
3. Verify behavior matches (golden tests, shadow traffic, integration checks).
4. Delete the old references.
5. Confirm no regressions before moving to the next consumer.

### Step 4 — Remove the Old System

Only after every consumer is migrated:

1. Verify zero active usage via metrics, logs, and dependency analysis (don't trust grep alone).
2. Remove the code.
3. Remove the tests, fixtures, docs, and configuration that supported it.
4. Remove the deprecation notices — they have served their purpose.
5. Land an OpenSpec `## REMOVED Requirements` delta so the spec stops promising the capability.

## Migration Patterns

### Strangler Pattern

Run old and new side by side. Route traffic incrementally. When the old path serves 0%, delete it.

```
Phase 1: New = 0%,  Old = 100% (replacement deployed but dark)
Phase 2: New = 10%, Old = 90%  (canary)
Phase 3: New = 50%, Old = 50%  (verify parity at scale)
Phase 4: New = 100%, Old = 0%  (idle but reversible)
Phase 5: Remove old (irreversible — only after a soak period)
```

### Adapter Pattern

Expose the old interface; forward to the new implementation. Consumers keep their code; you swap the engine.

**TypeScript (preserved from upstream):**

```typescript
// Adapter: old interface, new implementation
class LegacyTaskService implements OldTaskAPI {
  constructor(private newService: NewTaskService) {}

  // Old method signature, delegates to new implementation
  getTask(id: number): OldTask {
    const task = this.newService.findById(String(id));
    return this.toOldFormat(task);
  }
}
```

**Python equivalent — wrapping a deprecated `requests`-based client behind a new `httpx`-based interface during the strangler period:**

```python
# adapters/task_client_legacy.py
from __future__ import annotations

import warnings
from typing import Any

import httpx  # new transport

from new_task_client import NewTaskClient  # the replacement


class LegacyTaskClient:
    """Drop-in adapter that exposes the old `requests`-style surface
    but routes calls through the new httpx-based client.

    Lets existing call sites keep working unchanged while we migrate them
    one at a time. Delete this module once `git grep LegacyTaskClient` is empty.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        warnings.warn(
            "LegacyTaskClient is deprecated; import NewTaskClient from new_task_client. "
            "See docs/decisions/<capability>.md for migration guide.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._inner = NewTaskClient(
            transport=httpx.HTTPTransport(retries=2),
            base_url=base_url,
            timeout=timeout,
        )

    # Old signature: returned a dict. New client returns a Task model.
    def get_task(self, task_id: int) -> dict[str, Any]:
        task = self._inner.get(str(task_id))
        return {
            "id": int(task.id),
            "title": task.title,
            "done": task.status == "completed",
        }
```

The adapter buys you time without freezing consumers. It is itself a deprecation artifact: schedule its removal in the same proposal that introduces it.

### Feature Flag Migration

Switch consumers cohort-by-cohort using a runtime flag. Decouples *deploying* the new code from *exposing* it.

```python
# routing.py
from feature_flags import flags
from legacy_task_service import LegacyTaskService
from new_task_service import NewTaskService


def get_task_service(user_id: str):
    if flags.is_enabled("new-task-service", user_id=user_id):
        return NewTaskService()
    return LegacyTaskService()
```

Use feature flags when consumers are end users (not internal callers), or when you need an instant rollback path.

## Zombie Code (5 Indicators)

Zombie code is code that nobody owns but everybody depends on. It is not actively maintained, accumulates security debt, and silently constrains everything around it. Look for these five signals:

1. **No commits in 6+ months**, yet active consumers exist.
2. **No assigned maintainer or team** (CODEOWNERS empty, no Slack channel, no on-call).
3. **Failing or quarantined tests** that nobody fixes.
4. **Dependencies with known vulnerabilities** that nobody upgrades.
5. **Documentation references systems that no longer exist** — README points to a wiki that 404s, ADRs cite retired services.

**Response:** Either assign an owner and fund maintenance, or deprecate it with a concrete migration plan. Zombies cannot stay in limbo — they get investment or removal.

## Deprecating in OpenSpec

In this repo, deprecations ship as OpenSpec changes — the same proposal → review → implement → cleanup loop as new features. The spec deltas express intent precisely:

- **`## REMOVED Requirements`** delta in `spec.md` — use when the capability is going away entirely. Lists the requirements being deleted along with a one-line reason. After the change archives, the requirement disappears from the active spec.
- **`## MODIFIED Requirements`** delta in `spec.md` — use for *Advisory* deprecation. Mark the requirement as deprecated, link to the replacement, and document the migration guide inline. The capability still exists; the spec just signals "do not build new dependencies on this".
- **`## ADDED Requirements`** delta — for the *replacement* surface, written in the same change so reviewers see the trade together.
- **Proposal `proposal.md`** — record the answers to the 5-question matrix and pick advisory vs compulsory. Future archaeologists thank you.

Workflow:

1. `/plan-feature "deprecate <capability>"` — produces the proposal with the matrix answers and the spec deltas.
2. `/implement-feature <change-id>` — lands the adapter / strangler scaffolding, the `DeprecationWarning`, and the migration tooling. Consumers may migrate now or later (advisory) or before the deadline (compulsory).
3. After all consumers migrate, open a follow-up change that promotes the `MODIFIED` deprecation to `REMOVED` and deletes the code.
4. **`/update-specs`** keeps `openspec/specs/` in sync with reality after the deprecation lands — invoke it from the cleanup phase so the canonical spec no longer promises the deprecated surface.
5. **`/cleanup-feature`** orchestrates the merge, archives the proposal, and prunes branches. It is the standard exit door for both halves of the deprecation (the "mark deprecated" change and the "remove" change).

If you find yourself wanting to remove code without an OpenSpec change, stop — that is exactly the silent-removal pattern that breaks Hyrum's Law consumers. Run the change.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "It still works — why remove it?" | Working code that nobody maintains accumulates security debt and complexity. The cost grows silently and shows up as an incident, not a line item. |
| "Someone might need it later." | If it's needed later, rebuild it from a clean spec. Keeping unused code "just in case" costs more over a year than rebuilding from scratch. |
| "Migration is too expensive." | Compare migration cost to ongoing maintenance over 2–3 years, not a single sprint. The carrying cost almost always wins. |
| "We'll deprecate after the new system ships." | Deprecation planning starts at design time. By the time the new system ships, you have new priorities and the old one is permanent. |
| "Users will migrate on their own." | They won't. The Churn Rule says you fund the migration — provide tooling, codemods, or do it yourself. |
| "We can maintain both indefinitely." | Two systems doing the same job is double the tests, docs, on-call, and onboarding cost — forever. |
| "The OpenSpec change is overkill for a deletion." | Deletions are the riskiest operations in the codebase; the proposal is the audit trail that lets reviewers catch a Hyrum's Law trap. |

## Red Flags

- Deprecation announced with no replacement in production.
- Deprecation announced with no migration guide or codemod.
- "Soft" deprecation that has been advisory for 12+ months with no measurable progress.
- Zombie code with no `CODEOWNERS` entry and active import sites.
- New features being added to a system that is officially deprecated.
- Deprecation decision made without measuring current usage (no metrics, no log query).
- Code removal landed without verifying zero callers (grep-only, no telemetry).
- No OpenSpec change accompanies a removal — the spec still promises the capability that vanished.
- The 5-question matrix was skipped or only one question was actually answered.
- The Churn Rule is violated: owner says "consumers should just migrate" with no tooling provided.

## Verification

1. The OpenSpec proposal records explicit answers to all 5 matrix questions and an advisory-vs-compulsory call.
2. A migration guide exists at a stable URL (proposal `proposal.md` or `docs/decisions/<capability>.md`) before any deprecation warning ships.
3. Telemetry / logs / dependency analysis confirm zero active callers before any code is deleted (grep alone is insufficient).
4. The replacement is exercised in production for a soak period proportional to risk before the old system is removed.
5. `spec.md` carries the correct delta: `MODIFIED` (advisory) or `REMOVED` (final removal); `/update-specs` was run during cleanup.
6. Adapters and feature flags introduced for the migration have a scheduled removal date in a follow-up OpenSpec change — not "we'll clean it up later".
7. After removal, deprecation banners, warnings, and dead tests are gone — the codebase is *smaller*, not just rearranged.
