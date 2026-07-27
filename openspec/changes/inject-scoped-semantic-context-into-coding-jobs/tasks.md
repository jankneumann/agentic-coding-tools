# Tasks: Inject scoped semantic context into coding jobs

> Change ID: `inject-scoped-semantic-context-into-coding-jobs` (ri-12)
> Each task is sized to be one commit.

## 0. Contracts (wp-contracts)

- [x] 0.1 Author `contracts/schemas/semantic-context-hit.schema.json` — the
      per-hit provenance record (`file_path`, `start_line`, `end_line`, `score`,
      `indexed_commit`, `index_id`, `scope_decision`, `language`, `content`),
      all required, `additionalProperties: false`.
- [x] 0.2 Author `contracts/schemas/semantic-context-section.schema.json` —
      `schema_version`, `status`, `consumer`, `requested_revision`, `hits`,
      `omissions`, `provenance`, `fallback`; closed enums for omission reasons
      and fallback triggers; `oneOf` enforcing `injected ⇒ fallback null` and
      `fallback ⇒ hits empty`.
- [x] 0.3 Author `contracts/README.md` documenting the two schemas, the
      `similarity → score` and `source_revision → indexed_commit` render
      mapping (D7), and the promote-before-archive obligation.
- [x] 0.4 Promote both schemas to `openspec/contracts/code-search/schemas/` and
      add the byte-identity assertion to
      `skills/tests/context-engineering/test_promoted_semantic_context_contracts.py`.
- [x] 0.5 Add `skills/tests/context-engineering/test_semantic_context_schemas.py`
      proving each schema is a valid JSON Schema and rejects the two
      contradictory states (`injected` with a fallback, `fallback` with hits).

## 1. Transport helper (wp-bridge-transport)

- [x] 1.1 Add `try_code_search(...)` to
      `skills/coordination-bridge/scripts/coordination_bridge.py`, POSTing the
      ri-03 `CodeSearchRequest` body to `/search/code` and returning the
      discriminated response unmodified inside the standard envelope.
- [x] 1.2 Make the helper obey the *Uniform HTTP Helper Envelope* contract:
      never raise; map transport failure, 401/403, 404, 422, 429 and 5xx onto
      distinct `status="failed"` reasons.
- [x] 1.3 Gate the helper on `CAN_CODE_SEARCH` from `detect_coordination()` and
      return `status="skipped"`, `reason="capability_absent"` when false.
- [x] 1.4 Add `skills/tests/coordination-bridge/test_try_code_search.py`
      covering ok / skipped / each failure mapping with a stubbed transport.

## 2. Retrieval helper (wp-retrieval)

- [x] 2.1 Create `skills/context-engineering/scripts/` with `__init__.py` and
      the `SemanticContextRequest` / `SemanticContextResult` / `InjectedHit` /
      `Omission` / `ContextFallback` / `SectionProvenance` value types (D1),
      each with `to_dict()` matching the section schema.
- [x] 2.2 Implement revision resolution (D3): `--show-toplevel`, `rev-parse
      HEAD`, `FullRevision` shape check, and the `status --porcelain`
      staleness short-circuit.
- [x] 2.3 Implement scope derivation (D2): `index_scopes()` →
      `ReadScope.from_index_scopes()` → explicit scope payload, including the
      `no_declared_scope` and `scope_self_cancelling` outcomes.
- [x] 2.4 Implement namespace/index selection (D4): read the ri-09 checkpoint
      report, accept it only when `status=succeeded` and `indexed_revision ==
      revision`, else fall back to `CANONICAL_NAMESPACE`.
- [x] 2.5 Implement the deterministic rank key and the dedup pass (D5):
      `duplicate_exact` and `duplicate_contained`, partial overlap retained.
- [x] 2.6 Implement the first-fit budget pass (D6) with the four bounds, their
      env overrides, the fixed reason precedence, and no early break.
- [x] 2.7 Implement the local deny re-check and the `scope_filtered` /
      `all_hits_scope_filtered` outcome (D2).
- [x] 2.8 Implement `collect_semantic_context()` — the total
      `CodeSearchState` → trigger mapping (D8), the fixed local-precondition
      order, the `SEMANTIC_CONTEXT_INJECTION` gate (D9), and the guarantee that
      it never raises.
- [x] 2.9 Add `skills/tests/context-engineering/test_semantic_context_determinism.py`
      — hand-derived expected order over a tie-heavy fixture, plus the
      seeded-shuffle invariance assertion (D12).
