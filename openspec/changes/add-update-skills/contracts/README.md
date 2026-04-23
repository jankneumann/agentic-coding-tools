# Contracts — add-update-skills

No machine-readable contracts apply to this change.

## Sub-types evaluated

- **OpenAPI**: not applicable — change introduces no API endpoints.
- **Database**: not applicable — change introduces no schema changes.
- **Events**: not applicable — change emits no events.
- **Type generation stubs**: not applicable — no schemas to generate from.

## Why no contracts

This change is pure skill-and-script infrastructure operating against the local filesystem and git. The interface is the CLI shape of `sync_agents_md.py` (`--check` flag, exit codes 0/1/2) and `update_skills.py` (no flags in v1), both of which are pinned by spec scenarios in `specs/skill-runtime-sync/spec.md` rather than a separate contract artifact.

Future enhancement: if `/update-skills` grows flags or output formats consumed by other skills (e.g. structured JSON for autopilot integration), add a contract here.
