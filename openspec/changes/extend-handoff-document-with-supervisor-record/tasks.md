# Tasks — extend-handoff-document-with-supervisor-record

Six phases, one per work package. Test tasks precede the implementation they verify
(TDD RED → GREEN). Sizes per the plan-feature Task Sizing Reference; no task is L or XL.

Capability short names: `ac` = `agent-coordinator`, `sw` = `skill-workflow`,
`sv` = `supervise`. Contracts: `contracts/schemas/supervisor-record.schema.json`,
`contracts/db/034_handoff_supervisor_record.sql`, `contracts/openapi/handoffs.yaml`.

---

## Phase 0 — wp-contracts: the record shape is frozen first

- [x] 0.1 Test: both supervisor record schemas are valid 2020-12 schemas under a `FormatChecker`; full and mirror fixtures validate; a `pending_gates` entry without `deadline` fails; an unknown `gate` fails;
      the `gate` enum equals `trust_posture.Gate` values; root `written_by` and all
      `back_edge` members are required — **XS**
      **Spec scenarios**: sv *Pending gate carries the deadline downstream writers need*
      **Contracts**: supervisor-record.schema.json
      **Design decisions**: D7
      **Dependencies**: None

- [x] 0.2 Fixtures: `skills/tests/supervise/fixtures/supervisor-record/{full,minimal,invalid-*}.json`
      plus a matching `handoff-with-record.json` row fixture and mirror fixture — **XS**
      **Contracts**: supervisor-record.schema.json
      **Dependencies**: 0.1

- [x] Checkpoint: schema test green, review the diff, confirm only the change directory and
      the fixtures directory changed

## Phase 1 — wp-coordinator: one column, one key on every coordinator surface

- [x] 1.1 Test: `HandoffDocument.from_dict` yields `supervisor_record=None` for a row without
      the key and the dict itself for a row with it; `HandoffService.write(...,
      supervisor_record=...)` passes `p_supervisor_record` to the RPC; omitted → `None`;
      every existing `test_handoffs.py` test passes unchanged — **S**
      **Spec scenarios**: ac *Pre-migration rows load with a null record*, *Handoff without a
      supervisor record is unchanged*
      **Contracts**: 034 migration
      **Design decisions**: D1
      **Dependencies**: None

- [x] 1.2 Implement the dataclass field, `from_dict`, the `write()` parameter plus RPC arg
      in `handoffs.py`; add migration `034` from `contracts/db/` — **S**
      **Design decisions**: D1
      **Dependencies**: 1.1

- [x] 1.3 Test: compatibility — `write_handoff` in migrations has exactly one definition with nine
      parameters; the legacy defaults, empty-summary behavior, execution mode, and
      descending read order are unchanged; `test_rpc_migration_alignment` still passes — **S**
      **Spec scenarios**: ac *RPC name alignment holds*, *Migration is additive and
      forward-only*
      **Design decisions**: D1
      **Dependencies**: 1.2

- [x] Checkpoint: `agent-coordinator/tests/test_handoffs.py` + alignment test green, review
      the diff, confirm no API/MCP file changed yet

- [x] 1.4 Test: `POST /handoffs/write` accepts `supervisor_record` (object or null), 422s
      on a non-object; `POST /handoffs/read` rows carry the key; MCP `write_handoff` /
      `read_handoff` plus `handoffs://recent` round-trip it; `proxy_write_handoff` forwards
      it; `coordination_cli handoff read` prints it; a newer ordinary handoff cannot mask
      the supervisor row when `supervisor_only=true` — **S**
      **Spec scenarios**: ac *Supervisor record round-trips through every surface*,
      *Non-object record is rejected at the HTTP boundary*
      **Contracts**: openapi/handoffs.yaml
      **Design decisions**: D1
      **Dependencies**: 1.2

- [x] 1.5 Implement the one-key edit and `supervisor_only` read filter in `coordination_api.py` (`HandoffWriteRequest`, read
      row), `coordination_mcp.py` (both tools + resource), `http_proxy.py`,
      `coordination_cli.py`, `help_service.py` — **M**
      **Design decisions**: D1
      **Dependencies**: 1.4

- [x] 1.6 Test (live, `tests/e2e/postgres/test_handoffs_live.py`): write with a full fixture
      record, read back structurally equal after JSON decoding; write without → `null` — **S**
      **Spec scenarios**: ac *Supervisor record round-trips through every surface*
      **Dependencies**: 1.5

- [x] Checkpoint: coordinator unit + e2e suites green, `mypy --strict` clean, review the
      diff against `write_allow`

## Phase 2 — wp-host-plumbing: bridge, PhaseRecord, hooks, fallback schema

- [x] 2.1 Test: `try_handoff_write(content={"supervisor_record": R})` posts the key; without
      it the body is byte-identical to today's — **XS**
      **Spec scenarios**: sw *Bridge passes the supervisor record through*
      **Design decisions**: D6
      **Dependencies**: None

- [x] 2.2 Implement the conditional key in `coordination_bridge.try_handoff_write` — **XS**
      **Design decisions**: D6
      **Dependencies**: 2.1

- [x] 2.3 Test: `PhaseRecord(supervisor_record=None).to_handoff_payload()` equals the
      pre-change payload; set → round-trips through `from_handoff_payload`; the local
      fallback file with a record validates against `handoff-local-fallback.schema.json`;
      existing fixture files still validate — **S**
      **Spec scenarios**: sw *PhaseRecord carries the record without changing existing
      payloads*, *Local fallback file validates with the record present*
      **Design decisions**: D6
      **Dependencies**: None

