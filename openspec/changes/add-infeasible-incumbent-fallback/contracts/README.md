# Contracts: add-infeasible-incumbent-fallback

| Sub-type | File | Status |
|---|---|---|
| OpenAPI | `openapi/v1.4.yaml` | Self-contained overlay of v1.3 (`split-no-evidence-retention-reason`). Differences from v1.3, and nothing else: (1) the retention reason `incumbent-infeasible-configured-fallback` (`retained: false`: outside the kept-reasons conditional and outside the null-selected set); (2) the `Retention.fallback` object (`incumbent_exclusion_reasons`: sorted unique transient reasons, `minItems: 1`; `order_applied`), required when the reason is the configured fallback and forbidden otherwise (`allOf` if/then/else); (3) `ExcludedAssignment.reason` pattern widened to the `cost-policy:` prefix that `api.py` already emits (`cost-policy:unclassified`, `cost-policy:lower-priority-tier`) — a drift carried since v1.2, fixed here because v1.4 supersedes. |
| Events / persistence | `events/routing-decision-record.schema.json` | v1.3 decision record with differences (1) and (2); `$id`/title bumped to v1.4. |
| Generated types | `generated/models.py` | v1.3 models plus `TransientExclusionReason`, `FallbackOrderApplied`, `RetentionFallback` (sorted-unique validator) and `Retention.fallback` with the presence validator. |
| Database | none | `routing_decisions.retention` is JSONB with no CHECK on its contents (migration 044), so the new reason and `fallback` record need no migration (design D6). |
| Config | `agent-coordinator/routing.yaml` `fallback.vendor_order` | Not a wire contract. `FallbackOrder.vendor_order: list[str] \| None` — absent disables the fallback (design D5); when present, non-empty with unique agent-type entries, which the client loader checks against `agents.yaml`. The shipped file keeps the key absent with a commented example. |

v1.3 exists until merge only on `origin/openspec/split-no-evidence-retention-reason`; this overlay was
derived from it at commit `e832cff5`. Task 2.0 asserts v1.3 is merged (present under
`openspec/changes/`) and, if its SHA moved, regenerates v1.4 from it and confirms the diff is only the
differences listed above. The response's top-level `fallback: bool` keeps its v1.2 meaning (offline
local-static route) and stays `false` for a configured fallback. Tests locate these files with
`change_dir()`.
