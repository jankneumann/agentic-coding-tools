# Tasks: Clean Up Dispatch and Add SDK Fallback

## Task 1: Add `sdk` section schema to agents.yaml and agents_config.py

**Depends on:** none

**Files:** `agent-coordinator/agents.yaml`, `agent-coordinator/src/agents_config.py`

1. Define `SdkConfig` dataclass in `agents_config.py`: `package`, `method`, `model`, `model_fallbacks`, `api_key_env`, `max_tokens`
2. Add `sdk` field to `AgentEntry` dataclass (optional, `SdkConfig | None`)
3. Parse `sdk` section from agents.yaml during loading
4. Add `sdk` sections to `claude-remote`, `codex-remote`, `gemini-remote` in agents.yaml
5. Include `sdk` in `get_dispatch_configs()` output alongside `cli` and `transport`
6. Update schema validation to accept the new `sdk` key
7. Add unit tests for loading agents with and without `sdk` sections

## Task 2: Add `ApiKeyResolver` for secure key resolution

**Depends on:** none

**Files:** `skills/parallel-infrastructure/scripts/api_key_resolver.py` (new), `skills/parallel-infrastructure/scripts/tests/test_api_key_resolver.py` (new)

1. Create `ApiKeyResolver` class with `resolve(vendor, openbao_role_id, api_key_env)` method
2. Resolution order: OpenBao (via `openbao_role_id`) → env var (via `api_key_env`) → `None`
3. Import and reuse `_resolve_openbao_secret()` from `agent-coordinator/src/profile_loader.py` (via subprocess call to agent-coordinator, same pattern as `_find_coordinator_dir`)
4. Cache resolved keys for the lifetime of the resolver instance (avoid repeated vault lookups)
5. Add unit tests: OpenBao available, OpenBao unavailable with env var fallback, neither available

## Task 3: Implement `SdkVendorAdapter`

**Depends on:** Task 2

**Files:** `skills/parallel-infrastructure/scripts/review_dispatcher.py`

1. Add `SdkConfig` dataclass (mirrors the one in agents_config.py for standalone use)
2. Add `SdkVendorAdapter` class with:
   - `__init__(agent_id, vendor, sdk_config, api_key_resolver)`
   - `can_dispatch(mode)` — checks SDK package importability and API key availability (only supports `review` mode)
   - `dispatch(mode, prompt, cwd, timeout_seconds)` — calls vendor API, parses JSON findings
3. Implement per-vendor dispatch methods:
   - `_dispatch_anthropic(prompt, model, api_key, timeout)` — uses `anthropic.Anthropic().messages.create()` with tool_use for structured JSON
   - `_dispatch_openai(prompt, model, api_key, timeout)` — uses `openai.OpenAI().chat.completions.create()` with response_format for JSON
   - `_dispatch_google(prompt, model, api_key, timeout)` — uses `google.generativeai` with JSON output
4. Lazy import of SDK packages (only import when dispatching)
5. Model fallback chain on capacity errors (same pattern as CLI adapter)
6. Add unit tests with mocked SDK calls

## Task 4: Update `ReviewOrchestrator` for three-tier dispatch

**Depends on:** Task 1, Task 3

**Files:** `skills/parallel-infrastructure/scripts/review_dispatcher.py`

1. Update `from_config_dict()` to create `SdkVendorAdapter` instances for agents with `sdk` sections
2. Store both CLI and SDK adapters (separate dicts or unified with type discrimination)
3. Update `_select_reviewers()` to implement three-tier waterfall:
   - Tier 1: Local CLI available → use CLI adapter
   - Tier 2: SDK available (package importable + API key resolvable) → use SDK adapter
   - Tier 3: Skip vendor
4. Deduplicate by vendor — at most one reviewer per vendor type
5. Update `--list-agents` output to show dispatch method (CLI/SDK/unavailable)
6. Update `dispatch_and_wait()` to handle both adapter types (both return `ReviewResult`)
7. Add/update unit tests for three-tier selection logic

## Task 5: Update `agents.yaml` with SDK configurations

**Depends on:** Task 1

**Files:** `agent-coordinator/agents.yaml`

1. Add `sdk` section to `claude-remote`:
   ```yaml
   sdk:
     package: anthropic
     method: messages.create
     model: claude-sonnet-4-6
     model_fallbacks: [claude-haiku-4-5-20251001]
     api_key_env: ANTHROPIC_API_KEY
     max_tokens: 16384
   ```
2. Add `sdk` section to `codex-remote`:
   ```yaml
   sdk:
     package: openai
     method: chat.completions.create
     model: gpt-5.4
     model_fallbacks: [gpt-5.4-mini]
     api_key_env: OPENAI_API_KEY
     max_tokens: 16384
   ```
3. Add `sdk` section to `gemini-remote`:
   ```yaml
   sdk:
     package: google-generativeai
     method: generate_content
     model: gemini-2.5-pro
     model_fallbacks: [gemini-2.5-flash]
     api_key_env: GOOGLE_API_KEY
     max_tokens: 16384
   ```

## Task 6: Add optional SDK dependencies to pyproject.toml

**Depends on:** none

**Files:** `agent-coordinator/pyproject.toml`, `skills/pyproject.toml`

1. Add `sdk` optional dependency group to `agent-coordinator/pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   sdk = ["anthropic>=0.40", "openai>=1.50", "google-generativeai>=0.8"]
   ```
2. Add same to `skills/pyproject.toml` (skills venv needs them for review_dispatcher)
3. Ensure `uv sync --all-extras` installs them

## Task 7: Update spec delta for skill-workflow

**Depends on:** Task 4

**Files:** `openspec/changes/clean-up-dispatch-add-sdk-fallback/specs/skill-workflow/spec.md`

1. Add requirements for SDK dispatch adapter
2. Add requirements for three-tier dispatch selection
3. Add requirements for API key resolution via OpenBao
4. Add scenarios covering: SDK dispatch success, SDK dispatch with model fallback, API key not resolvable, mixed CLI+SDK dispatch
5. Update existing Review Dispatcher Protocol requirements to mention SDK as an alternative transport

## Task 8: Integration testing

**Depends on:** Task 4

**Files:** `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`

1. Add tests for `SdkVendorAdapter` with mocked vendor SDKs
2. Add tests for three-tier selection: CLI-only, SDK-only, mixed, none available
3. Add tests for `ApiKeyResolver` with mocked OpenBao
4. Add tests for `--list-agents` showing SDK dispatch method
5. Ensure all existing CLI-only tests still pass unchanged
