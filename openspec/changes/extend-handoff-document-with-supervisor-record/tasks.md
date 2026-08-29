# Tasks — extend-handoff-document-with-supervisor-record

Six phases, one per work package. Test tasks precede the implementation they verify
(TDD RED → GREEN). Sizes per the plan-feature Task Sizing Reference; no task is L or XL.

Capability short names: `ac` = `agent-coordinator`, `sw` = `skill-workflow`,
`sv` = `supervise`. Contracts: `contracts/schemas/supervisor-record.schema.json`,
`contracts/db/034_handoff_supervisor_record.sql`, `contracts/openapi/handoffs.yaml`.

---

## Phase 0 — wp-contracts: the record shape is frozen first

- [ ] 0.1 Test: `supervisor-record.schema.json` is a valid 2020-12 schema; a full fixture
      validates; a `pending_gates` entry without `deadline` fails; an unknown `gate` fails;
      the `gate` enum equals `trust_posture.Gate` values — **XS**
      **Spec scenarios**: sv *Pending gate carries the deadline downstream writers need*
      **Contracts**: supervisor-record.schema.json
      **Design decisions**: D7
      **Dependencies**: None

- [ ] 0.2 Fixtures: `skills/tests/supervise/fixtures/supervisor-record/{full,minimal,invalid-*}.json`
      plus a matching `handoff-with-record.json` row fixture — **XS**
      **Contracts**: supervisor-record.schema.json
      **Dependencies**: 0.1

- [ ] Checkpoint: schema test green, review the diff, confirm only the change directory and
      the fixtures directory changed

## Phase 1 — wp-coordinator: one column, one key on every coordinator surface

- [ ] 1.1 Test: `HandoffDocument.from_dict` yields `supervisor_record=None` for a row without
      the key and the dict itself for a row with it; `HandoffService.write(...,
      supervisor_record=...)` passes `p_supervisor_record` to the RPC; omitted → `None`;
      every existing `test_handoffs.py` test passes unchanged — **S**
      **Spec scenarios**: ac *Pre-migration rows load with a null record*, *Handoff without a
      supervisor record is unchanged*
      **Contracts**: 034 migration
      **Design decisions**: D1
      **Dependencies**: None

- [ ] 1.2 Implement the dataclass field, `from_dict`, the `write()` parameter plus RPC arg
      in `handoffs.py`; add migration `034` from `contracts/db/` — **S**
      **Design decisions**: D1
      **Dependencies**: 1.1

- [ ] 1.3 Test: arity — `write_handoff` in migrations has exactly one definition with nine
      parameters; `test_rpc_migration_alignment` still passes — **XS**
      **Spec scenarios**: ac *RPC name alignment holds*, *Migration is additive and
      forward-only*
      **Design decisions**: D1
      **Dependencies**: 1.2

- [ ] Checkpoint: `agent-coordinator/tests/test_handoffs.py` + alignment test green, review
      the diff, confirm no API/MCP file changed yet

- [ ] 1.4 Test: `POST /handoffs/write` accepts `supervisor_record` (object or null), 422s
      on a non-object; `POST /handoffs/read` rows carry the key; MCP `write_handoff` /
      `read_handoff` plus `handoffs://recent` round-trip it; `proxy_write_handoff` forwards
      it; `coordination_cli handoff read` prints it — **S**
      **Spec scenarios**: ac *Supervisor record round-trips through every surface*,
      *Non-object record is rejected at the HTTP boundary*
      **Contracts**: openapi/handoffs.yaml
      **Design decisions**: D1
      **Dependencies**: 1.2

- [ ] 1.5 Implement the one-key edit in `coordination_api.py` (`HandoffWriteRequest`, read
      row), `coordination_mcp.py` (both tools + resource), `http_proxy.py`,
      `coordination_cli.py`, `help_service.py` — **M**
      **Design decisions**: D1
      **Dependencies**: 1.4

- [ ] 1.6 Test (live, `tests/e2e/postgres/test_handoffs_live.py`): write with a full fixture
      record, read back byte-identical; write without → `null` — **S**
      **Spec scenarios**: ac *Supervisor record round-trips through every surface*
      **Dependencies**: 1.5

- [ ] Checkpoint: coordinator unit + e2e suites green, `mypy --strict` clean, review the
      diff against `write_allow`

## Phase 2 — wp-host-plumbing: bridge, PhaseRecord, hooks, fallback schema

- [ ] 2.1 Test: `try_handoff_write(content={"supervisor_record": R})` posts the key; without
      it the body is byte-identical to today's — **XS**
      **Spec scenarios**: sw *Bridge passes the supervisor record through*
      **Design decisions**: D6
      **Dependencies**: None

- [ ] 2.2 Implement the conditional key in `coordination_bridge.try_handoff_write` — **XS**
      **Design decisions**: D6
      **Dependencies**: 2.1

- [ ] 2.3 Test: `PhaseRecord(supervisor_record=None).to_handoff_payload()` equals the
      pre-change payload; set → round-trips through `from_handoff_payload`; the local
      fallback file with a record validates against `handoff-local-fallback.schema.json`;
      existing fixture files still validate — **S**
      **Spec scenarios**: sw *PhaseRecord carries the record without changing existing
      payloads*, *Local fallback file validates with the record present*
      **Design decisions**: D6
      **Dependencies**: None

