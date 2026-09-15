# Contracts — add-skill-audit

The four contract sub-types were evaluated:

| Sub-type | Applies? | Why |
|---|---|---|
| OpenAPI | Partially | `POST /archetypes/resolve_for_phase` gains one optional response field `procedure_mode`. The change is additive and documented in `specs/agent-archetypes/spec.md` "Procedure Mode Prompt Injection"; the existing endpoint contract in the `agent-archetypes` spec ("Phase Archetype Resolution Endpoint Contract") is the authority, so no separate OpenAPI file is introduced. |
| Database | No | No schema, migration, or query changes. Memory is read through the existing `/memory/query` endpoint; `agent_sessions.phase_archetype` is read through `GET /discovery/agents`. |
| Events | No | No events are emitted or consumed. |
| Type generation | Yes | One new JSON Schema, below. |

## Machine-readable contract

- `schemas/skill-audit-findings.schema.json` — the findings ledger every
  audit run writes. Consumers: the report renderer, `--propose` (which adapts
  findings into `openspec/schemas/candidate-work.schema.json` stubs), and any
  later benchmark change that fills `evidence.benchmark`. At implementation
  the file is copied verbatim to
  `skills/skill-audit/install_assets/openspec/schemas/` so `install.sh` ships
  it to consumer repositories; this copy is the plan-time authority.

## Text-level contracts captured in spec deltas

- **`archetypes.yaml` `procedure_mode` field and the two injected sentences** — `specs/agent-archetypes/spec.md`; the sentences are module-level constants in `agents_config.py` so tests import them rather than restate them.
- **Layer rule table** — `design.md` D2, mirrored in `skills/skill-audit/references/layers.md`.
- **Evidence join precedence** — `specs/harness-engineering/spec.md`.
- **Freshness stamp fields and `--check-freshness` exit codes** — `specs/skill-workflow/spec.md` "Skill Audit Freshness and Hand-off".
