# Vendor structured-output probe table

Only rows with `result: verified` may change `agents.yaml` review-mode args.
Do not copy Grok's `--json-schema` onto another binary.

| Vendor | Flags probed | Probe date | Result | Wiring |
|--------|--------------|------------|--------|--------|
| grok | `--output-format json --json-schema <schema>` | 2026-07 (add-agy-grok-pi-harnesses E6) | verified | already in `agents.yaml` |
| claude_code | _unprobed_ | — | unprobed | none |
| codex | _unprobed_ | — | unprobed | none |
| antigravity | _unprobed_ | — | unprobed | none |
| pi | `--mode json` (NDJSON event stream; inner payload still free-form) | 2026-07 (E8) | absent (stream is not a findings schema) | none; phase 1 NDJSON unwrap stays |

Implementation task 4.1 fills the `unprobed` rows. If a probe fails, set
`result: absent` and leave wiring empty.
