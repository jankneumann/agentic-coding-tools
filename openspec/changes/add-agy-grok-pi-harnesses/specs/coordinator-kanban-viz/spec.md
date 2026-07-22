# coordinator-kanban-viz — delta for add-agy-grok-pi-harnesses

Updates the recognized vendor swimlane roster and the demo seeder's vendor coverage.

## MODIFIED Requirements

### Requirement: Vendor Swimlanes on In-Flight Cards

When an `In Flight` card represents a work-package whose children include multiple agents with distinct vendor values (extracted per design.md D4: canonical source is the `agent_id` suffix after `--`; secondary cross-check is `agent_sessions.agent_type`), the card SHALL render mini-lanes — one per distinct vendor — showing the most recent `audit_log` row for that vendor's agent.

Each mini-lane SHALL display: the vendor name and color, a one-line summary of the latest operation (`audit_log.args_summary` truncated to one line), and a relative timestamp (`<n>s ago`, `<n>m ago`).

The swimlane component SHALL derive the vendor dynamically from the `agent_id` suffix and SHALL NOT hold a hardcoded vendor roster. Adding or retiring a harness SHALL therefore require no change to the component. The roster `claude`, `codex`, `antigravity`, `grok`, `pi` is normative for the seeder and for test fixtures, not for the rendering component.

#### Scenario: Single-vendor card collapses swimlanes

**WHEN** a card represents a work-package with exactly one child agent
**THEN** the card SHALL render a single lane labeled with that agent's vendor
**AND** SHALL NOT render an N-lane structure with a single populated lane

#### Scenario: Vendor-diverse card renders one lane per vendor

**WHEN** a card represents a work-package with three child agents whose vendors are `claude`, `grok`, and `codex`
**THEN** the card SHALL render exactly three mini-lanes
**AND** each lane SHALL display the most recent `audit_log` row for the agent of its vendor
**AND** lanes SHALL be sorted by vendor name in stable lexicographic order

#### Scenario: Historical vendor still renders

**WHEN** a card has a child agent whose `agent_id` suffix is `gemini` from a historical audit row
**THEN** that agent SHALL render in its own lane labelled `gemini`
**AND** the card SHALL NOT crash or omit the agent
**AND** no roster allow-list in the component SHALL be consulted to make this decision

#### Scenario: Lane shows live activity update on SSE event

**WHEN** the client receives an `event: audit` SSE payload for an agent currently rendered on a swimlane
**THEN** the affected lane SHALL update its summary text within 200ms
**AND** other lanes on the same card SHALL NOT re-render

#### Scenario: Completed work-package collapses swimlanes to consensus indicator

**WHEN** a card's underlying work-package transitions to `completed` AND the work-package was vendor-diverse
**THEN** the swimlanes SHALL collapse into a single consensus indicator (`✓` if review consensus is `agree`, `✗` if `conflict`)
**AND** the indicator SHALL source from the existing `parallel-infrastructure` consensus synthesizer's output

### Requirement: Demo Data Seeding for the Kanban Board

The system SHALL provide a seed script that populates the coordinator work queue with a representative set of issues spanning every kanban column and every vendor swimlane, suitable for local development and operator demos.

The seed script SHALL:

- Use stdlib-only HTTP (no extra dependencies on the coordinator side).
- Plant issues tagged with a configurable `change:<change-id>` label so they appear on the board.
- Tag every seeded issue with a stable umbrella label (`seed:active`) and a per-run unique label (`seed:<run-id>`) so prior runs can be wiped without touching real coordinator work.
- Cover every `work_queue.status` value (`pending`, `blocked`, `claimed`, `running`, `completed`, `failed`) at least once.
- Cover every recognized vendor swimlane (`claude`, `codex`, `antigravity`, `grok`, `pi`) plus a no-vendor row.
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
**THEN** the seeded agents SHALL span every recognized vendor (`claude`, `codex`, `antigravity`, `grok`, `pi`)
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
