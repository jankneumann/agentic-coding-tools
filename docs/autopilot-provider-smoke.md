# Autopilot Provider Smoke

Use the provider smoke harness to verify autopilot's provider-neutral dispatch
path from a specific CLI/runtime without starting an expensive remote run.

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider codex --dry-run --json
```

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider gemini --dry-run --json
```

The smoke builds an IMPLEMENT phase payload, resolves the provider-specific
model through the same archetype model map used by the coordinator, routes the
payload through the provider dispatch adapter in dry-run mode, and prints the
normalized result. For Codex and Gemini, the smoke fails if `opus`, `sonnet`,
or `haiku` would be passed as the dispatch model.

To exercise the negative guard:

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider codex --dry-run --model opus --json
```
