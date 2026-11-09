# Plan Findings: add-local-agent-probe

Produced by `/iterate-on-plan` (autopilot PLAN_ITERATE, architect archetype). Threshold: medium.

## Iteration 1

Baseline: `openspec validate --strict` passed; work-packages validator VALID.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency | high | `config_fingerprint` was "sha256 of the canonical-JSON `cli` block", but the sources serialize differently: `get_dispatch_configs()` emits the `CliConfig` dataclass with defaults filled in (`model_flag: "-m"`, `prompt_via_stdin: false`), local `agents.yaml` is raw. If the writer (`install.sh --check`, local yaml) and the reader (`discover_reviewers`, HTTP) use different sources, every entry looks stale and the filter never fires. | D4: fingerprint over a normalized projection with defaults applied (`command`, mode args, `*_flag`, `probe`), excluding model lists. Spec scenarios: identical across sources; model-list edit keeps entry fresh. New task 6.1 runs the end-to-end check against the real `agents.yaml`. |
| 2 | completeness | high | `review_dispatcher` has its own mirror `CliConfig` (`:558`) whose loader (`:~2571`) drops unknown keys, so `probe` would be lost before the dispatcher fingerprints or filters. Not listed in Impact. | D1 + Impact: mirror `CliConfig` gains `probe`; task 3.4 adds it; 3.3 asserts it survives loading. |
| 3 | completeness | high | Runtime write-back (D6) put `runtime_failure` inside a `lanes` entry, which requires L0/L1/L2 data. The dispatcher has no such data when no probe has run, and the record would be wiped by any fingerprint change even though the failure belongs to the account. | Cache schema: top-level `runtime_failures` map keyed by agent_id, fresh by TTL only. Contract test fixtures updated (1.1). |
| 4 | completeness | high | The dispatcher dispatches lanes concurrently (`ThreadPoolExecutor`, `:3181`) and reviews can run in parallel. Using `os.replace` alone prevents torn files but loses concurrent updates. | D4: read-modify-write under `threading.Lock` plus `fcntl.flock` on a sibling lock file (best-effort where fcntl is absent). Scenario: concurrent writers do not lose updates. |
| 5 | consistency | medium | `auth_ok` cleared both runtime classes, but `vendor_unavailable` is the billing/credits class (`_UNAVAILABLE_PATTERNS`, HTTP 402), which a token-free probe cannot observe. | D6: `vendor_unavailable` clears only by TTL. New scenario added. |
| 6 | feasibility/consistency | medium | NFR "total ≤ 15 s" contradicts sequential 10 s subprocesses within a lane (version + N help + auth). | D10: dedupe help argv, 25 s per-lane deadline (unrun tiers → `probe_timeout`). NFR is now ≤ 30 s. Task 2.1 asserts it. |
| 7 | completeness | medium | The watchdog calls `check_all_vendors()` synchronously inside an async method every 5 min. With new tiers, each cycle would spawn auth-status commands and could block the coordinator's event loop. | New D11 (who re-probes vs reuses): the watchdog reuses fresh entries and runs via `asyncio.to_thread`. `watchdog.py` added to Impact and to wp-dispatch scope. Scenario added. |
| 8 | completeness | medium | Missing failure-path scenarios: version command fails, auth command hangs, cache unwritable during dispatch. | Three scenarios added; write-back is best-effort with an unchanged `ReviewResult`. |
| 9 | clarity | medium | vendor-ux said existing fields "keep their meaning", but `dispatch_modes` was narrowed to modes that pass L1. | Narrowing stated explicitly, with the no-probe-block equivalence. |
| 10 | clarity | medium | The way `vendor_health` imports `vendor_probe` under the watchdog's by-path load was not specified. A plain `import` fails, and an unregistered module breaks `@dataclass` (#643). | D1: load the sibling by path and register it in `sys.modules` before `exec_module`. |
| 11 | testability | low | The ≤ 50 ms timing assertion would be flaky. | NFR is now verified by "no subprocess started" plus a coarse bound. (Fixed opportunistically.) |
| 12 | parallelizability | low | Tasks 3.5 and 3.6 were declared parallel to 3.4, but all three edit `review_dispatcher.py`. | Explicit sequential deps 3.4 → 3.5 → 3.6 (same package, so no width lost). |

## Iteration 2

Re-scan after the edits found stale wording: proposal Approach 1 still said "keyed by … realpath + version" and "fingerprint folded into the cache key", and D5 named the old `runtime_failure` field. All of it is fixed. No new findings at or above medium.

Remaining (below threshold, not addressed):
- low: combined short flags (`-sread-only`) would not match the whole-token rule. Covered by `ignore_flags` / `help_args`, and no current lane uses that form.
- low: `$AGENTIC_PROBE_CACHE` may point anywhere the user can write. This is the same trust boundary as the user's own environment.
- low: cross-repo thrash under one `agent_id` (accepted, see design Risks).

## Parallelizability

Independent packages after wp-contracts: wp-probe-core and wp-config (width 2), then wp-dispatch and wp-install (width 2), then wp-integration. No two packages overlap in `write_allow`. Inside a package, tasks that share a file are sequential.
