# Tasks — add-frontier-model-tier

Small change, applied directly in one pass (no work packages).

- [x] 1.1 Add `OPTIONAL_MODEL_TIERS` / `ALL_MODEL_TIERS`, accept `frontier` in the archetype
  `model` and `escalation.escalate_to` enums and the `model_aliases` per-provider schema
  (optional property, base tiers stay required), and bump `DEFAULT_PROVIDER_MODEL_MAP` to
  `schema_version: 2` with `frontier` for `claude_code` (`fable`) and `codex`
  (`gpt-5.6-sol`) (S)
- [x] 1.2 `resolve_provider_model`: resolve optional tiers; fall back to the provider's
  `premium` model when an optional tier is unmapped; raise only when premium is also
  missing (S)
- [x] 1.3 `archetypes.yaml`: add `frontier` aliases; set `architect` to `model: frontier` (XS)
- [x] 1.4 `provider_dispatch.py`: add `fable` to `_CLAUDE_ALIASES` (XS)
- [x] 1.5 Create `openspec/schemas/provider-model-map.schema.json` (stable home, v2, optional
  frontier, provider key set open) (S)
- [x] 1.6 Repair + repoint `skills/tests/vendor-neutral-autopilot`: schema path → stable home,
  `phase-dispatch-contract.md` → archive path, `write_capable` fixture fix; add frontier
  coverage (accepts/optional/fallback/raises, default-map conformance) (M)
- [x] 1.7 Coordinator-side tests: real `archetypes.yaml` resolves PLAN → `fable` /
  `gpt-5.6-sol` / gemini-premium-fallback; IMPLEMENT stays `sonnet` (S)
- [x] 1.8 Verify: coordinator suite, vendor-neutral-autopilot + autopilot skills suites,
  `ruff` + `mypy --strict` on `agents_config.py`, `openspec validate --strict` (S)

## Refinement — thinking-level-aware tiers (operator direction, 2026-07-22)

- [x] 2.1 Tier entries accept `{model, thinking}` objects alongside bare strings
  (`_TIER_VALUE_SCHEMA`, stable schema `$defs/tierEntry`); `ModelSpec` dataclass;
  `resolve_provider_model_spec` carries thinking through resolution and fallback;
  `ResolvedArchetype.thinking` + endpoint field added additively (S)
- [x] 2.2 Roster refresh: codex `gpt-5.6-sol@xhigh` / `gpt-5.6-sol@medium` /
  `gpt-5.6-terra` / `gpt-5.6-luna`; gemini `gemini-3.6-flash` / `gemini-3.6-flash-lite` (XS)
- [x] 2.3 Tests derive expectations from the configured map — no model-id literals in
  assertions (vendor-neutral-autopilot, test_archetypes_yaml, test_audit_capability_gaps) (S)
- [ ] 2.4 Follow-up (dispatch plumbing): translate `thinking` to vendor flags at the CLI
  adapter boundary (codex `model_reasoning_effort`, grok thinking budget, claude effort) —
  belongs with the harness/dispatch work, not this change
- [ ] 2.5 Follow-up (model selection): consult the OpenRouter Pareto (cost vs performance)
  data when choosing pi/OpenRouter tier models (operator direction: Kimi 3 frontier
  candidate); feed cost-per-successful-task tuning via the vendor effectiveness memory loop
