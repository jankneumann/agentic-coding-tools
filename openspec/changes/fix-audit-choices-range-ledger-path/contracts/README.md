# Contracts — fix-audit-choices-range-ledger-path

No contract sub-types apply. Each was evaluated:

- **OpenAPI**: no endpoints are introduced or modified. This change touches a
  local CLI driver and a path helper.
- **Database**: no schema is introduced or modified.
- **Events**: no events are introduced or modified. The ledger carries the
  six-field event-artifact header, but that header is defined by
  `openspec/schemas/decision-choices.schema.json`, which this change explicitly
  does not touch — only where the file is written changes, not what is in it.
- **Type generation**: nothing to generate from, since none of the above apply.

The one interface that does change is the on-disk **location** of a standalone
range audit's output. That is specified in `specs/skill-workflow/spec.md`
(scenarios 12 through 14) and in `design.md` D1, rather than as a machine-
readable contract, because it is a path convention rather than a payload shape.
