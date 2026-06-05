# Tasks: cross-vendor-arbitrage-instrument

Test-first ordering: within each phase, test tasks precede the implementation they verify. Phases map to work packages in `work-packages.yaml`. Checkpoint markers appear every 2–3 implementation tasks.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Validate the four contract schemas parse as JSON Schema 2020-12 and add a schema-lint test
  **Contracts**: contracts/events/arbitrage-signal.schema.json, contracts/events/cost-ledger-entry.schema.json, contracts/events/router-decision.schema.json, contracts/config/vendor-pricing-eligibility.schema.json
  **Design decisions**: D10
  **Dependencies**: None
- [ ] 1.2 Add fixture instances (one valid + one invalid) per contract schema for downstream tests to reuse
  **Contracts**: all four schemas
  **Dependencies**: 1.1
- [ ] 1.3 Checkpoint: run schema-lint + fixtures, review diff, verify scope (contracts/ only)

## Phase 2 — Coordinator signal substrate (wp-coordinator-signals)

- [ ] 2.1 Write tests for `arbitrage_signal` recording — five families, async non-blocking, no-op when disabled
  **Spec scenarios**: Signal Recording — "A cost/quota signal is recorded with vendor labels", "A throttle event captures the invisible cap", "Recording degrades gracefully when disabled"
  **Contracts**: contracts/events/arbitrage-signal.schema.json
  **Design decisions**: D2, D7
  **Dependencies**: 1.2
- [ ] 2.2 Create `agent-coordinator/src/arbitrage_signal.py` — record via `AuditService.log_operation` (operation `arbitrage.signal.<family>`); validate payload against the contract
  **Spec scenarios**: Signal Recording — all
  **Design decisions**: D2
  **Dependencies**: 2.1
- [ ] 2.3 Register the `coordinator.signal` OTel meter in `telemetry.py` and emit labelled measurements (vendor/model/modality/archetype) from `arbitrage_signal`
  **Spec scenarios**: Signal Recording — "A cost/quota signal is recorded with vendor labels"
  **Design decisions**: D2
  **Dependencies**: 2.2
- [ ] 2.4 Checkpoint: run coordinator unit tests, review diff, verify scope
- [ ] 2.5 Write tests for the kill-switch flag `ARBITRAGE_INSTRUMENT_ENABLED` — default off no-ops recording + telemetry
  **Spec scenarios**: Single Kill Switch — "Disabling the instrument restores default dispatch"
  **Design decisions**: D7
  **Dependencies**: 2.1
- [ ] 2.6 Implement the feature-flag gate in `arbitrage_signal` and a shared `is_enabled()` helper
  **Spec scenarios**: Single Kill Switch
  **Design decisions**: D7
  **Dependencies**: 2.5
- [ ] 2.7 Write tests for Cedar eligibility — programmatic-ineligible vendor rejected; eligibility change takes effect without restart
  **Spec scenarios**: Hard Feasibility Constraints — "A programmatic-ineligible vendor is rejected as a worker", "An eligibility change takes effect without redeploy"
  **Contracts**: contracts/config/vendor-pricing-eligibility.schema.json
  **Design decisions**: D4
  **Dependencies**: 1.2
- [ ] 2.8 Extend `cedar/schema.cedarschema` with Agent attributes `vendor` / `modality` / `data_residency` and add `forbid()` eligibility policies; wire attributes through `_build_entity` from policy context
  **Spec scenarios**: Hard Feasibility Constraints — both
  **Design decisions**: D4
  **Dependencies**: 2.7
- [ ] 2.9 Add eligibility values to `agents.yaml` / `agent_profiles.metadata` (mutable, NOTIFY-invalidated) — Claude lead-eligible/programmatic-ineligible; Codex/Gemini/opencode programmatic-eligible
  **Spec scenarios**: Hard Feasibility Constraints — "An eligibility change takes effect without redeploy"
  **Design decisions**: D4
  **Dependencies**: 2.8
- [ ] 2.10 Checkpoint: run coordinator unit + policy tests, review diff, verify scope

## Phase 3 — Scheduled probes (wp-probes)

- [ ] 3.1 Write tests for the ToS monitor — changed content hash emits a compliance signal; unchanged emits none
  **Spec scenarios**: ToS Monitor Probe — "A changed ToS clause emits a compliance signal"
  **Contracts**: contracts/events/arbitrage-signal.schema.json
  **Design decisions**: D6
  **Dependencies**: 2.2
- [ ] 3.2 Create `agent-coordinator/src/probes/tos_monitor.py` — fetch + hash + diff the configured automation-clause URLs; record signal on change
  **Spec scenarios**: ToS Monitor Probe
  **Design decisions**: D6
  **Dependencies**: 3.1
- [ ] 3.3 Write tests for the model canary — changed fingerprint emits a quality_drift signal
  **Spec scenarios**: Model Canary Probe — "A drifted model fingerprint emits a drift signal"
  **Design decisions**: D6
  **Dependencies**: 2.2
