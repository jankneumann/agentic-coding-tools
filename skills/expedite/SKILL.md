---
name: expedite
description: Readiness gate for sync-point operations — inspect validation, rework, and active-agent state before merge
category: Workflow
tags: [validation, gate, expediter, sync-point]
triggers:
  - "expedite"
  - "ready to merge"
  - "is this ready"
  - "expediter"
requires:
  coordinator:
    required: []
    safety: []
    enriching: []
---

# Expedite

Inspect a change for readiness before sync-point operations (`/cleanup-feature`, `/merge-pull-requests`). Produces a binary verdict — `READY` or `BLOCKED` — with a structured list of checks.

The expediter is a **read-only** role. It does not merge, mutate state, or run commands that change the worktree, the registry, or the remote. Its only job is to refuse outgoing work that is not ready, the way an expediter at the kitchen pass refuses a plate that is not right.

This is the kitchen-brigade role implementation called out in [`docs/mental-models.md`](../../docs/mental-models.md) gap G2 — a first-class expediter to replace the implicit role currently scattered across `/cleanup-feature` and `/merge-pull-requests`.

## Arguments

`$ARGUMENTS` — OpenSpec change-id (required).

Optional flags:
- `--validation-report <path>` — explicit path to `validation-report.md` (default: probe candidate paths)
- `--rework-report <path>` — explicit path to `rework-report.json` (default: probe candidate paths)
- `--json` — emit machine-readable JSON instead of human text
- `--repo-root <path>` — repo root (default: current working directory)

## Steps

### 1. Run the expediter

```bash
python skills/expedite/scripts/expedite.py <change-id>
```

The script:
- Calls `skills/shared/active_agents.py:check_no_active_agents` to verify exclusive access.
- Probes for `validation-report.md` at `openspec/changes/<change-id>/validation-report.md`, then `.../reports/validation-report.md`, then `.git-worktrees/<change-id>/validation-report.md`. If found, runs `gate_logic.pre_merge_gate` against it (smoke / security / e2e hard gates).
- Probes for `rework-report.json` at the same three locations. If found, loads it via `rework_report.load_rework_report` and inspects `summary_action`.
- Returns exit `0` (READY) or `1` (BLOCKED).

### 2. Interpret the verdict

**READY** → it is safe to invoke `/cleanup-feature` or `/merge-pull-requests` for this change.

**BLOCKED** → stop. Each failing check has a `detail` and an `action`. Common blockers and their resolutions:

| Check fail | Resolution |
|---|---|
| `active_agents` | Wait for the listed agents to finish, or pass `--force` to override after operator confirmation. |
| `validation_report` (no file) | Run `/validate-feature` first. |
| `validation_report` (hard gate fail) | Investigate the failing phase; re-run `/validate-feature`; if accepted, pass `--force`. |
| `rework_report` (`block-cleanup`) | Holdout failure — iterate on the failures and re-validate; do not merge. |
| `rework_report` (`iterate`) | Run `/iterate-on-implementation`, then re-validate. |

A `skip` status (e.g., no `rework-report.json`) does not block. Some changes legitimately have no rework report.

### 3. Optional: machine-readable mode

```bash
python skills/expedite/scripts/expedite.py <change-id> --json > /tmp/verdict.json
```

The JSON shape is:
```json
{
  "change_id": "...",
  "ready": true|false,
  "checks": [
    {"name": "...", "status": "pass|fail|skip", "detail": "...", "action": "..."}
  ]
}
```

## What the expediter does NOT do

- Does **not** merge, push, or close PRs. That is `/merge-pull-requests`.
- Does **not** teardown worktrees. That is part of `/cleanup-feature`.
- Does **not** update specs. That is `/update-specs`.
- Does **not** re-run validation. That is `/validate-feature`.
- Does **not** auto-fix anything. It is a refusal gate, not a remediation step.

## Workflow Context

```
/implement-feature → /validate-feature → /expedite → /cleanup-feature
                                          (gate)      (sync-point)
```

`/cleanup-feature` and `/merge-pull-requests` already have their own active-agent guard via `skills/shared/active_agents.py`. The expediter is complementary — it adds the validation-report and rework-report checks that those skills do not currently inspect.

## See Also

- [`skills/shared/active_agents.py`](../shared/active_agents.py) — the active-agent guard
- [`skills/validate-feature/scripts/gate_logic.py`](../validate-feature/scripts/gate_logic.py) — `pre_merge_gate`, `REQUIRED_PHASES`
- [`skills/validate-feature/scripts/rework_report.py`](../validate-feature/scripts/rework_report.py) — `ReworkReport`, `load_rework_report`
- [`docs/mental-models.md`](../../docs/mental-models.md) gap G2 — the rationale
