# Vendor dispatch capabilities

This matrix describes the result-channel guarantees used by
`review_dispatcher.py`. It records observed CLI behavior, not aspirational
vendor features.

## Result protocol

Synchronous review commands must return structured findings through a
vendor-supported JSON or JSON-stream mode. Asynchronous commands must emit the
versioned `VendorResultEnvelope` documented by
`build-structured-vendor-result-channel`. The dispatcher does not infer task
ids or completion from prose.

For async work, the coordinator queue is authoritative:

1. `submit_work` and an exact-task claim succeed before vendor launch;
2. structured vendor status is harvested;
3. `complete_work` persists the terminal envelope; and
4. only then are findings returned to review convergence.

## Capability matrix

| Lane | CLI structured review | Async CLI envelope | SDK modes | Effective fallback |
| --- | --- | --- | --- | --- |
| `claude-local` | Yes: print mode plus JSON Schema | Not configured | n/a | Local CLI review, alternative, quick |
| `claude-remote` | Yes: synchronous remote print plus JSON Schema | Not advertised: background/resume status is text-only in the installed CLI | `review` only (Anthropic SDK) | CLI or SDK review; no SDK alternative/quick |
| `codex-local` | Yes: prompt-contracted JSON parsed strictly | Not configured | n/a | Local CLI review, alternative, quick |
| `codex-remote` | No live CLI lane: installed `codex cloud exec/status` exposes no JSON status option | Not advertised | `review` only (OpenAI SDK) | SDK review; no alternative/quick |
| `antigravity-local` | Yes: print JSON response envelope | Not configured | none | CLI only |
| `grok-local` | Yes: `--output-format json` plus canonical JSON Schema | Not configured | none | CLI only |
| `pi-local` | Yes: NDJSON event stream with final assistant payload | Not configured | none | CLI only |
| `ocr-local` | Yes: local adapter JSON | Not configured | none | CLI only |

The remote async rows are deliberately absent from `agents.yaml`. Adding one
requires a verified command or trusted wrapper that emits
`vendor-envelope-v1` for both submission and status. A text-only command must
not be enabled with a regex compatibility parser.

## SDK boundary

`SdkVendorAdapter.can_dispatch()` and `dispatch()` accept only `review`.
Unsupported modes are rejected before API-key resolution and before invoking a
vendor SDK. This keeps a missing CLI from silently widening a read-only SDK
fallback into an implementation channel.

## Operator diagnosis

- `Invalid structured async submission`: the launch command returned data
  that is not a version-1 envelope.
- `Invalid structured async status`: a status response was malformed or
  changed shape.
- `Completion ledger submission failed`: no remote command was started.
- `Completion ledger update failed before result consumption`: the vendor
  finished, but the terminal record was not durable, so the result was withheld.