- [ ] 3.4 Create `agent-coordinator/src/probes/model_canary.py` — fixed prompt per model, fingerprint response, record signal on drift
  **Spec scenarios**: Model Canary Probe
  **Design decisions**: D6
  **Dependencies**: 3.3
- [ ] 3.5 Checkpoint: run probe tests, review diff, verify scope
- [ ] 3.6 Register both probes as `WatchdogService` periodic jobs; verify they do not schedule when the instrument flag is off
  **Spec scenarios**: Single Kill Switch — "Disabling the instrument restores default dispatch"
  **Design decisions**: D6, D7
  **Dependencies**: 3.2, 3.4

## Phase 4 — Router, ledger, tripwires, digest (wp-skill-router)

- [ ] 4.1 Write tests for the cost ledger — actual + counterfactual recorded; missing usage flagged estimated; headline metric with/without estimates
  **Spec scenarios**: Metered-Counterfactual Cost Ledger — "A ledger entry records actual and counterfactual cost", "Missing token usage is recorded as a labelled estimate"
  **Contracts**: contracts/events/cost-ledger-entry.schema.json, contracts/config/vendor-pricing-eligibility.schema.json
  **Design decisions**: D3, D5
  **Dependencies**: 1.2
- [ ] 4.2 Create `skills/vendor-arbitrage/scripts/ledger.py` + `eligibility.py` — load the versioned pricing/eligibility config; compute counterfactual; persist via `roadmap-runtime` `LearningEntry.vendor_notes`
  **Spec scenarios**: Metered-Counterfactual Cost Ledger — both
  **Design decisions**: D3, D5
  **Dependencies**: 4.1
- [ ] 4.3 Write tests for the static-priority router — cheapest eligible tier; spill on 429; provenance recorded; rejects infeasible
  **Spec scenarios**: Static-Priority Router — "Router prefers the cheapest eligible tier", "Router spills on rate-limit"; Hard Feasibility Constraints — "A programmatic-ineligible vendor is rejected as a worker"
  **Contracts**: contracts/events/router-decision.schema.json
  **Design decisions**: D8
  **Dependencies**: 1.2
- [ ] 4.4 Create `skills/vendor-arbitrage/scripts/router.py` — `select_assignment(work_unit, feasible_set)`; feasibility via coordinator `check_policy`; cheap-first + 429 spill + cohesion penalty; record decision provenance
  **Spec scenarios**: Static-Priority Router — both
  **Design decisions**: D8
  **Dependencies**: 4.3
- [ ] 4.5 Checkpoint: run skill tests, review diff, verify scope
- [ ] 4.6 Write tests for tripwires — ToS-diff freezes a vendor; economic-kill fires below maintenance threshold; each writes a learning entry
  **Spec scenarios**: Tripwires Flip System Posture — "A ToS-diff tripwire freezes dispatch", "An economic-kill tripwire fires when arbitrage stops paying"
  **Design decisions**: D9
  **Dependencies**: 4.1, 4.3
- [ ] 4.7 Create `skills/vendor-arbitrage/scripts/tripwires.py` — declarative thresholds; flip posture flag (vendor freeze) honoured by router feasibility; write learning entries
  **Spec scenarios**: Tripwires Flip System Posture — both
  **Design decisions**: D9
  **Dependencies**: 4.6
- [ ] 4.8 Write tests for the digest — reports net savings with/without estimates and lists fired tripwires
  **Spec scenarios**: Landscape Digest — "The digest reports the headline arbitrage metric"
  **Design decisions**: D3, D5
  **Dependencies**: 4.1
- [ ] 4.9 Create `skills/vendor-arbitrage/scripts/digest.py` + `SKILL.md` — assemble the landscape report from the signal substrate
  **Spec scenarios**: Landscape Digest
  **Design decisions**: D3
  **Dependencies**: 4.8
- [ ] 4.10 Checkpoint: run skill tests, review diff, verify scope

## Phase 5 — Integration & spec coordination (wp-integration)

- [ ] 5.1 Write an end-to-end test: feature-flag off ⇒ dispatch identical to baseline; flag on ⇒ a routed unit produces a ledger entry, a provenance signal, and an OTel measurement
  **Spec scenarios**: Single Kill Switch — "Disabling the instrument restores default dispatch"; Signal Recording — all
  **Design decisions**: D1, D7
  **Dependencies**: 3.6, 4.4, 4.9
- [ ] 5.2 Cross-reference the new spec: mark the `observability` cost requirement fulfilled and the `symphony` `token-rate-limit-and-run-accounting` item subsumed (notes only, no duplication)
  **Design decisions**: D11
  **Dependencies**: 5.1
- [ ] 5.3 Wire the `vendor-arbitrage` skill into `skills/install.sh` sync and add the kill-switch flag to docs
  **Spec scenarios**: Single Kill Switch
  **Design decisions**: D1, D7
  **Dependencies**: 5.1
- [ ] 5.4 Checkpoint: run full suite (coordinator + skills), `openspec validate --strict`, review cumulative diff, verify no scope creep