- [ ] 2.4 Implement the `PhaseRecord` field, conditional payload key, parse, plus the
      fallback-schema property — **S**
      **Design decisions**: D6
      **Dependencies**: 2.3

- [ ] Checkpoint: `skills/tests/phase-record-compaction` green, review the diff, confirm
      fixture files unchanged

- [ ] 2.5 Test: the PreCompact hook plus the SessionEnd hook include `supervisor_record` in
      the `/handoffs/write` body when the latest phase record has one, otherwise produce
      today's body; source vs `agent-coordinator/scripts/` mirror copies are identical — **S**
      **Spec scenarios**: sw *Compaction and session end do not drop the record*
      **Design decisions**: D5
      **Dependencies**: None

- [ ] 2.6 Implement the pass-through in `precompact_handoff.py` plus `deregister_agent.py`,
      sync the mirror copies; leave `register_agent.py` untouched — **XS**
      **Design decisions**: D5
      **Dependencies**: 2.5

- [ ] Checkpoint: `skills/tests/session-bootstrap` green, `git diff --stat` shows no
      `register_agent.py` change

## Phase 3 — wp-supervisor-builder: `cycle_state.py supervisor-record`

- [ ] 3.1 Test: builder derives `active_changes` from a fixture tree (two changes with
      loop-state v4 vs v5, one with a roadmap match); sorted by `change_id`; v4 state
      yields `pending_gate: null`; a change absent from disk is absent from output — **S**
      **Spec scenarios**: sv *Derivable section is recomputed, not carried*
      **Design decisions**: D2, D3
      **Dependencies**: None

- [ ] 3.2 Test: with `--prior`, `pending_gates` / `standing_decisions` / `back_edge` carry
      forward; a decision past `expires_at` is dropped; prior may be a handoff JSON or the
      mirror; two runs over an unchanged tree are byte-identical; output validates against
      the record schema — **S**
      **Spec scenarios**: sv *Non-derivable sections are carried forward*, *Builder is
      deterministic*
      **Contracts**: supervisor-record.schema.json
      **Design decisions**: D3
      **Dependencies**: None

- [ ] 3.3 Implement `build_supervisor_record(repo_root, prior=None, *, now=...)` plus the
      `supervisor-record` subcommand in `cycle_state.py` — **M**
      **Design decisions**: D2, D3
      **Dependencies**: 3.1, 3.2

- [ ] Checkpoint: `skills/tests/supervise` green including `TestHostAssistedInvariant`,
      review the diff

- [ ] 3.4 Test: `write_mirror()` writes only the three non-derivable sections plus
      `schema_version`/`written_at`; passes `audit-writes`; `select_prior(handoff, mirror)`
      returns the newer by `written_at`, the mirror when the handoff is missing — **S**
      **Spec scenarios**: sv *Mirror holds only the non-derivable sections*, *Newer mirror
      wins over a stale handoff*, *Coordinator unreachable falls back to the mirror*
      **Design decisions**: D4
      **Dependencies**: None

- [ ] 3.5 Implement `write_mirror`, `select_prior`, plus the `mirror` / `rehydrate`
      subcommands — **S**
      **Design decisions**: D4
      **Dependencies**: 3.4

- [ ] Checkpoint: supervise suite green, review the diff, verify scope

## Phase 4 — wp-skill-docs: wire /supervise

- [ ] 4.1 Test: `TestWorkflowContract` extended — rehydrate step 1 names
      `supervisor-record` plus `try_handoff_read`; INTAKE/CYCLE end with the record write;
      the existing string assertions (`snapshot-writes`, `audit-since`, `record --keys`,
      dry-run block) still hold — **XS**
      **Spec scenarios**: sv *Fresh session lists state from the handoff alone*
      **Design decisions**: D4, D5
      **Dependencies**: None

- [ ] 4.2 Rewrite `skills/supervise/SKILL.md` rehydrate step 1 plus the INTAKE/CYCLE closing
      steps around the builder, mirror, handoff write; render the record's sections in
      the digest's "Needs a decision" / "Ready now" — **S**
      **Design decisions**: D4, D5
      **Dependencies**: 4.1

- [ ] 4.3 Add `/supervise` to the handoff-hook skill list wherever prose enumerates it
      (`docs/guides/workflow.md` if applicable); run `install.sh` — **XS**
      **Dependencies**: 4.2

- [ ] Checkpoint: supervise suite green, mirrors synced

## Phase 5 — wp-integration

- [ ] 5.1 Run `agent-coordinator` unit + e2e suites, all `skills/tests`, `ruff`, `mypy
      --strict` on `agent-coordinator/src` — **S**
      **Dependencies**: all Phase 1–4 tasks

- [ ] 5.2 Promote `contracts/openapi/handoffs.yaml` over the canonical contract; run
      `make context-drift-gate` — **XS**
      **Dependencies**: 5.1

- [ ] 5.3 `openspec validate extend-handoff-document-with-supervisor-record --strict`; append
      the Implementation `PhaseRecord`; update checkboxes; commit; push — **XS**
      **Dependencies**: 5.2
