# Unify roadmap dispatch tie-break on list order

> Change ID: `unify-roadmap-dispatch-tie-break`
> Effort: S
> Priority: 1

## Summary

Break priority ties by the item's position in `roadmap.yaml` in every roadmap
dispatch path, replacing the `item_id` tie-break that coordinated batches and the
cross-roadmap resolver use today.

## Problem

Two ready items with the same `priority` dispatch in a different order depending
on execution mode:

| Path | Code | Tie-break |
|---|---|---|
| Sequential readiness | `skills/roadmap-runtime/scripts/readiness.py` | roadmap **list order** (stable sort on priority alone) |
| Coordinated batches | `skills/roadmap-runtime/scripts/dispatch_scheduler.py` | **item_id** |
| Cross-roadmap resolver | `skills/roadmap-runtime/scripts/resolve_readiness.py` | **item_id** |

`refine-roadmap reorder` is the only way to express order among equal
priorities, and today it is honored by sequential dispatch and silently ignored
by coordinated dispatch. On the live `skill-rightsizing` roadmap, moving `ri-08`
before `ri-06` leaves `ri-06` and `ri-07` first in coordinated mode. Found by
Codex review on PR #554; filed as issue #555. #554 shipped a preview warning so
the divergence is at least visible, which this change makes unnecessary.

## Approach

`item_id` is an identifier, not an intended ordering. Roadmap list position is
the operator's expressed order, it is what `reorder` writes, and it is already
what sequential dispatch honors. So all three paths adopt
`(priority, position)` — and `(priority, roadmap_id, position)` across
roadmaps, keeping `roadmap_id` as the cross-workspace separator.

Position becomes an explicit field on `ReadyDispatchItem` rather than an
implicit property of argument order, so a caller that filters or re-sorts ready
items cannot silently change dispatch order.

The alternative — unify on `item_id` — needs a smaller diff but makes
within-tier `reorder` meaningless, so `refine-roadmap` would have to refuse the
operation or rewrite every item's priority to express order. That trades an
inconsistency for a lost capability.

## Impact

- Ordering among equal priorities changes in coordinated dispatch and in the
  cross-roadmap resolver. No item becomes ready or unready, and no batch becomes
  larger or smaller: only the order within a tier changes, and only where
  `item_id` order and list order disagree.
- The readiness result contract is unchanged. Rank stays expressed as array
  order, so `contracts/readiness-result.schema.json` needs no new field.
- `source_fingerprint` changes for every roadmap, and it now moves when items
  are reordered. Its canonical projection sorted items by `item_id`, which made
  list order invisible on purpose; with position deciding ranking, a pure
  reorder became a readiness-relevant input change that the digest has to cover
  under the existing "Deterministic Readiness Projection" requirement. Any
  stored fingerprint will compare stale once, which is what a downstream
  projection is built to handle.
- `refine-roadmap`'s tie-order preview warning is removed; the reorder it warned
  about now takes effect in both modes.

## Acceptance Outcomes

- Sequential readiness, coordinated batch selection, and the cross-roadmap
  resolver order a same-priority pair identically, in roadmap list order, for a
  roadmap whose list order contradicts `item_id` order.
- `select_safe_ready_batch` orders by declared position rather than argument
  order, so a scrambled `ready_items` sequence yields roadmap order.
- A `refine-roadmap reorder` within a priority tier changes coordinated dispatch
  order, and the preview emits no tie-order warning.
