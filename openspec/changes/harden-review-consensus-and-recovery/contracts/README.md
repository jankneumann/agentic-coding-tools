# Contracts: harden-review-consensus-and-recovery

This change modifies internal JSON/Python boundaries rather than HTTP, database, or event interfaces. The frozen revision-1 coordination contracts are:

- `consensus-policy.schema.json` — normalized input/output contract for blocker and adjudication policy.
- `review-attempt.schema.json` — per-attempt diagnostics and routing provenance shared by CLI, SDK, async polling, manifests, and the future typed-result channel.

Production implementation remains authoritative in `openspec/schemas/consensus-report.schema.json`, its install-asset copy, and the dataclasses/config models in `review_dispatcher.py` and `agents_config.py`. Package implementations MUST keep production shapes compatible with these frozen contracts. No OpenAPI, SQL, generated language type, event, or mock contract applies.

Validate with:

```bash
uv run --project skills python -m json.tool openspec/changes/harden-review-consensus-and-recovery/contracts/consensus-policy.schema.json
uv run --project skills python -m json.tool openspec/changes/harden-review-consensus-and-recovery/contracts/review-attempt.schema.json
```
