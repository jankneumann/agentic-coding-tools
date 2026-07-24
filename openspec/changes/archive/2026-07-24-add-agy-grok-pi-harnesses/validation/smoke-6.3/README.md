# Task 6.3 — Live smoke dispatch evidence (2026-07-24)

Operator-authorized, billed. One review-mode dispatch per new vendor; all returned a
parseable result envelope. Raw outputs saved alongside.

| Vendor | Command (review mode, from agents.yaml) | Result | Envelope |
|---|---|---|---|
| grok | `printf '%s' <prompt> \| grok -m grok-4.5 --prompt-file /dev/stdin --output-format json` | exit 0, `text="SMOKE-OK-GROK"`, cost $0.008 | JSON; `.text` (no `.structuredOutput` w/o schema — confirms E6 fallback) |
| antigravity | `agy --model gemini-3.6-flash-medium --prompt <prompt> --mode plan` | exit 0, stdout `SMOKE-OK-AGY` | plain Claude-shaped stdout (confirms E7) |
| pi | `pi --model qwen/qwen3-coder -p --provider openrouter --mode json --no-tools <prompt>` | exit 0, `SMOKE-OK-PI` | NDJSON stream (see pi_out.txt) |

## Ground-truth outcome
pi's real NDJSON (pi_out.txt) disproved the eval-backend's nested-`agent_end` assumption:
one `message_end` per message, each with `role`, prompt echoed as `role:user`. This
resolved the IMPL_ITERATE finding — pi.py fixed to take the last assistant message
(commit 6219477c, issue 035ffd93). A separate usage-accounting follow-up remains on
that issue (usage nested in `message.usage`, keys input/output/totalTokens).

Note: `--dry-run` dispatch smoke also passed for all three; the deployed coordinator
(coord.rotkohl.ai) returns HTTP 500 on archetype resolution for the new providers
because it runs pre-merge code without this change's archetypes.yaml — expected until ship.
