# Tasks — add-supervisor-candidate-work-digest

Five phases, one per work package. Test tasks precede the implementation they verify
(TDD RED → GREEN). Sizes per the plan-feature Task Sizing Reference; no task is L or XL.

Capability short name: `sv` = `supervise`. Contracts:
`contracts/schemas/rubric-score.schema.json`, `contracts/schemas/digest.schema.json`.

---

## Phase 0 — wp-contracts: rubric and digest shapes frozen first

- [ ] 0.1 Test: both schemas are valid 2020-12 documents; a full rubric fixture validates;
      a score of 0 or 6, a missing factor, and a bad fingerprint each fail; the digest
      fixture validates and `factors` keys equal the rubric's five — **XS**
      **Spec scenarios**: sv *Schema-invalid rubric output is rejected*
      **Contracts**: both
      **Dependencies**: None

- [ ] 0.2 Fixtures: `skills/tests/supervise/fixtures/digest/{stubs/*.json, rubric-valid.json,
      rubric-invalid-*.json, digest-expected.json, roadmap-x/roadmap.yaml}` — **XS**
      **Contracts**: both
      **Dependencies**: 0.1

- [ ] Checkpoint: schema test green, review the diff, confirm only the change directory and
      the fixtures directory changed

## Phase 1 — wp-digest-module: `digest.py`

- [ ] 1.1 Test: `store` writes one byte-stable file per surviving stub under
      `openspec/supervise/candidates/` named by the reversible `stub_key` mapping; re-run
      over the same stubs changes no bytes; `--dry-run` writes nothing; every path passes
      `classify_write` — **S**
      **Spec scenarios**: sv *Digest on a fresh cycle*, *Dry run writes nothing*
      **Design decisions**: D1
      **Dependencies**: None

- [ ] 1.2 Implement `store` (+ `key_to_filename` / `filename_to_key`) in `digest.py` — **S**
      **Design decisions**: D1, D3
      **Dependencies**: 1.1

- [ ] 1.3 Test: `rank` rejects each invalid rubric fixture naming stub + field and writes
      nothing; valid scores + fixture tree produce `digest-expected.json` byte-for-byte;
      `dependency_ready`, `staleness_days`, `prior_decision` computed from the fixture
      tree; `rejected` excluded, `deferred` sunk, `deferred` past `until` back to pending;
      changing one factor reorders exactly per the weights; scores cached per stub with
      the fingerprint; unchanged fingerprint → `cached_scores: true` and no
      `--scores` needed — **S**
      **Spec scenarios**: sv *Ranking is a pure function of scores and signals*, *Unchanged
      fingerprint reuses cached scores*, *Prior decisions shape the ranking*,
      *Schema-invalid rubric output is rejected*
      **Contracts**: rubric-score, digest
      **Design decisions**: D2
      **Dependencies**: None

- [ ] 1.4 Implement `rank` — validation, mechanical signals, weights, caching, ordering,
      `digest.json` write; and `digest` (section assignment + prose render) — **M**
      **Design decisions**: D2, D6
      **Dependencies**: 1.2, 1.3

- [ ] Checkpoint: `skills/tests/supervise` green including `TestHostAssistedInvariant`
      (which now covers `digest.py`), review the diff, confirm `cycle_state.py` unchanged

- [ ] 1.5 Test: `stub-to-request` emits one `op: add` with the D4 field mapping, next free
      `item_id`, `change_id` from the stub, provenance line, `--acceptance` values;
      refuses without `--acceptance`; the emitted request passes `refiner.preview_refinement`
      against the fixture roadmap with one new item and no errors — **S**
      **Spec scenarios**: sv *Approve a stub into an existing roadmap*, *Missing acceptance
      outcomes are refused*, *Approval never bypasses the preview*
      **Design decisions**: D4
      **Dependencies**: None

- [ ] 1.6 Implement `stub-to-request` — **S**
      **Design decisions**: D4
      **Dependencies**: 1.5

