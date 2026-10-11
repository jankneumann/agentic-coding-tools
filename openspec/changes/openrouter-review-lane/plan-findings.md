# Plan Findings: openrouter-review-lane

Produced by `/iterate-on-plan` (autopilot PLAN_ITERATE, architect archetype), 2026-10-11.
Threshold: medium. Baseline: `openspec validate --strict` passed, but the change was still
the plan-roadmap scaffold.

The analysis ran inline. This harness exposes no sub-agent (`Task`/`Agent`) tool, so the
parallel Explore analysts were not dispatched (recorded as a `skill-procedure-deviation`
decision in `session-log.md`).

## Iteration 1 — scaffold to plan

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | completeness | critical | `proposal.md` had no Why, What Changes, or Impact sections | Rewrote `proposal.md` with all three, plus Non-goals |
| 2 | consistency | critical | The spec delta sat under the placeholder capability `multiplayer-collaboration` (the guide capability), and the touched capabilities had no deltas | Removed the placeholder. Added deltas for `parallel-infrastructure`, `skill-workflow`, `supervise`, `model-routing` |
| 3 | testability | critical | Every scenario was "WHEN implemented THEN <outcome restated>", so none could be verified | Rewrote as concrete WHEN/THEN with injected transports, fixture values, and exact reasons and codes |
| 4 | feasibility | critical | `tasks.md` was a generic five-item checklist that traced to no requirement | Seven task groups with Files, Depends, TDD ordering, and a traceability table |
| 5 | consistency | high | The new behaviour duplicated existing requirements (Dispatchable Vendor Verification, OpenAI-Compatible Dispatcher Discovery, Honest Review Quorum, Execution Profile) instead of modifying them | Converted to MODIFIED deltas carrying the full requirement text |
| 6 | feasibility | high | The plan assumed an enforced spend ceiling. In fact `ROUTING_MONTHLY_CEILING_USD` is advisory and `LedgerService.record` has no caller | D4: budget checked during the probe (coordinator ceiling or key limit), a new `POST /routing/spend`, and a spool with replay |
| 7 | feasibility | high | API lanes are always `probe_unsupported`, so an OpenRouter lane could never verify | D3: authenticated zero-cost probe (`GET /key`, `GET /models`) |
| 8 | feasibility | high | `agent_lane.py` hard-codes a single lane, so cloud `converge()` cannot reach quorum 2 | D7: `CompositeOrchestrator` with `--verified-lanes` |
| 9 | correctness | high | Lane identity: `converge()` keys results by `vendor`. Two lanes sharing one id would collide, and an Anthropic-family OpenRouter model would fake diversity | D1 lane id = `type`; D2 family rule (reject `anthropic`, skip duplicate families) |
| 10 | security | high | An HTTP lane cannot read files. An overflowing packet would give a blinded "no findings" vote (the `pi --no-tools` precedent) | D6: refuse with `packet_requires_tools`; the blinded-review floor applies |
| 11 | performance | medium | Adding a metered lane to the shared roster would make every host review pay OpenRouter | D5: metered lanes fill quorum only (`fill_target`) |
| 12 | consistency | medium | Supervisor `rank()` infers the endpoint kind from `probe_unsupported`, which is wrong once API lanes verify | D8: additive `lane_kinds` in the report, with a fallback |
| 13 | completeness | medium | A mid-run budget or auth loss returned `quorum_lost`, which contradicts "parks with capability_unavailable" | Honest Review Quorum MODIFIED: mapping for `vendor_unavailable` and `auth_required` |
| 14 | scope | medium | Overlap with the draft changes `add-coordinator-llm-gateway` and `add-model-usage-ledger` | Explicit non-goals. Writes only the existing `routing_spend_ledger` |
| 15 | completeness | medium | Retiring the policy had no evidence gate, so TRUST_POSTURE could be edited before the lane worked | D9 plus a guard test that requires `evidence/cloud-quorum-run.md` |
| 16 | consistency | medium | D1 initially gave the agent an `api_key_env` field, which the agent schema rejects (`additionalProperties: false`) | Removed it; the dispatcher's `OPENROUTER_API_KEY` default for `openrouter` covers it |

## Iteration 2 — self-review of the rewritten plan

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | clarity | medium | `local` API lanes had no verification rule once budget conditions were added | Spec: a `local` lane verifies on probe success alone |
| 2 | assumptions | medium | `review_reservation_usd` had no default | D4: default `1.00`, kept as data |
| 3 | completeness | medium | `claude_code` verification inside `agent_lane` was left implicit, and the failure mode of a missing `claude` binary was not covered | D7: the running agent is always verified; risk row added |
| 4 | assumptions | medium | Supervisor and worker environment classes can differ (inherited from ri-21) | Risk row added; out of scope with the reason stated |

## Iteration 3 — settle check

No finding at or above medium remains. Residual findings below the threshold:

| # | Type | Criticality | Description | Disposition |
|---|------|-------------|-------------|-------------|
| 1 | parallelizability | low | No `work-packages.yaml`. Dependencies and write scopes are in `tasks.md` only | Generate it at `/implement-feature` if the coordinated tier is selected |
| 2 | security | low | Any agent holding a coordinator API key can post spend rows, which could exhaust the ceiling and deny the lane | Accepted. The route is authenticated and audited, and the harm is denial of a metered lane only |
| 3 | assumptions | low | Three operator choices carry defaults rather than confirmed answers (design "Open questions"). An interactive AskUserQuestion is not available to a phase sub-agent | Surfaced in the handoff for the operator. Every default fails closed or saves cost |
| 4 | performance | low | The probe adds up to two HTTP calls (≤ 10 s each) per `--check-vendors` run | Accepted. It runs once per batch, and API lanes probe only for mode `review` |

## Parallelizability

Independent: 3 groups (1, 2, 4) | Sequential chains: 1 (→3→{5,6}→7) | Max parallel width: 3.
File overlap: `review_dispatcher.py` (groups 1 and 3, ordered by dependency; group 1 owns only
the `ReviewResult` fields), `review_quorum_policy.json` (groups 3 and 7, ordered),
`skills/autopilot/SKILL.md` (groups 6 and 7, ordered). No two independent groups share a file.
