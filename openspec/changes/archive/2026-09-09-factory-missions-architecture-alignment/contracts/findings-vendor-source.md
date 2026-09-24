# Findings Vendor-Source Convention

## File naming

Each vendor (or behavioral validator) emitting findings into the consensus surface MUST write its output to a file named:

```
findings-<vendor>.json
```

at the path `<output-dir>/findings-<vendor>.json` where `<output-dir>` is the consensus synthesizer's input directory (typically `openspec/changes/<change-id>/`).

**Reserved vendor names** (for current implementations):
- `findings-claude.json` — scrutiny review by Claude
- `findings-codex.json` — scrutiny review by Codex
- `findings-gemini.json` — scrutiny review by Gemini
- `findings-gen-eval.json` — behavioral findings from gen-eval (HTTP/MCP/CLI)
- `findings-playwright.json` — behavioral findings from Playwright validator (frontend)

## Schema conformance

Every `findings-<vendor>.json` file MUST validate against `openspec/schemas/review-findings.schema.json`. Schema-non-conformant files MUST be rejected by `consensus_synthesizer.py` with a clear error naming the failing field.

## Type-enum routing

The schema's `type` enum distinguishes finding categories:

| Type | Source | Semantics |
|---|---|---|
| `correctness`, `security`, `performance`, `style`, `architecture`, `compatibility`, `resilience`, `observability` | Scrutiny reviewers | Hypotheses derived from reading code |
| `spec_gap`, `contract_mismatch` | Scrutiny reviewers | Findings about plan-implementation alignment |
| `behavioral_failure` | Behavioral validators (gen-eval, Playwright) | Evidence of deployed system behaving wrong |

Consumers (e.g., `cleanup-feature` merge gates) MAY filter or route by type. Severity is comparable across all types.

## Required vs optional metadata

Required fields per schema: `severity`, `description`, `location`, `type`.

Recommended optional metadata for behavioral findings:
- `metadata.browser` — for Playwright findings (e.g., `chromium`, `firefox`, `webkit`)
- `metadata.scenario_id` — gen-eval's scenario identifier
- `metadata.run_id` — for cross-referencing with gen-eval/Playwright run logs

The `location` field for behavioral findings sourced from OpenSpec scenarios MUST point at the originating spec file, not the gen-eval scenario YAML — see `gen-eval-cli.md` for the source-tracking convention.

## Synthesizer behavior

`consensus_synthesizer.py` MUST:

1. Discover all `findings-<vendor>.json` files in the input directory.
2. Validate each against the schema; abort with non-zero exit on schema violation.
3. Treat absence of any individual file as not-an-error (some vendors may legitimately not have run).
4. Merge all findings into a single ranked output, deduplicating where two findings have matching `location` + `type` (treat as cross-vendor confirmation, raise consensus score).
5. Emit `consensus.json` (existing convention) and log per-vendor counts: `merged: claude=N, codex=M, gen-eval=K, ...`.

The synthesizer MUST NOT introduce different ranking logic for behavioral vs scrutiny findings. Severity is the canonical ranking key.
