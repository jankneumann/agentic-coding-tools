# Deferred Tasks — add-per-phase-archetype-resolution

Tasks moved out of the implementation scope and deferred to a follow-up
proposal. Each entry records *why* the deferral was made so a future
proposal can pick it up.

## D-1: Expose `phase_archetype` in `GET /discovery/agents` listing

**Origin**: tasks.md 4.3, 4.4 (the `GET /status/agents` listing portion).
**Spec**: `specs/agent-coordinator/spec.md` — Status Report Payload Phase
Archetype Field, scenario "subsequent calls to GET /status/agents SHALL return
phase_archetype: 'architect' for that agent".

**What this implementation does**: `POST /status/report` accepts and forwards
the optional `phase_archetype` field through the coordinator event bus
(`coordinator_status` channel, in the event `context` dict). Subscribers
that consume the event stream (notification daemons, observability dashboards
listening on the channel) see the `phase_archetype` value alongside `phase`.

**What this implementation does NOT do**: Persist `phase_archetype` on the
`AgentInfo` discovery record so that `GET /discovery/agents` returns it as
part of each agent's current-phase summary.

**Why deferred**:
1. The persistence path requires extending the `discovery` service
   (`agent-coordinator/src/discovery.py`) and likely the
   `database/migrations/*.sql` files to add a `phase_archetype` column on
   the agent-status table. Both are **outside the wp-coordinator scope**
   declared in `work-packages.yaml` (`write_allow` covers `agents_config.py`,
   `coordination_api.py`, `archetypes.yaml`, and `tests/`).
2. Forcing the discovery extension into wp-coordinator would require also
   amending the work-package's `write_allow` and re-running plan validation,
   and would add migration coordination concerns to a change that was
   designed to be additive.
3. Operationally, autopilot's primary consumers of the value (the runner
   that emits status reports, downstream notification subscribers) get
   the value via the event bus today. The dashboard/listing exposure is a
   nice-to-have for retrospective queries.

**Pickup criteria** (for the follow-up):
- Extend `AgentInfo` dataclass with `phase_archetype: str \| None = None`.
- Add a database migration adding `phase_archetype TEXT` to the agent-status
  table.
- Extend `DiscoveryService.heartbeat` (or add a new `update_phase_archetype`
  method) so `POST /status/report` can persist the value.
- Extend `GET /discovery/agents` to surface `phase_archetype` in the response
  dict.
- Update the corresponding test in
  `agent-coordinator/tests/test_phase_archetype_resolution.py` to assert
  `GET /discovery/agents` round-trips the value.
