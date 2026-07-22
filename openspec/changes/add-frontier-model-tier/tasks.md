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
