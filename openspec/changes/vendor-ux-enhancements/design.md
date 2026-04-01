# Design: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## Design Decisions

### D1: Adversarial mode as a dispatch_mode, not a finding type

**Decision**: Add `adversarial` as a new `dispatch_mode` in `agents.yaml` CLI configs, alongside existing `review` and `alternative` modes. Do NOT add a new finding type to the schema.

**Rationale**: The review findings schema already has `architecture` and `correctness` types that cover adversarial findings semantically. What makes adversarial review different is the *prompt persona*, not the *output schema*. Adding it as a dispatch mode means:
- Each vendor's adversarial CLI args can differ (e.g., Claude might use `--print` with a different system prompt, Codex might use a different model)
- The consensus pipeline requires zero changes — adversarial findings are structurally identical to standard findings
- Equal-weight consensus naturally falls out: a confirmed finding needs 2+ vendors to agree regardless of which mode produced it

**Rejected alternative**: New finding type `adversarial_challenge`. This would require schema migration, consensus synthesizer changes, and downstream consumers to handle a new type. The prompt-level approach achieves the same effect with zero schema changes.

### D2: Adversarial prompt template lives in review_dispatcher.py

**Decision**: Add a `ADVERSARIAL_PROMPT_PREFIX` constant to `review_dispatcher.py` that wraps the standard review prompt with a contrarian persona. The dispatcher prepends this prefix when `--mode adversarial` is used.

**Rationale**: Prompts are already constructed in the dispatcher (it builds the full prompt string before passing to `CliVendorAdapter.dispatch()`). Adding adversarial framing at this layer means all vendors receive the same adversarial context, ensuring comparable findings for consensus matching.

### D3: Quick-task uses a new `quick` dispatch_mode

**Decision**: Add a `quick` dispatch mode to `agents.yaml` that uses read-write args (like `alternative`) but without worktree isolation. Create a new skill `/quick-task` with its own `SKILL.md`.

**Rationale**: The existing `alternative` mode is designed for work-package implementation within a worktree. Quick-task operates on the current working directory without isolation. A dedicated mode allows vendors to configure different args (e.g., fewer `--allowedTools` restrictions than full implementation, but more than read-only review).

**Rejected alternative**: Reuse `alternative` mode. This would conflate two different execution contexts (worktree-scoped implementation vs. ad-hoc current-directory tasks) and prevent vendors from configuring them independently.

### D4: Quick-task result format is freeform text, not structured JSON

**Decision**: Quick-task returns vendor stdout directly to the user, not parsed into a findings schema.

**Rationale**: Quick-task bypasses OpenSpec — there's no change-id, no spec to validate against, no consensus to synthesize. Forcing structured output would add complexity without a consumer. Users want to see the vendor's natural response (explanation, diff, investigation results).

### D5: Vendor health check as a standalone script + watchdog method

**Decision**: Implement health check as `skills/parallel-infrastructure/scripts/vendor_health.py` that can be invoked both as a CLI script and imported as a module by `WatchdogService`.

**Rationale**: Dual-use design:
- CLI invocation: `python3 vendor_health.py --json` — standalone, no coordinator needed, works offline
- Watchdog import: `from vendor_health import check_all_vendors` — called by `_check_vendor_health()` at watchdog interval
- The `/vendor:status` skill just shells out to the CLI script and formats output

### D6: Health probe uses `can_dispatch()` + dry-run model list, not actual inference

**Decision**: Health probes check CLI availability (`shutil.which`), API key resolution (`ApiKeyResolver`), and model listing (vendor-specific lightweight endpoint). They do NOT send inference requests.

**Rationale**: Inference probes cost money and add latency. `can_dispatch()` already checks CLI presence. API key validity can be tested with a lightweight endpoint (e.g., `GET /models` for OpenAI, `GET /v1/models` for Anthropic). This gives high confidence without cost.

### D7: Watchdog vendor health events use existing event bus channels

**Decision**: Vendor health events emit on the `coordinator_agent` channel with event type `vendor.unavailable` / `vendor.recovered`, urgency `medium`.

**Rationale**: The `coordinator_agent` channel already handles agent lifecycle events (stale, registered). Vendor availability is conceptually similar — it's an agent infrastructure concern. Using an existing channel avoids schema changes to the event bus.

## Component Interactions

```
┌──────────────────────────────────────────────────────┐
│                    agents.yaml                        │
│  (adds: adversarial + quick dispatch_modes per vendor)│
└──────────┬───────────────────────────┬────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────────┐
│  review_dispatcher   │    │   vendor_health.py       │
│  .py                 │    │   (new script)           │
│                      │    │                          │
│  + adversarial       │    │  check_all_vendors()     │
│    prompt prefix     │    │  check_vendor(agent_id)  │
│  + dispatch_and_wait │    │  CLI: --json output      │
│    (mode=adversarial)│    │                          │
└──────────┬───────────┘    └──────────┬──────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────────┐
│ parallel-review-*    │    │  WatchdogService         │
│ skills               │    │                          │
│                      │    │  + _check_vendor_health()│
│  --adversarial flag  │    │  + vendor.unavailable    │
│  dispatches with     │    │    event emission        │
│  mode=adversarial    │    │                          │
└──────────────────────┘    └──────────────────────────┘

┌──────────────────────────────────────────────────────┐
│              /quick-task skill (new)                   │
│                                                       │
│  Input: prompt + optional --vendor flag               │
│  Uses: ReviewOrchestrator.dispatch_and_wait()         │
│         with mode="quick"                             │
│  Output: vendor stdout (freeform text)                │
│  No OpenSpec artifacts created                        │
└──────────────────────────────────────────────────────┘
```
