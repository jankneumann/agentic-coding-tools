# Tasks

- [x] Make `readiness._get_ready_items` sort on an explicit `(priority, position)` key instead of relying on sort stability.
- [x] Add `position` to `ReadyDispatchItem` and order `select_safe_ready_batch` by `(priority, position)`.
- [x] Pass each item's roadmap index from `autopilot-roadmap/scripts/orchestrator.py`.
- [x] Order the cross-roadmap resolver by `(priority, roadmap_id, position)` without changing its result contract.
- [x] Remove `refine-roadmap`'s tie-order preview warning and its tests.
- [x] Cover the unified order with tests at all three sites, including a roadmap whose list order contradicts `item_id` order.
- [x] Carry list position in the resolver's canonical fingerprint projection so a pure reorder is not invisible to staleness comparison.
