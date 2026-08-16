# Autopilot Provider Smoke

Use the provider smoke harness to verify autopilot's provider-neutral dispatch
path from a specific CLI/runtime without starting an expensive remote run.

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider codex --dry-run --json
```

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider antigravity --dry-run --json
```

The smoke builds an IMPLEMENT phase payload, resolves the provider-specific
model through the same archetype model map used by the coordinator, routes the
payload through the provider dispatch adapter in dry-run mode, and prints the
normalized result. For any non-Claude provider (Codex, Antigravity, Grok, Pi,
local), the smoke fails if `opus`, `sonnet`, or `haiku` would be passed as the
dispatch model.

To exercise the negative guard:

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider codex --dry-run --model opus --json
```

## Local provider

The `local` provider dispatches to an OpenAI-compatible endpoint (e.g. a
llama.cpp `llama-server`, vLLM, or Ollama instance on the GX10 host — see
`docs/proposals/magnitude-local-model-harness.md` for serving-stack selection):

```bash
skills/.venv/bin/python skills/autopilot/scripts/smoke_provider_dispatch.py \
  --provider local --dry-run --json
```

Real mode requires `LOCAL_INFERENCE_BASE_URL` (the base URL includes the API
version prefix, e.g. `http://gx10.local:8080/v1`; optional
`LOCAL_INFERENCE_API_KEY`, `LOCAL_INFERENCE_MAX_CONCURRENCY` default 4,
clamped to 64). To stay inside the archetype trust boundary (`runner`,
`analyst`, `documenter`, `validator` only), the `local` smoke builds an INIT
phase payload (archetype `runner`) rather than IMPLEMENT. Real mode requires a
resolver-confirmed permitted archetype and exits 2 without dispatching
otherwise; with the archetype confirmed and the endpoint unset or unreachable,
it reports the structured `fallback` degradation as its outcome instead of
hanging — the expected "provider inert" state, not a smoke failure. The
dispatch adapter independently refuses non-permitted archetypes
(defence-in-depth), and its concurrency cap is per-process, not host-level.