- [ ] 1.7 Test: `decide` records `{stub_key, decision, roadmap_ref|route, until, reason,
      decided_at}` in the mirror's `back_edge.digested_stubs`, replacing an existing entry
      for the same key; the next `store` run prunes `approved`/`rejected` files and their
      `.rubric.json`; `deferred` files survive; an AST walk over `skills/supervise/scripts/`
      finds no write to any path ending in `roadmap.yaml` — **S**
      **Spec scenarios**: sv *Decision is recorded and the store is pruned*, *Deferred stub
      returns after its date*, *Approval never bypasses the preview*
      **Design decisions**: D5
      **Dependencies**: None

- [ ] 1.8 Implement `decide` and the prune step in `store` — **S**
      **Design decisions**: D5
      **Dependencies**: 1.7

- [ ] Checkpoint: supervise suite green, `ruff` clean, review the cumulative diff against
      `write_allow`

## Phase 2 — wp-rubric-prompt: the sub-agent contract

- [ ] 2.1 Test: `templates/rubric-prompt.md` names all five factors with the D2 questions,
      states the 1–5 scale and the risk inversion, instructs JSON-only output, and embeds
      the schema `$id`; a fixture batch rendered through the template contains every stub
      key and its provenance excerpt — **XS**
      **Spec scenarios**: sv *Digest on a fresh cycle*
      **Contracts**: rubric-score
      **Design decisions**: D2
      **Dependencies**: None

- [ ] 2.2 Write `templates/rubric-prompt.md` as a pure template with `{{batch}}`,
      `{{ready_set}}`, `{{fingerprint}}` slots the host fills; document the slots at the
      top — **S**
      **Design decisions**: D2
      **Dependencies**: 2.1

- [ ] Checkpoint: prompt test green, review the diff

## Phase 3 — wp-skill-docs: rewire CYCLE and INTAKE

- [ ] 3.1 Test: `TestWorkflowContract` extended — CYCLE step 2 stores stubs, step 4 dispatches
      the rubric sub-agent then runs `digest.py rank`, step 5 renders from `digest.json`;
      the unchanged-fingerprint rule re-presents `digest.json`; INTAKE has an "approve from
      digest" step naming `stub-to-request`, `refiner.py preview`, `apply
      --expect-base-sha256`, and `decide`; existing assertions (`snapshot-writes`,
      `audit-since`, `record --keys`, dry-run `MUST NOT invoke` block) still hold — **XS**
      **Spec scenarios**: sv *Digest on a fresh cycle*, *Approve a stub into an existing
      roadmap*, *New-roadmap stub falls back to plan-roadmap*
      **Design decisions**: D2, D4, D6
      **Dependencies**: None

- [ ] 3.2 Rewrite CYCLE steps 2–5 in `skills/supervise/SKILL.md` around store, rubric
      dispatch, `rank`, `digest.json`; update the Output table and Idempotency section for
      the store, cache, and `digest.json` — **S**
      **Design decisions**: D1, D2, D6
      **Dependencies**: 3.1

- [ ] 3.3 Add the INTAKE "approve from digest" step: `stub-to-request`, `refiner.py preview`,
      operator confirmation, `apply --expect-base-sha256`, `decide`; plan-roadmap fallback
      for new-roadmap stubs — **XS**
      **Design decisions**: D4, D5
      **Dependencies**: 3.1

- [ ] 3.4 Run `install.sh` to resync mirrors — **XS**
      **Dependencies**: 3.2, 3.3

- [ ] Checkpoint: supervise suite green, mirrors synced

## Phase 4 — wp-integration

- [ ] 4.1 Run all `skills/tests`, `ruff` on `skills/supervise`; run one scripted end-to-end
      cycle over the fixture tree (store → rank with the valid rubric fixture → digest →
      decide → store prunes) and diff against `digest-expected.json` — **S**
      **Dependencies**: all Phase 1–3 tasks

- [ ] 4.2 `openspec validate add-supervisor-candidate-work-digest --strict`; append the
      Implementation `PhaseRecord`; update checkboxes; commit; push — **XS**
      **Dependencies**: 4.1
