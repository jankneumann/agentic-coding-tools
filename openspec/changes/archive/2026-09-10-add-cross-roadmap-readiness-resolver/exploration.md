# Exploration: Cross-Roadmap Readiness Resolver

## Roadmap context

- Parent roadmap: `roadmap-supervisor-orchestration`, item `ri-16`.
- Completed dependency: `ri-17` (`add-typed-cross-roadmap-edges-to-the-roadmap-schema`), implemented by commit `39cb6a3e87f591d488f52f0e04563406df21584b`.
- No `ri-17` learning entry exists, so its shipped model/schema/validation code is the dependency evidence.

## Existing behavior

- `skills/autopilot-roadmap/scripts/orchestrator.py` owns the only current `_get_ready_items` definition. It combines roadmap admission status with checkpoint `completed_items` and `failed_items`.
- `skills/roadmap-runtime/scripts/models.py` owns typed `external_depends_on`, tolerant/strict sibling-roadmap loading, and checkpoint loading.
- `skills/supervise/scripts/cycle_state.py` exposes a `ready` command, but its `ready_across_roadmaps` projection reads roadmap status only, is grouped per roadmap, and carries no checkpoint-consistency signal.
- `docs/guides/state-artifacts.md` makes `checkpoint.json` authoritative for execution position and terminal sets. Queue and display state are projections and must not overwrite canonical state.

## Constraints carried into the plan

1. The obsolete roadmap phrase “cross-roadmap `blocked_by` edges” is interpreted as ri-17's typed `external_depends_on` edges.
2. A present, valid checkpoint supplies authoritative completed/failed terminal sets. A missing checkpoint is a valid never-started state and falls back to roadmap definition status.
3. Invalid, identity-mismatched, or internally inconsistent checkpoint state is surfaced and withheld from ready output; it is never repaired from learnings, handoffs, queue rows, mtimes, or wall-clock age.
4. Staleness is content-derived. No `generated_at`, current-time comparison, filesystem mtime, learning, handoff, or queue input may affect output bytes.
5. The globally ranked order is `(priority, roadmap_id, item_id)`.

## Architecture freshness

The required architecture `--ensure` check was attempted with `skills/.venv/bin/python`. It degraded because the repository's configured `src/` and `web/` roots do not exist, and it left committed artifacts untouched. No plan decision below relies on architecture-generated findings.