- [x] 2.10 Add `skills/tests/context-engineering/test_semantic_context_budget.py`
      — each of the six omission reasons produced deterministically, and the
      no-early-break property (a small hit admitted after a large one is
      skipped).

## 3. Renderer (wp-renderer)

- [x] 3.1 Implement `skills/context-engineering/scripts/render_semantic_context.py`
      producing the injected `## Semantic code context` section exactly per D7,
      including the untrusted-content line.
- [x] 3.2 Render the per-hit provenance line with all five roadmap-required
      fields plus `index_id`, using the `score` / `indexed_commit` names.
- [x] 3.3 Render the fallback section variant with trigger, state, reason, and
      the suggested `rg` command built from the package's `read_allow`.
- [x] 3.4 Emit nothing at all (not even a heading) when the result's fallback
      reason is `injection_disabled`, so a flag-off run is byte-identical to
      today (D9).
- [x] 3.5 Add `skills/tests/context-engineering/test_render_semantic_context.py`
      with golden-text assertions for injected, each fallback trigger, and the
      flag-off empty case.

## 4. Consumers (wp-consumers)

- [x] 4.1 Extend `skills/context-engineering/SKILL.md` — semantic code as a
      Level-3 augmentation, the retrieval protocol, the budget table, the
      omission and fallback vocabularies, and the opt-in flag.
- [x] 4.2 Add the consumer protocol block to `skills/implement-feature/SKILL.md`
      and `skills/iterate-on-implementation/SKILL.md`.
- [x] 4.3 Add the consumer protocol block to `skills/quick-task/SKILL.md` and
      `skills/debugging-and-error-recovery/SKILL.md`, including the
      `no_declared_scope` behaviour for change-less jobs.
- [x] 4.4 Add the consumer protocol block to `skills/validate-feature/SKILL.md`
      and `skills/parallel-review-implementation/SKILL.md`.
- [x] 4.5 Add `skills/tests/context-engineering/test_consumer_protocol_blocks.py`
      asserting all six consumer SKILL.md files declare a distinct `consumer`
      id and delegate to the shared helper rather than restating the algorithm.

## 5. Fallback proof matrix (wp-fallback-tests)

- [x] 5.1 `test_fallback_stale.py` — dirty worktree and `not_indexed` both
      yield `trigger=stale` with the right reason, no exception, exit 0.
- [x] 5.2 `test_fallback_unavailable.py` — flag off, capability absent,
      non-HTTP transport, bridge failure, `not_configured`, `unavailable`, and
      429 each yield `trigger=unavailable` with distinct reasons.
- [x] 5.3 `test_fallback_mismatched.py` — `revision_mismatch` yields
      `trigger=mismatched`, zero hits, and an exact-search instruction.
- [x] 5.4 `test_fallback_out_of_scope.py` — `scope_rejected`, missing package
      scope, self-cancelling scope, and all-hits-filtered each yield
      `trigger=out_of_scope` with distinct reasons.
- [ ] 5.5 `test_fallback_never_blocks.py` — for every trigger the helper
      returns a `SemanticContextResult`, and an unknown/future state string maps
      to `unavailable` / `unknown_state` rather than injecting.

## 6. Integration (wp-integration)

- [ ] 6.1 Run the full ri-12 suite plus the pre-existing
      `skills/coordination-bridge/scripts/tests` suite and record the result.
- [ ] 6.2 Verify the flag-off invariant end to end: with
      `SEMANTIC_CONTEXT_INJECTION` unset, an assembled context block for one
      consumer is byte-identical to the pre-change output.
- [ ] 6.3 Add `docs/guides/semantic-context-injection.md` documenting the flag,
      the four triggers, the budget defaults, and the HTTP-only constraint
      (D13); link it from the code-search guide.
- [ ] 6.4 Sync skills to the runtime mirrors with
      `bash skills/install.sh --mode rsync --force --deps none --python-tools none`
      and confirm no source file under `skills/` was modified by the sync.
- [ ] 6.5 Run `openspec validate inject-scoped-semantic-context-into-coding-jobs
      --strict` and
      `python3 skills/validate-packages/scripts/validate_work_packages.py
      openspec/changes/inject-scoped-semantic-context-into-coding-jobs/work-packages.yaml`.
- [ ] 6.6 Reconcile every package's outputs, tick this file, and record the
      session log.
