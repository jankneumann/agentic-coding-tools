# Deferred Tasks: add-adaptive-model-router

## DT-1 — Internal task-derived benchmark (held-out verification)

- **Origin**: add-adaptive-model-router plan revision 2 (2026-07-09), amendment A4 from the
  Databricks coding-agent benchmark review; also absorbs the transcript-history backfill idea
  from superseded `usage-stats-multi-model` (see design.md "D12").
- **What**: Mine completed OpenSpec changes (real tasks + verification evidence already in this
  repo: tasks.md, validation reports, held-out test outcomes in episodic memory/transcripts) into
  a small internal benchmark suite. Grade by checkpoint-and-run-held-out-tests, no LLM judge.
  Use it to (a) seed quality *priors* for cloud models on this codebase — replacing OpenRouter
  public rankings as the primary prior source, which Databricks showed misleads on private
  codebases — and (b) extend the gen-eval calibration suite (task 5.6) beyond local models.
- **Why deferred**: Requires accumulated completed-change corpus and the routing posterior
  infrastructure from this change to be in place first; independent of the 8-package DAG.
- **Migration target**: follow-up proposal `add-internal-routing-benchmark` (not yet created);
  re-evaluate after this change's validate phase.
- **Scope context**: read-only mining of `openspec/changes/archive/**`, coordinator episodic
  memory, and collect-transcripts output; new suite under `packages/gen-eval/`.
- **Dependencies**: this change's wp-feedback (posterior store) and wp-db-catalog (catalog rows).
