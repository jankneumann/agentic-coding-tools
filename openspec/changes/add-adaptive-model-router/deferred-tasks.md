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

## DT-2 — Cedar policy deployment (task 3.4)

- **Origin**: task 3.4.
- **What**: Deploy mutable Cedar feasibility policies and vendor attributes beyond the pure feasibility filter already in `resolver.py`.
- **Why deferred**: Outside dg-00 wiring acceptance; requires a separately reviewed governance rollout.
- **Migration target**: follow-up dispatch-governance item.

## DT-3 — Roadmap exploration dispatch enforcement (task 4.6)

- **Origin**: task 4.6; task 4.5 tests and the fail-closed policy gate are already landed.
- **What**: Thread the exploration gate through every roadmap dispatch caller.
- **Why deferred**: Outside dg-00 wiring acceptance and overlaps later dispatch-governance orchestration work.
- **Migration target**: dedicated roadmap-orchestration follow-up.

## DT-4 — Feedback writers and calibration (tasks 5.4-5.6)

- **Origin**: tasks 5.4, 5.5, 5.6; feedback aggregation core from 5.1-5.3 is landed.
- **What**: Add best-effort learning-log writers and gen-eval calibration seeding.
- **Why deferred**: The dg-00 API accepts feedback, but producer integration and calibration are not prerequisites for its four acceptance outcomes.
- **Migration target**: feedback/calibration follow-up.

## DT-5 — Probes, tripwires, and quota headroom (tasks 6.1-6.8)

- **Origin**: tasks 6.1 through 6.8.
- **What**: ToS monitoring, model canaries, economic/posture tripwires, and optional quota-axi probing.
- **Why deferred**: Deliberately excluded from dg-00; watchdog wiring landed with independent refresher, local-probe, and ledger schedules and remains extensible for these jobs.
- **Migration target**: separate governance-signal changes.

## DT-6 — Usage dashboard and routing telemetry (tasks 7.1-7.5)

- **Origin**: tasks 7.1 through 7.5.
- **What**: React usage dashboard and coordinator routing telemetry.
- **Why deferred**: Outside the substrate wiring required by dg-00.
- **Migration target**: observability roadmap follow-up.

## DT-7 — Original integration tail (tasks 8.2-8.5)

- **Origin**: original tasks 8.2 through 8.5.
- **What**: External live-local-endpoint smoke test, absorbed-change archival, dev-time OpenRouter MCP registration, and an ADR for the full adaptive-routing vision.
- **Why deferred**: dg-00 is validated with deterministic service/delegation integration tests; archival, optional developer tooling, and the full-vision ADR must not be implied by this bounded tranche.
- **Migration target**: follow-up integration/documentation change after the broader proposal resumes.

## DT-8 — Central model-ownership migration from PR 417

- **Origin**: the stale plan-only PR 417 tasks 4.7-4.9 / design D14.
- **What**: Move concrete model IDs and fallback lists out of `agents.yaml` and into an exact harness/dispatch/tier route table.
- **Why deferred**: Not a dg-00 acceptance outcome and conflicts with the current static fallback contract. Keeping the current static mapping intact is required to prove `ROUTING_ADAPTIVE=off` equality.
- **Migration target**: a dedicated post-dg-00 configuration-ownership change. The catalog/Candidate seams remain extensible for ri-18 billing metadata without adding that metadata here.

## DT-9 — Full-spec residual reconciliation

- **Origin**: preserved original requirements in `deferred-specs/` after dg-00 scope convergence.
- **What**: Reconcile disappeared OpenRouter models to unavailable, propagate stale-catalog state into decision provenance, and schedule feedback/ToS/canary jobs when their implementations land.
- **Why deferred**: These are explicit obligations of the original full proposal, not any of the four dg-00 roadmap outcomes.
- **Migration target**: the follow-up changes that reactivate the corresponding preserved requirements.

## Preservation map

- `tasks-full-proposal.md`: exact pre-convergence task record.
- `work-packages-full-proposal.yaml`: exact pre-convergence machine DAG.
- `change-context-full-proposal.md`: pre-convergence full traceability matrix.
- `deferred-specs/`: exact pre-convergence normative delta specs.
