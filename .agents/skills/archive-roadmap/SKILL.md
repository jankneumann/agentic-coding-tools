---
name: archive-roadmap
description: "Archive a completed roadmap workspace to openspec/roadmaps/archive/<date>-<id>/"
category: Maintenance
tags: [roadmap, archive, openspec]
triggers:
  - "archive-roadmap"
  - "archive roadmap"
---

# Archive Roadmap

Move a completed roadmap workspace into the archive directory, mirroring the OpenSpec change-archive convention. Preserves the full workspace contents (`proposal.md`, `roadmap.yaml`, `checkpoint.json`, `learnings/`) under a date-prefixed archive entry.

## Arguments

`<roadmap-id>` - The roadmap identifier, matching the workspace directory name under `openspec/roadmaps/`.

Optional flags:
- `--force` - Archive even if items are not in terminal states (`completed` or `skipped`). Useful for abandoned epics.
- `--archive-root <path>` - Override the default archive directory. Defaults to `<workspace>/../archive`.

## Prerequisites

- A roadmap workspace at `openspec/roadmaps/<roadmap-id>/` containing at least `roadmap.yaml`.
- Shared runtime at `skills/roadmap-runtime/scripts/`.

## Steps

### 1. Resolve workspace and load roadmap

```python
from pathlib import Path
import sys
sys.path.insert(0, "skills/archive-roadmap/scripts")
from archive import archive_roadmap, IncompleteRoadmapError

workspace = Path("openspec/roadmaps") / roadmap_id
```

### 2. Check completion status

The helper inspects every item's `status` field. Terminal statuses are `completed` and `skipped`. Anything else (`failed`, `blocked`, `replan_required`, `in_progress`, `approved`, `candidate`) means the roadmap is incomplete.

If incomplete and `--force` is not set, the helper raises `IncompleteRoadmapError` with a per-status count. Surface that to the user verbatim and prompt them to either:
- Pass `--force` to archive anyway (e.g., abandoned epic).
- Resolve the unfinished items first via `/autopilot-roadmap` or manual edits, then re-run.

### 3. Generate archive target

The destination is `openspec/roadmaps/archive/<YYYY-MM-DD>-<roadmap-id>/`, where the date is today's date in ISO format. This matches the OpenSpec change-archive naming convention (`openspec/changes/archive/<date>-<change-id>/`).

If the target already exists (multiple archives in one day with the same id, or a re-archive after restoration), the helper raises `FileExistsError`. Resolve manually — rename the existing entry or pick a different date.

### 4. Move workspace to archive

The helper creates the archive root if needed, then moves the workspace directory in place. After move:
- `openspec/roadmaps/<roadmap-id>/` — gone.
- `openspec/roadmaps/archive/<date>-<roadmap-id>/` — full workspace contents preserved.

### 5. Display summary

Print a concise summary:

```
## Archive Complete

**Roadmap:** <roadmap-id>
**Archived to:** openspec/roadmaps/archive/<date>-<roadmap-id>/
**Items:** N completed, M skipped (or counts by status if --force was used)
**Forced:** yes/no
```

## Code Pattern

```python
try:
    result = archive_roadmap(workspace, force=force_flag)
except IncompleteRoadmapError as e:
    # Surface counts to user and ask how to proceed
    print(f"Cannot archive: {e}")
    return
except FileExistsError as e:
    # Surface collision to user
    print(f"Archive collision: {e}")
    return

print(f"Archived {result.roadmap_id} to {result.destination}")
```

## Guardrails

- Refuses to overwrite an existing archive entry (collision protection).
- Refuses to archive incomplete roadmaps without `--force` (prevents accidental archival of in-progress work).
- Preserves the entire workspace tree — checkpoint and learnings move with the roadmap so the history is auditable post-archive.
- Never deletes anything. The move operation is reversible by `mv` back to the original location.

## Output Location

```
openspec/roadmaps/
├── <active-roadmap-id>/         # active workspaces
│   ├── proposal.md
│   ├── roadmap.yaml
│   ├── checkpoint.json
│   ├── learnings/
│   └── learning-log.md
└── archive/
    └── <YYYY-MM-DD>-<roadmap-id>/   # archived (this skill's output)
        └── (same layout, frozen)
```

## Related Skills

- `/plan-roadmap` — produces the workspace this skill archives.
- `/autopilot-roadmap` — drives items to terminal states so this skill can archive them cleanly.
- `/openspec-archive-change` — analogous skill for individual OpenSpec changes; this skill is the roadmap-level counterpart.
