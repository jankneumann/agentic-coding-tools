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

## Local sandbox operations

The local sandbox lane is backed by `@anthropic-ai/sandbox-runtime` 0.0.77. Install
the pinned runtime with `npm ci --ignore-scripts --prefix tools/sandbox-runtime`;
Linux also needs `bubblewrap`, `socat`, `rg`, usable unprivileged user namespaces,
and an AppArmor posture that permits them. macOS needs `/usr/bin/sandbox-exec`,
`socat`, and `rg`. Run the controlled probe with:

```bash
skills/.venv/bin/python -m pytest \
  skills/shared/tests/test_sandbox_profile_integration.py -q -rs
```

A skip is not rollout evidence. Its message names the missing prerequisites. The
authoritative Linux and macOS gate is `.github/workflows/sandbox-runtime.yml`; after
the branch is pushed, verify its exact head SHA and downloaded artifacts with:

```bash
skills/.venv/bin/python skills/shared/verify_sandbox_runtime_evidence.py \
  --workflow-path .github/workflows/sandbox-runtime.yml \
  --head-sha "$(git rev-parse HEAD)" \
  --require-platform linux --require-platform darwin
```

### Policy and endpoint inventory

Network policy is default-deny and exported for one exact enabled agent through
`GET /policies/network/export?agent_id=<agent-id>`. Author both global and
profile-scoped rules in the coordinator database; disabled, malformed, unassigned,
or unknown-agent policy never becomes a partial allowlist. Before enabling a lane,
inventory its API hostname, git remote, inference gateway, DNS behavior, proxy
compatibility, `api_key_env`, and `state_env_keys`. Wildcards cover subdomains only;
private/reserved resolved addresses remain denied. GitHub or any other broad allowed
domain is still an exfiltration channel.

### Rollout and recovery

Roll out one environment-authenticated read-only lane first. Require an applied
sandbox audit event, matching routing/policy/settings/endpoint digests, successful
controlled allowed egress, and denied private/DNS-resolved egress before expanding
to write-capable modes. A sandboxed writer edits only; the host validates and makes
the save-point commit.

Events are synchronously sent to `POST /dispatch/sandbox-events`. Transport and 5xx
failures enter the bounded operator-owned `outbox.jsonl`; permanent 4xx rejection
moves the record to `dead-letter.jsonl`. These files live in the configured audit
state root outside every checkout with directory mode 0700 and file mode 0600.
Inspect outbox telemetry, restore coordinator reachability or credentials, and call
the audit port's bounded drain. Do not delete a dead letter until its schema/auth
cause is understood and the event is durably recorded or explicitly waived.

If preflight, policy export, credential selection, settings materialization, or audit
delivery cannot prove the requested boundary, keep the lane rollout-ineligible.
Never recover by replaying the command unsandboxed. For `remote_state_unknown`, query
the vendor and coordinator ledger before retrying so still-running work is not
duplicated.

The threat claim is blast-radius reduction for confused or prompt-injected agents,
not multi-user or determined-adversary containment. Allowed destinations, supplied
leaf credentials, shared Git object reads, hardlinks, and same-user races remain
documented residuals.
