# Contracts: add-infeasible-incumbent-fallback

| Sub-type | File | Status |
|---|---|---|
| OpenAPI | `openapi/v1.4.yaml` | Self-contained overlay of v1.3 (`split-no-evidence-retention-reason`). Adds the retention reason `incumbent-infeasible-configured-fallback` (`retained: false`: outside the kept-reasons conditional and outside the null-selected set) and the optional `Retention.fallback` object (`incumbent_exclusion_reason`, `order_applied`). |
| Events / persistence | `events/routing-decision-record.schema.json` | v1.3 decision record with the same two additions. |
| Generated types | `generated/models.py` | v1.3 models plus `TransientExclusionReason`, `FallbackOrderApplied`, `RetentionFallback`, and `Retention.fallback`. |
| Database | none | `routing_decisions.retention` is JSONB with no CHECK on its contents (migration 044), so the new reason and `fallback` record need no migration (design D6). |
| Config | `agent-coordinator/routing.yaml` `fallback.vendor_order` | Not a wire contract. Validated by `RoutingPolicyDocument` (`FallbackOrder.vendor_order`); its absence disables the fallback (design D5). |

v1.4 is derived from v1.3, which exists until merge only on `origin/openspec/split-no-evidence-retention-reason`. If v1.3 changes before it merges, regenerate v1.4 from it: the additions above are the only differences. Tests locate these files with `change_dir()`.
