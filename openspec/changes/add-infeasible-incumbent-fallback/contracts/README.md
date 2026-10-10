# Contracts: add-infeasible-incumbent-fallback

| Sub-type | File | Status |
|---|---|---|
| OpenAPI | `openapi/v1.4.yaml` | Self-contained overlay of v1.3 (`split-no-evidence-retention-reason`). Differences from v1.3, and nothing else: (1) the retention reason `incumbent-infeasible-configured-fallback` (`retained: false`: outside the kept-reasons conditional and outside the null-selected set), plus a `SelectModelResponse` conditional that this reason implies `selected` is an object and top-level `fallback` is `false`; (2) the `Retention.fallback` object (`incumbent_exclusion_reasons`: unique transient reasons, `minItems: 1`, emitted sorted by the producer; `order_applied`: verbatim copy of the policy's `fallback:` block, all four lists required, non-empty, unique), required when the reason is the configured fallback and forbidden otherwise (`allOf` if/then/else); (3) `ExcludedAssignment.reason` pattern widened to the `cost-policy:` prefix that `api.py` already emits (`cost-policy:unclassified`, `cost-policy:lower-priority-tier`) — a drift carried since v1.2, fixed here because v1.4 supersedes. |
| Events / persistence | `events/routing-decision-record.schema.json` | v1.3 decision record with differences (1) and (2) (the record's top-level `fallback` is already `const: false`); `$id`/title bumped to v1.4. |
| Generated types | `generated/models.py` | v1.3 models plus `TransientExclusionReason`, `FallbackOrderApplied` (all four lists, unique validator), `RetentionFallback` (unique validator) and `Retention` with `retained`/`reason` parity and the `fallback` presence validator (explicit `null` counts as present). Sortedness of `incumbent_exclusion_reasons` is a producer invariant, not validated by any of the three contracts. |
| Database | none | `routing_decisions.retention` is JSONB with no CHECK on its contents (migration 044), so the new reason and `fallback` record need no migration (design D6). |
| Config | `agent-coordinator/routing.yaml` `fallback.vendor_order` | Not a wire contract. `FallbackOrder.vendor_order: list[str] \| None` — absent disables the fallback (design D5); when present, non-empty with unique agent-type entries, which the client loader checks against `agents.yaml`. The shipped file keeps the key absent with a commented example. |

v1.3 exists until merge only on `origin/openspec/split-no-evidence-retention-reason`; this overlay was
derived from it at commit `e832cff5`. Because a squash merge keeps blob hashes but not commit SHAs, the
v1.3 inputs are pinned by `git hash-object` blob id:

| v1.3 file | blob |
|---|---|
| `contracts/openapi/v1.3.yaml` | `3305df4d5e80907acca687511a9aced015c2d6c8` |
| `contracts/events/routing-decision-record.schema.json` | `009d212cbd8fdafa2974cfaace60b1babb4bca37` |
| `contracts/generated/models.py` | `a81117ce979ce3bb8908edc570746295ae866780` |

Task 2.0 resolves the merged v1.3 change with `change_dir()` (active or archived), compares these blobs,
and, if any differs, regenerates v1.4 from the merged v1.3 and confirms the diff is only the differences
listed above. The response's top-level `fallback: bool` keeps its v1.2 meaning (offline
local-static route) and stays `false` for a configured fallback. Tests locate these files with
`change_dir()`.
