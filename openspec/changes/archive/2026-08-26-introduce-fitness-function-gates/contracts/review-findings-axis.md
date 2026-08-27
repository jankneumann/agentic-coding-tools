# Contract: review-findings axis enum (v2)

The `axis` enum in `review-findings.schema.json` becomes, in this exact order:

```json
["correctness", "readability", "architecture", "security", "performance",
 "observability", "resilience", "compatibility"]
```

Rules all packages code against:

1. **Three copies, one value.** The enum is byte-identical in:
   - `openspec/schemas/review-findings.schema.json` (canonical)
   - `skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`
     (verified byte-identical to canonical as of wp-contracts)
   - `agent-coordinator/agents.yaml` inline `--json-schema` block — **the `axis` enum at
     line 289 only**. Line 285 is the separate `type` enum, which already carries
     `observability` / `compatibility` / `resilience` and MUST NOT be touched by this
     change.
   The wp-schema test suite asserts identity across all three; drift is a test failure.
2. **`axis` and `severity` remain required.** Producers (parallel-review skills,
   validate-feature linters, findings emitters) MUST emit both. Legacy migration
   defaults stay `axis: "correctness"`, `severity: "fyi"`.
3. **Consensus keys on axis.** Cross-vendor matching is
   `(axis, file_path, line_range-overlap)`. Same-line findings with different axes do
   not merge. `ConsensusFinding` carries `agreed_axis`.
4. **Severity enum is unchanged**: `["critical", "nit", "optional", "fyi", "none"]`.
