## MODIFIED Requirements

### Requirement: Demo Data Seeding for the Kanban Board

The system SHALL provide a seed script that populates the coordinator work queue with a representative set of issues spanning every kanban column and every vendor swimlane, suitable for local development and operator demos.

The seed script SHALL:

- Use stdlib-only HTTP (no extra dependencies on the coordinator side).
- Plant issues tagged with a configurable `change:<change-id>` label so they appear on the board.
- Tag every seeded issue with a stable umbrella label (`seed:active`) and a per-run unique label (`seed:<run-id>`) so prior runs can be wiped without touching real coordinator work.
- Cover every `work_queue.status` value (`pending`, `blocked`, `claimed`, `running`, `completed`, `failed`) at least once.
- Cover every recognized vendor swimlane (`claude`, `codex`, `antigravity`, `grok`, `pi`, `prime`) plus a no-vendor row.
- Support a `--reset` mode that closes every issue tagged `seed:active` via `POST /issues/close`.

The seed script SHALL NOT promise to populate `claimed_by` / `claimed_at` / `completed_at` columns, since those are populated only by `/work/claim` and `/work/complete`, not by `/issues/update`. The script's docstring SHALL document this limitation.

#### Scenario: Seed populates every column

**WHEN** the operator runs `seed_kanban_board.py --api-key <key> --change-id demo-kanban`
**THEN** the coordinator work queue SHALL contain at least one issue in each of: `pending`, `blocked`, `claimed`, `running`, `completed`, `failed` status
**AND** each seeded issue SHALL carry the label `change:demo-kanban`
**AND** each seeded issue SHALL carry both `seed:active` and a per-run `seed:<run-id>` label
**AND** running the kanban-viz frontend against the coordinator SHALL render cards in each of the three columns (Backlog, In Flight, Done)

#### Scenario: Seed covers the full vendor roster

**WHEN** the operator runs `seed_kanban_board.py --api-key <key> --change-id demo-kanban`
**THEN** the seeded agents SHALL span every recognized vendor (`claude`, `codex`, `antigravity`, `grok`, `pi`, `prime`)
**AND** at least one seeded issue SHALL have no vendor
**AND** no seeded agent SHALL carry the retired `gemini` vendor

#### Scenario: --reset wipes prior seeded rows

**WHEN** the operator runs `seed_kanban_board.py --reset` after a prior seed run
**THEN** every issue tagged with `seed:active` SHALL be closed via `POST /issues/close`
**AND** the script SHALL print the count of issues closed
**AND** non-seeded issues (without the `seed:active` label) SHALL remain unaffected

#### Scenario: Idempotent re-seed leaves multiple distinct runs queryable

**WHEN** the operator runs `seed_kanban_board.py` twice in succession without `--reset`
**THEN** the coordinator SHALL contain two distinct sets of seeded issues, each with a different `seed:<run-id>` label
**AND** both sets SHALL share the `seed:active` umbrella label
**AND** a subsequent `--reset` SHALL close both sets together