- [x] 2.4 Implement the `PhaseRecord` field, conditional payload key, parse, plus the
      fallback-schema property — **S**
      **Design decisions**: D6
      **Dependencies**: 2.3

- [x] Checkpoint: `skills/tests/phase-record-compaction` green, review the diff, confirm
      fixture files unchanged

- [x] 2.5 Test: `try_handoff_read(supervisor_only=true)` forwards the filter and returns
      the newest record-bearing handoff even when a newer ordinary handoff exists — **S**
      **Spec scenarios**: ac *Supervisor-only read is not masked by ordinary handoffs*
      **Design decisions**: D7A
      **Dependencies**: None

- [x] 2.6 Implement bridge support for the `supervisor_only` read parameter; leave all three
      generic session hooks untouched — **XS**
      **Design decisions**: D5, D7A
      **Dependencies**: 2.5

- [x] Checkpoint: bridge + PhaseRecord suites green; `git diff --stat` shows no session-hook change

## Phase 3 — wp-supervisor-builder: `cycle_state.py supervisor-record`

- [x] 3.1 Test: builder derives `active_changes` from a fixture tree (v4/v5, DONE, ESCALATE,
      malformed and missing loop-state, duplicate roadmap matches, parent plus child registry
      entries); sorted by `change_id`; v4 yields `pending_gate: null`; DONE/invalid changes
      are absent and degraded inputs are reported — **S**
      **Spec scenarios**: sv *Derivable section is recomputed, not carried*
      **Design decisions**: D2, D3
      **Dependencies**: None

- [x] 3.2 Test: with `--prior`, `pending_gates` / `standing_decisions` / `back_edge` carry
      forward; a decision past `expires_at` is dropped; prior may be a normalized handoff record extracted from
      `data.handoffs[0].supervisor_record` or the mirror; two runs over an unchanged tree
      with the same explicit `--now` value are byte-identical; output validates with a format checker against the canonical full-record schema — **S**
      **Spec scenarios**: sv *Non-derivable sections are carried forward*, *Builder is
      deterministic*
      **Contracts**: supervisor-record.schema.json
      **Design decisions**: D3
      **Dependencies**: None

- [x] 3.3 Implement `build_supervisor_record(repo_root, prior=None, *, now=...)` plus the
      `supervisor-record` subcommand with an optional `--now` test hook in `cycle_state.py` — **M**
      **Design decisions**: D2, D3
      **Dependencies**: 3.1, 3.2

- [x] Checkpoint: `skills/tests/supervise` green including `TestHostAssistedInvariant`,
      review the diff

- [x] 3.4 Test: `write_mirror()` writes only the three sanitized non-derivable sections plus
      `schema_version`/`written_at`; validates against the dedicated mirror schema; is a
      no-op preserving `written_at` for unchanged content; passes `audit-writes`; the mirror
      is excluded from cycle fingerprinting; `select_prior(handoff, mirror)`
      returns the newer by `written_at`, the mirror when the handoff is missing — **S**
      **Spec scenarios**: sv *Mirror holds only the non-derivable sections*, *Newer mirror
      wins over a stale handoff*, *Coordinator unreachable falls back to the mirror*
      **Design decisions**: D4
      **Dependencies**: None

- [x] 3.5 Implement `write_mirror`, `select_prior`, mirror sanitization, fingerprint exclusion, plus the `mirror` / `rehydrate`
      subcommands — **S**
      **Design decisions**: D4
      **Dependencies**: 3.4

- [x] Checkpoint: supervise suite green, review the diff, verify scope

## Phase 4 — wp-skill-docs: wire /supervise

- [x] 4.1 Test: rehydrate behavior covers handoff-only, a newer ordinary handoff, coordinator-down
      mirror fallback, newer mirror, and rendered pending gates; `TestWorkflowContract` names
      `supervisor-record` plus `try_handoff_read(supervisor_only=true)`; INTAKE and non-dry-run
      CYCLE write the mirror before final audit and handoff afterward; dry-run writes neither;
      the existing string assertions (`snapshot-writes`, `audit-since`, `record --keys`,
      dry-run block) still hold — **XS**
      **Spec scenarios**: sv *Fresh session restores durable state and re-derives active changes*
      **Design decisions**: D4, D5
      **Dependencies**: None

- [x] 4.2 Rewrite `skills/supervise/SKILL.md` rehydrate step 1 plus the INTAKE/CYCLE closing
      steps around the builder, mirror, handoff write; render the record's sections in
      the digest's "Needs a decision" / "Ready now" — **S**
      **Design decisions**: D4, D5
      **Dependencies**: 4.1

- [x] 4.3 Add `/supervise` to the handoff-hook skill list wherever prose enumerates it
      (`docs/guides/workflow.md` if applicable); run `install.sh` — **XS**
      **Dependencies**: 4.2

- [x] Checkpoint: supervise suite green, mirrors synced

## Phase 5 — wp-integration

- [x] 5.1 Run `agent-coordinator` unit + e2e suites, all `skills/tests`, `ruff`, `mypy
      --strict` on `agent-coordinator/src` — **S**
      **Dependencies**: all Phase 1–4 tasks

- [x] 5.2 Promote `contracts/openapi/handoffs.yaml` over the canonical contract and both record
      schemas to `openspec/schemas/`; run
      `make context-drift-gate` — **XS**
      **Dependencies**: 5.1

- [x] 5.3 `openspec validate extend-handoff-document-with-supervisor-record --strict`; append
      the Implementation `PhaseRecord`; update checkboxes; commit; push — **XS**
      **Dependencies**: 5.2
