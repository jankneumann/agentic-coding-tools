# Tasks: switch-pi-standard-to-ox-alpha

## 1. Spec

- [x] 1.1 Apply the `configuration` delta: the `pi` requirement states slug *form*
      and purpose, and no longer names `qwen/qwen3-coder` as the default.

## 2. Config

- [x] 2.1 `agent-coordinator/src/agents_config.py` — `DEFAULT_PROVIDER_MODEL_MAP`
      `providers.pi.standard` → `stealth/ox-alpha`. Update the adjacent comment,
      which currently reads "`standard` fixed to qwen/qwen3-coder by roadmap ri-01"
      — that statement becomes false and would otherwise mislead the next reader.
- [x] 2.2 `agent-coordinator/archetypes.yaml` — `model_tiers.pi.standard` →
      `stealth/ox-alpha`; update the comment on the same block for the same reason.
- [x] 2.3 `agent-coordinator/agents.yaml` — `pi-local.cli.model` →
      `stealth/ox-alpha`. Leave `model_fallbacks: ["qwen/qwen3-coder-flash"]`
      unchanged: the fallback must stay on a stable published slug so it survives
      the stealth model's retirement.
- [x] 2.4 Confirm `frontier`, `premium`, `economy` are untouched in both files.

## 3. Tests

- [x] 3.1 `test_pi_tiers_are_openrouter_slugs` — keep the per-tier
      `<publisher>/<model>` form assertion; remove the
      `pi["standard"] == "qwen/qwen3-coder"` literal and its comment, which cites
      a SHALL this change removes.
- [x] 3.2 Add a regression assertion that `model_fallbacks` for `pi-local`
      contains no `stealth/` slug — encoding task 2.3's reasoning as a test rather
      than a comment.
- [x] 3.3 `uv run pytest tests/test_agents_config.py` green in `agent-coordinator`.

## 4. Verification

- [x] 4.1 `openspec validate --strict switch-pi-standard-to-ox-alpha`.
- [x] 4.2 `make context-drift-gate` — confirms no generated artifact went stale.
      Editing `agents_config.py` (Python source the architecture analyzer parses)
      staled `docs/architecture-analysis/*`; remediated with `make architecture-refresh`
      and the regenerated artifacts are committed alongside. Verified the drift was
      caused by this change and not pre-existing: a clean worktree at origin/main
      reports `fresh` / exit 0.
- [ ] 4.3 Confirm `stealth/ox-alpha` resolves against the live OpenRouter model
      list before merge. **Blocked in-sandbox** (no egress to `openrouter.ai`);
      must be run by the operator:
      `curl -s https://openrouter.ai/api/v1/models | jq -r '.data[].id' | grep -x 'stealth/ox-alpha'`
