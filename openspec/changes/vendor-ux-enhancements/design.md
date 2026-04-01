# Design: Vendor UX Enhancements

**Change ID**: `vendor-ux-enhancements`

## Design Decisions

### D1: Adversarial mode is a prompt modification, not a new dispatch_mode

**Decision**: Adversarial review reuses the existing `review` dispatch mode unchanged. The only difference is the **prompt content** — the review skills prepend an adversarial framing prefix before passing the prompt to `review_dispatcher.py --mode review`. No changes to `agents.yaml`, `CliVendorAdapter`, or `ReviewOrchestrator`.

**Rationale**: The `dispatch_mode` in `agents.yaml` controls CLI args (e.g., `--print --allowedTools Read,Grep,Glob`). Adversarial review needs the same CLI args as standard review — it's read-only analysis with the same tools. The only difference is *what the prompt asks for*. Adding a new dispatch_mode would duplicate identical CLI configs across all vendors for zero benefit.

**Rejected alternatives**:
- New `adversarial` dispatch_mode in agents.yaml — duplicates `review` mode CLI args with no behavioral difference
- New finding type `adversarial_challenge` — requires schema migration and consensus synthesizer changes

### D2: Adversarial prompt prefix lives in the review skills, not the dispatcher

**Decision**: The adversarial prompt prefix is a constant in a shared location (e.g., `skills/parallel-infrastructure/scripts/adversarial_prompt.py` or inline in the skill SKILL.md). The review skills prepend it when `--adversarial` flag is set, then call the dispatcher normally.

**Rationale**: The dispatcher is a generic vendor routing engine — it shouldn't know about review strategies. The skills already construct the review prompt before passing it to the dispatcher. Adding the adversarial framing at the skill level keeps the dispatcher simple and strategy-agnostic.

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
┌─────────────────────────────────┐
│    agents.yaml                   │
│    (adds: quick dispatch_mode)   │
│    (adversarial: NO changes)     │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐     ┌─────────────────────────┐
│  review_dispatcher.py            │     │  vendor_health.py        │
│  (UNCHANGED for adversarial)     │     │  (new script)            │
│                                  │     │                          │
│  dispatch_and_wait(mode="review")│     │  check_all_vendors()     │
│  dispatch_and_wait(mode="quick") │     │  check_vendor(agent_id)  │
└──────────┬───────────────────────┘     │  CLI: --json output      │
           │                             └──────────┬──────────────┘
           ▼                                        │
┌─────────────────────────────────┐                 ▼
│ parallel-review-* skills         │     ┌─────────────────────────┐
│                                  │     │  WatchdogService         │
│  --adversarial flag              │     │                          │
│  → prepends adversarial prompt   │     │  + _check_vendor_health()│
│  → calls dispatcher with         │     │  + vendor.unavailable    │
│    mode="review" (unchanged)     │     │    event emission        │
└──────────────────────────────────┘     └──────────────────────────┘

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
