# Tasks: Score supervise rubric stubs in one batched call

> Change ID: `score-supervise-rubric-stubs-in-one-batched-call`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Ground the real code: the "analyst-archetype rubric dispatch" is host-orchestration
      prose in `SKILL.md`/`templates/rubric-prompt.md`, not Python; `digest.py` is
      deliberately host-assisted and never calls a model (design D1).
- [x] Add `skills/supervise/scripts/rubric_score.py` (new sibling script, not a change to
      `digest.py`): guarded `system_one_decisions` import, `score_batch(repo_root,
      manifest, dry_run=False)` batching up to 100 `Score` questions (20 stubs x 5 factors)
      in one `decide()` call (D2), all-or-nothing degradation matching
      `_validate_score_join`'s existing contract (D3), Score-to-schema mapping (D6).
- [x] Relax `openspec/schemas/supervise-rubric-score.schema.json`'s `factor.required` to
      `["score"]` (D4).
- [x] Add this change's own `contracts/schemas/{rubric-score,digest}.schema.json` and
      repoint `test_digest_schemas.py`'s `CHANGE_SCHEMA_DIR` here (D5) instead of the
      archived `add-supervisor-candidate-work-digest` change.
- [x] Update `digest.py`'s `rank_candidates`: add `_FACTOR_LEVEL_LABELS`, substitute a
      legend label into `justifications[factor]` when a factor's `justification` is absent
      (D4).
- [x] Update `SKILL.md`'s Rank step: try `rubric_score.py score-batch` first, dispatch the
      analyst sub-agent only on its failure (D7). Regenerated `.claude/skills/`,
      `.agents/skills/` mirrors via `install.sh` (gitignored, not committed).
- [x] Add `compute_agreement()` to `rubric_score.py` -- the report function only, per the
      scope correction in design D8 (no real manifest/archived-output data exists yet).
- [x] Update `skills/tests/supervise/test_digest_schemas.py`: split
      `test_rubric_rejects_a_missing_factor_or_justification` into a still-required-`score`
      test and a new `test_rubric_accepts_a_missing_justification` test.
- [x] Add `skills/tests/supervise/test_rubric_score.py`: `score_batch`'s batching shape,
      Score-to-schema mapping, all-or-nothing degradation (module unavailable, one missing
      factor, malformed score), CLI exit codes, `compute_agreement` against a synthetic
      fixture pair.
- [x] Add `test_rank_renders_score_legend_when_justification_is_absent` to `test_digest.py`
      (the digest snapshot test the acceptance outcome asks for).
- [x] Add `test_batched_rubric_scorer_is_tried_before_the_analyst_archetype_fallback` to
      `test_cycle_state.py`'s `TestWorkflowContract` (SKILL.md fallback-ordering assertion).
- [x] Confirm the full pre-existing `skills/tests/supervise/` suite (356 tests before this
      item) passes unchanged, plus all new/modified tests (382 total).
- [x] `uv run ruff check .` clean on all changed files (ri-16 lesson).
- [x] Write a MODIFIED spec delta for the existing `supervise` capability (not a new
      capability -- `openspec/specs/supervise/spec.md` already documents the
      Candidate-Work Digest requirement) reflecting the two-tier dispatch order and the
      optional-justification/legend-fallback behavior.
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance,
      `item.status = COMPLETED` on the roadmap item) in the same PR.
- [ ] Review and merge.
