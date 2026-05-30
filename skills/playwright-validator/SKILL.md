---
name: playwright-validator
description: Drive a deployed frontend via Playwright using OpenSpec WHEN/THEN scenarios; emit behavioral_failure findings.
category: Validation
tags: [validation, playwright, frontend, behavioral, gen-eval, openspec]
triggers:
  - "playwright validator"
  - "playwright validate"
  - "validate frontend"
  - "playwright-validator"
  - "frontend behavioral"
---

# Playwright Validator

Behavioral validator for frontend surfaces. Reads OpenSpec scenarios
(`openspec/changes/<id>/specs/**/*.md`) and a frontend descriptor
(`evaluation/descriptors/<id>.yaml`), generates Playwright
TypeScript test files, executes them with `npx playwright test --reporter=json`,
and emits `findings-playwright.json` conforming to
`openspec/schemas/review-findings.schema.json`.

This is the **peer skill** chosen in design D2 of
`factory-missions-architecture-alignment` — packaged separately from
`packages/gen-eval/` so its Node/browser-binary
dependencies don't bleed into the gen-eval Python runtime.

## When to use

* You have a frontend at a URL (or a static fixture) and an OpenSpec change
  with `#### Scenario:` blocks describing click-and-assert flows.
* You want behavioral evidence (deployed-system behavior) to feed into
  `consensus_synthesizer` alongside scrutiny reviewer findings.
* `validate-feature --phase gen-eval` auto-detects a `frontend-descriptor`
  and dispatches here.

For HTTP/MCP API surfaces, use `/gen-eval` instead — that path remains the
non-frontend dispatch target.

## Arguments

`$ARGUMENTS` — at minimum, the change-id:

* `<change-id>` (required, `^[a-zA-Z0-9_-]+$`) — OpenSpec change identifier.
* `--descriptor PATH` — path to frontend-descriptor YAML (default:
  `evaluation/descriptors/<change-id>.yaml`).
* `--specs-dir PATH` — override OpenSpec specs directory.
* `--output-dir PATH` — where `findings-playwright.json` is written
  (default: `openspec/changes/<change-id>/`).
* `--test-dir PATH` — where the generated `.spec.ts` files land
  (default: `skills/playwright-validator/test-results/generated/<change-id>/`).
* `--browsers chromium [firefox webkit]` — override descriptor's matrix.
* `--dry-run` — emit the `.spec.ts` but do not invoke `npx playwright test`.

## Invocation

Direct (Python):

```bash
skills/.venv/bin/python skills/playwright-validator/scripts/cli.py <change-id>
```

Module form (after the skill is on `PYTHONPATH`):

```bash
python -m playwright_validator <change-id> [--descriptor PATH] [--output-dir PATH]
```

Dispatch shim (used by `validate-feature --phase gen-eval`):

```bash
bash skills/playwright-validator/scripts/dispatch.sh <change-id>
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | All scenarios passed |
| 1    | One or more Playwright tests failed; `findings-playwright.json` emitted |
| 2    | Pipeline error: missing descriptor, malformed YAML, missing env var |
| 64   | Invalid change-id (failed `^[a-zA-Z0-9_-]+$`) |
| 127  | Playwright CLI not on PATH; **no findings file** emitted |

## Auto-detection in validate-feature

`validate-feature --phase gen-eval` walks
`evaluation/descriptors/*.yaml` and routes each descriptor:

1. If the YAML validates against
   `contracts/frontend-descriptor.schema.json` → dispatch to this skill via
   `dispatch.sh`.
2. Otherwise → existing HTTP/MCP gen-eval path
   (`packages/gen-eval/`).

The detection predicate is `descriptor.is_frontend_descriptor(path)` from
`scripts/descriptor.py`.

## Findings output

Per `contracts/findings-vendor-source.md` and design D8, this skill
**always** writes to `findings-playwright.json` (never `findings-gen-eval.json`).
The two files coexist when both validators run on the same change.

Each finding:

* `type: "behavioral_failure"` (per design D3).
* `criticality: "high"` (default for failed Playwright assertions).
* `file_path` + `line_range` reference the **OpenSpec spec.md**, not the
  generated `.spec.ts` file (per the "Playwright findings trace to OpenSpec
  scenarios" spec scenario).
* `metadata.browser` — chromium / firefox / webkit (per the "Browser matrix"
  scenario).
* `metadata.scenario_id` — the OpenSpec scenario's name.

## Sample frontend (smoke test)

A minimal static HTML page is available at
`packages/gen-eval/tests/fixtures/sample-descriptor.yaml` (per design D7 —
package-shipped data). To exercise the full pipeline (requires Node + Playwright):

```bash
skills/.venv/bin/python skills/playwright-validator/scripts/cli.py \
    sample-frontend-demo \
    --descriptor packages/gen-eval/tests/fixtures/sample-descriptor.yaml \
    --specs-dir openspec/changes/sample-frontend-demo/specs
```

## Localhost-bind invariant (D7)

The descriptor schema's `lifecycle.bind_address` defaults to `127.0.0.1`.
The runner additionally inspects `lifecycle.startup_command` and refuses to
launch when `0.0.0.0` appears unless the operator explicitly set
`bind_address` to a non-localhost value.

## Auth-flow env vars

`auth_flow[].value` may reference `${VAR_NAME}` (regex `^[A-Z_][A-Z0-9_]*$`).
Substitution uses Python's `string.Template` — never shell expansion. A
missing env var causes the pipeline to abort **before any browser launches**
with the exact error:

```
auth_flow: required env var <VAR_NAME> not set
```

Operators can preflight by setting the optional `env_vars_required` list in
the descriptor; the validator checks it before the auth_flow walk.

## Testing

Unit + integration tests at `skills/tests/playwright-validator/`. Run:

```bash
skills/.venv/bin/python -m pytest skills/tests/playwright-validator/ -v
```

Tests that would invoke real `npx playwright` skip gracefully when the CLI
is unavailable (`pytest.skip("requires npx playwright")`).
