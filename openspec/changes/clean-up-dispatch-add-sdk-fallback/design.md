# Design: Clean Up Dispatch and Add SDK Fallback

## Decision 1: SDK Adapter Architecture

### Chosen: `SdkVendorAdapter` parallel to `CliVendorAdapter`

Add a new `SdkVendorAdapter` class that implements the same `dispatch()` → `ReviewResult` interface as `CliVendorAdapter`, but calls vendor APIs via their Python SDKs instead of subprocess CLI invocation.

**Alternatives considered:**

- **Unified adapter with CLI/SDK modes**: More complex, couples two very different dispatch mechanisms in one class. Rejected for violating single responsibility.
- **HTTP-based dispatch via coordinator**: Would require the coordinator to proxy API calls, adding latency and a single point of failure. Rejected — SDK dispatch should work standalone.

### SDK Adapter Design

```python
class SdkVendorAdapter:
    def __init__(self, agent_id, vendor, sdk_config, api_key_resolver):
        self.agent_id = agent_id
        self.vendor = vendor
        self.sdk_config = sdk_config
        self.api_key_resolver = api_key_resolver

    def can_dispatch(self, mode: str) -> bool:
        """Check if SDK package is importable and API key is resolvable."""

    def dispatch(self, mode, prompt, cwd, timeout_seconds) -> ReviewResult:
        """Call vendor API, parse JSON findings from response."""
```

Key properties:
- Lazy SDK import (only import `anthropic`/`openai`/`google.generativeai` when actually dispatching)
- API key resolved at dispatch time via `ApiKeyResolver`
- Same `ReviewResult` return type as CLI adapter
- Model fallback chain (same pattern as CLI: primary → fallback on capacity errors)

## Decision 2: API Key Resolution

### Chosen: OpenBao-first with env var fallback

```
resolve_api_key(vendor, openbao_role_id):
  1. If OpenBao is available (OPENBAO_ADDR set):
     → Use openbao_role_id to read secret from vault
  2. Elif env var exists (ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY):
     → Use env var
  3. Else:
     → Return None (vendor skipped)
```

**Alternatives considered:**

- **OpenBao only, no env var fallback**: Too strict for development/testing where OpenBao may not be running. Rejected.
- **Hardcoded keys in agents.yaml**: Security risk, keys in git history. Rejected per user requirement.
- **Keyring/system credential store**: Platform-dependent, adds complexity. Rejected for now — OpenBao is the standard.

### Reuse of existing infrastructure

The `profile_loader.py` already has `_resolve_openbao_secret()` which:
1. Reads `OPENBAO_ADDR` from environment
2. Uses `hvac` client to authenticate via AppRole (`OPENBAO_ROLE_ID` + `OPENBAO_SECRET_ID`)
3. Reads secrets from the vault path

The SDK adapter will import and reuse this function rather than reimplementing OpenBao access.

## Decision 3: agents.yaml Schema Extension

### Chosen: Add `sdk` section to remote agents

```yaml
claude-remote:
  type: claude_code
  transport: http
  openbao_role_id: claude-code-web
  cli:
    # ... existing CLI config (kept for backward compat)
  sdk:
    package: anthropic
    method: messages.create
    model: claude-sonnet-4-6
    model_fallbacks: [claude-haiku-4-5-20251001]
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 16384
```

**Alternatives considered:**

- **Separate SDK config file**: Splits related config across files. Rejected — agents.yaml is the single source of truth for agent capabilities.
- **Infer SDK from vendor type**: Less explicit, harder to override. Rejected — explicit configuration prevents surprises.

### Per-vendor SDK configuration

| Vendor | Package | API Method | Notes |
|--------|---------|------------|-------|
| Anthropic | `anthropic` | `messages.create` | Supports structured output via tool_use |
| OpenAI | `openai` | `chat.completions.create` | Supports JSON mode / response_format |
| Google | `google-generativeai` | `GenerativeModel.generate_content` | Supports JSON output |

## Decision 4: Dispatch Selection Logic

### Chosen: Three-tier waterfall per vendor

```python
def _select_reviewers(reviewers):
    selected = {}  # vendor → best reviewer

    for vendor in unique_vendors(reviewers):
        local_cli = find(reviewers, vendor=vendor, is_local=True, cli_available=True)
        sdk = find(reviewers, vendor=vendor, has_sdk=True, api_key_resolvable=True)

        if local_cli:
            selected[vendor] = local_cli     # Tier 1: Local CLI
        elif sdk:
            selected[vendor] = sdk           # Tier 2: SDK/API
        # else: Tier 3: skip vendor

    return list(selected.values())
```

This ensures:
- At most one reviewer per vendor (no double dispatch)
- Local CLI always wins (uses subscription, fastest)
- SDK only used when CLI is unavailable (genuine fallback)
- Vendors without any working transport are silently skipped

## Decision 5: Prompt Formatting for SDK Dispatch

### Chosen: System + User message with JSON output instruction

For SDK dispatch, the review prompt is wrapped in a standard chat format:

```python
system = """You are a code reviewer. Analyze the provided artifacts and output
ONLY valid JSON conforming to review-findings.schema.json. Do not include
any text outside the JSON object."""

user = f"""Review type: {review_type}
Target: {target}

{prompt}

Output your findings as JSON with this structure:
{{
  "review_type": "{review_type}",
  "target": "{target}",
  "reviewer_vendor": "<your model name>",
  "findings": [...]
}}"""
```

Where possible, use vendor-specific structured output features (Anthropic tool_use, OpenAI response_format) to ensure valid JSON.

## Non-Goals

- **Parallel SDK dispatch**: Start with sequential dispatch (same as CLI). Parallel is a future optimization.
- **Streaming**: Not needed for review dispatch — we wait for the complete response.
- **Cost tracking**: Out of scope — can be added later by wrapping API calls.
- **SDK dispatch for `alternative` mode**: Only `review` mode (read-only) is supported via SDK. `alternative` mode (write access) still requires CLI.
