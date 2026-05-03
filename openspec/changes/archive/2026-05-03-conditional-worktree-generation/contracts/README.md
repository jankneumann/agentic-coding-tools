# Contracts: Conditional Worktree Generation

**Status**: No machine-readable contracts apply to this change.

This is a skill-internal behavioral change. The evaluation below is documented here (per plan-feature Step 7 requirements) so that reviewers can confirm no contract sub-types were missed.

## Sub-type evaluation

| Sub-type | Applicable? | Reason |
|---|---|---|
| **OpenAPI** | No | No HTTP endpoints added or modified. The optional coordinator extension (Phase 5) augments an existing agent-registration endpoint; that change is owned by the coordinator's own spec and will produce a contract delta there when implemented, not in this change. |
| **Database** | No | No tables, columns, constraints, indexes, or stored procedures added or modified. `.git-worktrees/.registry.json` is a JSON state file, not a database. |
| **Event** | No | No new events published or consumed. The single-line stderr log messages are unstructured operator diagnostics, not a machine-consumed event stream. |
| **Type generation** | No | Nothing to generate — no OpenAPI schemas, no DB models. |

## What plays the role of a contract here

The observable interface between this change and its consumers is the CLI surface of:

1. `skills/worktree/scripts/worktree.py` (subcommands: `setup`, `teardown`, `pin`, `unpin`, `heartbeat`, `gc`, `list`, `status`, `resolve-branch`)
2. `skills/worktree/scripts/merge_worktrees.py`

The stdout contract (key=value lines from `setup` and `resolve-branch --parent`) is consumed by `eval "$(… )"` in SKILL.md files. Backward compatibility for that contract is verified by the regression tests in Phase 2 (task 2.2) and Phase 4 (task 4.1) rather than by schemas under `contracts/`.

The optional `isolation_provided` field on agent registration (Phase 5) is an additive, nullable coordinator extension. When the coordinator's own OpenSpec change formalizes it, that change's `contracts/openapi/*.yaml` will record the schema delta.

## When contracts would apply

A future change that:

- Adds a new HTTP endpoint for querying environment profile remotely
- Introduces a database-persisted record of per-agent isolation state
- Publishes "isolation_resolved" events to a coordinator event bus

would produce files under `contracts/openapi/`, `contracts/db/`, or `contracts/events/` respectively. None of those apply here.
