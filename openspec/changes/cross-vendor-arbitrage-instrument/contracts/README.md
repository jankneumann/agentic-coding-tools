# Contracts: cross-vendor-arbitrage-instrument

Because Approach A spans two codebases (the coordinator `arbitrage_signal`/probe module and the `vendor-arbitrage` skill), these schemas ARE the cross-codebase coordination boundary (design decision D10). Both sides validate against them; they are the only coupling.

## Contract sub-types evaluated

| Sub-type | Applicable? | Artifact |
|---|---|---|
| Event payloads | **Yes** | `events/arbitrage-signal.schema.json`, `events/cost-ledger-entry.schema.json`, `events/router-decision.schema.json` |
| Config | **Yes** | `config/vendor-pricing-eligibility.schema.json` (runtime-mutable pricing + eligibility, D4/D5) |
| OpenAPI (HTTP endpoints) | No new endpoints | Signals ride the existing `audit_log` write path (`AuditService.log_operation`); no new REST surface is introduced in this slice. If a dedicated signal-write endpoint proves necessary for HTTP-only (cloud) skill agents, it will be added as a follow-up and contracted then. |
| Database schema | No new tables | D2/D3: signals ride `audit_log`; interpretive records extend `roadmap-runtime` `LearningEntry.vendor_notes` / `checkpoint.vendor_state`. Cedar eligibility attributes extend the existing `cedar/schema.cedarschema` and `agent_profiles.metadata` (JSONB), not new tables. |
| Generated types | Deferred | Pydantic/TS stubs can be generated from the event schemas if a typed consumer needs them; not required for this slice. |

## Notes

- The `vendor-pricing-eligibility` config is intentionally a *contract* and not code: editing it must reorganise routing without a redeploy (D4). The `version` field is stamped onto every ledger entry for auditability.
- `router-decision.schema.json` pins `policy: "static-priority"` in this slice. The deferred smart router is required to populate the same schema with a different `policy` value, so the signal layer is unchanged when the optimiser slots in (D8).
