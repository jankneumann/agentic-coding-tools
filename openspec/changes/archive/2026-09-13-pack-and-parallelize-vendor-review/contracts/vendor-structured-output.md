# Vendor structured-output probe table

Only rows with `result: verified` may change `agents.yaml` review-mode args.
Do not copy Grok's `--json-schema` onto another binary.

| Vendor | Flags probed | Probe date | Result | Wiring |
|--------|--------------|------------|--------|--------|
| grok | `--output-format json --json-schema <schema>` | 2026-07 (add-agy-grok-pi-harnesses E6); re-probed 2026-09-12 | verified | already in `agents.yaml` (`--json-schema` `@review-findings-schema`) |
| claude_code | `--json-schema <schema>` (inline JSON; "JSON Schema for structured output validation"); `--output-format json` (CLI result envelope, not a findings schema) | 2026-09-12 | verified (`--json-schema`) | `claude-local` / `claude-remote` review args: `--json-schema` `@review-findings-schema` |
| codex | `codex exec --output-schema <FILE>` (schema file for final response shape); `codex exec --json` (JSONL events, not a schema); `codex review` / `codex cloud exec` (no schema flag) | 2026-09-12 | verified (`--output-schema` on `exec`) | none — flag takes a **file path**; dispatcher sentinel injects an inline JSON string. Do not copy `--json-schema`. Leave prompt-path until file-path injection exists. |
| antigravity | `--json-schema` (schema string or path "to enforce structured output"); `--output-format json` (print-mode envelope, not a findings schema) | 2026-09-12 | verified (`--json-schema`) | `antigravity-local` review args: `--json-schema` `@review-findings-schema` |
| pi | `--mode json` (NDJSON event stream; inner payload still free-form); `--json-schema` → `Unknown option` | 2026-07 (E8); re-probed 2026-09-12 | absent (stream is not a findings schema; no schema flag) | none; phase 1 NDJSON unwrap stays |

Implementation task 4.1 fills the `unprobed` rows. If a probe fails, set
`result: absent` and leave wiring empty.

## Probe notes (2026-09-12)

Method: `command --help` / subcommand `--help`, plus a no-model flag-parse check.
No live billed review was run. Binaries: `grok` 1.0.5, `claude` 2.1.268,
`codex` 0.150.1, `agy` 1.2.2, `pi` 0.84.3. Names `claude-code` and `antigravity`
are not on PATH; dispatch uses `claude` and `agy`.

- **grok** — `grok --help` still documents `--json-schema <SCHEMA>` ("the model
  is constrained to produce JSON matching this schema. Implies --output-format
  json"). Existing review args unchanged.
- **claude_code** — `claude --help` documents `--json-schema <schema>` with an
  inline JSON example. `claude --print --json-schema '{...}'` is accepted
  (fails only on missing prompt, not unknown-flag). `--output-format json`
  without a schema is not treated as verified.
- **codex** — `codex exec --help` documents `--output-schema <FILE>` as a JSON
  Schema file for the model's final response shape (schema-constraining) and
  `--json` as JSONL events. `codex review --help` and `codex cloud exec --help`
  have neither. Wiring `--output-schema @review-findings-schema` would pass a
  JSON blob as a filepath and break dispatch.
- **antigravity** — `agy --help` documents `--json-schema` as a schema string
  or path. Omitting the value errors `flag needs an argument: -json-schema`.
- **pi** — `pi --help` still lists `--mode json` as `text|json|rpc` only.
  `pi --json-schema` errors `Unknown option: --json-schema`.
