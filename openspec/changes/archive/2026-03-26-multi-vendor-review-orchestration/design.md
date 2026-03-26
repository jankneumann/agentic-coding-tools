# Design: Multi-Vendor Review Orchestration

## Architecture Decisions

### AD-1: CLI Subprocess as Primary Dispatch

**Decision**: Use CLI subprocess invocation (`codex exec`, `gemini code`) as the primary dispatch mechanism rather than work queue or HTTP API.

**Rationale**:
- Works today without requiring agents to poll a queue
- The orchestrating agent (Claude) controls the full lifecycle: invoke, wait, collect output
- Codex and Gemini CLI tools already support skill/prompt execution
- Matches existing patterns in `agent-coordinator/evaluation/backends/`

**Trade-off**: Synchronous — orchestrator blocks while waiting. Acceptable for reviews (minutes, not hours). Work queue dispatch is a future enhancement for cloud agents.

### AD-2: Config-Driven Generic Adapter

**Decision**: Use a single `CliVendorAdapter` class parameterized by CLI configuration from `agents.yaml`, rather than per-vendor adapter subclasses.

All vendor-specific CLI details — command binary, per-mode args, model flag syntax — are declared in `agents.yaml` under a `cli` key. The adapter reads this config and constructs the subprocess command at dispatch time.

```yaml
# agents.yaml — CLI configuration per agent
agents:
  codex-local:
    type: codex
    cli:
      command: codex
      dispatch_modes:
        review:
          args: [exec, -s, read-only]
        alternative_plan:
          args: [exec, -s, workspace-write]
        alternative_impl:
          args: [exec, -s, workspace-write]
      model_flag: -m
      model: null                        # null = CLI default
      model_fallbacks: [o3, gpt-4.1]

  gemini-local:
    type: gemini
    cli:
      command: gemini
      dispatch_modes:
        review:
          args: [--approval-mode, default, -o, json]
        alternative_plan:
          args: [--approval-mode, auto_edit, -o, json]
        alternative_impl:
          args: [--approval-mode, yolo]
      model_flag: -m
      model: null
      model_fallbacks: [gemini-2.5-pro, gemini-2.5-flash]

  claude-code-local:
    type: claude_code
    cli:
      command: claude
      dispatch_modes:
        review:
          args: [--print, --allowedTools, "Read,Grep,Glob"]
        alternative_plan:
          args: [--print, --allowedTools, "Read,Grep,Glob,Write,Edit"]
        alternative_impl:
          args: [--print, --allowedTools, "Read,Grep,Glob,Write,Edit,Bash"]
      model_flag: --model
      model: null
      model_fallbacks: [claude-sonnet-4-6]
```

**Command construction** (generic, works for any vendor):
```python
cmd = [cli.command, *cli.dispatch_modes[mode].args]
if model:
    cmd.extend([cli.model_flag, model])
cmd.append(prompt)  # prompt is always the last positional arg
```

**Rationale**:
- No vendor-specific adapter code — one class handles all vendors
- CLI flag changes are YAML edits, not code changes
- Adding a new vendor means adding an entry to agents.yaml, not a new Python class
- Model flag syntax (`-m` vs `--model`) varies per vendor — config handles this

**Trade-off**: Less validation at the code level — a bad YAML entry could produce an invalid command. Mitigated by the `can_dispatch()` check which verifies the binary exists and runs a smoke test.

### AD-3: File-Based Handoff

**Decision**: Pass artifacts to vendors via filesystem paths, not piped stdin or API payloads.

**Rationale**:
- Review skills already read from filesystem
- Large artifacts (design docs, code diffs) may exceed stdin limits
- Output path is deterministic: `reviews/findings-<vendor>.json`
- Works within worktree isolation model

### AD-4: Consensus as Overlay, Not Replacement

**Decision**: Consensus report references per-vendor findings by ID. It does not replace or merge them — it annotates.

```json
{
  "consensus": [
    {
      "finding_id": "codex-3",
      "matched_findings": ["gemini-5"],
      "status": "confirmed",
      "agreed_criticality": "high",
      "agreed_disposition": "fix"
    },
    {
      "finding_id": "gemini-2",
      "matched_findings": [],
      "status": "unconfirmed",
      "original_criticality": "medium",
      "recommended_disposition": "accept"
    }
  ]
}
```

**Rationale**: Preserves full vendor context. Human reviewer can drill into any vendor's reasoning. No information loss from merging.

### AD-5: Discovery-Driven Vendor Selection

**Decision**: Use coordinator `discover_agents()` to find available reviewers, with fallback to CLI `which` detection.

**Selection priority**:
1. Query `discover_agents(capability="review", status="active")` — returns registered agents
2. If coordinator unavailable, check `which codex`, `which gemini` — binary presence detection
3. Select vendors that are different from the implementing agent's vendor (vendor diversity)
4. If only one vendor available, proceed with single-vendor review + warning

### AD-6: Dispatch Modes as Config, Not Code

**Decision**: Dispatch modes (`review`, `alternative_plan`, `alternative_impl`) and their per-vendor CLI flags are declared in `agents.yaml` under `cli.dispatch_modes`, not hardcoded in adapter code. See AD-2 for the full YAML schema.

Each mode's `args` list determines:
1. **Non-interactive invocation** — flags that suppress user prompts
2. **Permission scope** — read-only vs write access
3. **Output handling** — structured output format flags

**Default dispatch_modes shipped in agents.yaml**:

| Mode | Codex args | Gemini args | Claude args |
|------|-----------|------------|------------|
| `review` | `[exec, -s, read-only]` | `[--approval-mode, default, -o, json]` | `[--print, --allowedTools, "Read,Grep,Glob"]` |
| `alternative_plan` | `[exec, -s, workspace-write]` | `[--approval-mode, auto_edit, -o, json]` | `[--print, --allowedTools, "Read,Grep,Glob,Write,Edit"]` |
| `alternative_impl` | `[exec, -s, workspace-write]` | `[--approval-mode, yolo]` | `[--print, --allowedTools, "Read,Grep,Glob,Write,Edit,Bash"]` |

**Rationale**: CLI flags change as vendor tools evolve. Making them config means updating flags is a YAML edit, not a code change and release cycle. The adapter doesn't need to know vendor-specific flag semantics — it just reads the args list and appends the prompt.

**Safety**: Wrong dispatch_modes config could cause an agent to hang or write outside scope. Mitigated by:
- `can_dispatch()` smoke test on adapter initialization
- Hard timeout on every subprocess (kills hung processes)
- Worktree isolation for write modes (limits blast radius)

### AD-7: Non-Interactive Guarantee

**Decision**: Every vendor dispatch MUST guarantee that subprocess invocation never blocks on user input. The `cli.dispatch_modes` config MUST include non-interactive flags for each mode.

**Verification**: The `can_dispatch()` check verifies:
1. The CLI binary (`cli.command`) exists on PATH
2. The binary is executable
3. The requested dispatch mode exists in `cli.dispatch_modes`

**Timeout as safety net**: Even with non-interactive flags, the dispatcher enforces a hard timeout. If a process doesn't produce output within the timeout, it's killed — this catches cases where a vendor update introduces an unexpected prompt or a config error omits a non-interactive flag.

## Component Design

### 1. Review Dispatcher (`scripts/review_dispatcher.py`)

New script in `skills/parallel-implement-feature/scripts/`.

Two layers: **CliVendorAdapter** (generic, config-driven) and **ReviewOrchestrator** (multi-vendor coordination).

```
CliVendorAdapter (single class, parameterized by agents.yaml config)
├── agent_id: str
├── vendor: str  (from agent entry type)
├── cli_config: CliConfig  (from agents.yaml cli section)
├── can_dispatch(mode: DispatchMode) → bool
├── dispatch_review(
│       review_type: Literal["plan", "implementation"],
│       dispatch_mode: DispatchMode,
│       prompt: str,
│       cwd: Path,
│       timeout_seconds: int = 300,
│       model_override: str | None = None,
│   ) → DispatchResult
└── build_command(mode, prompt, model) → list[str]

CliConfig (parsed from agents.yaml cli section)
├── command: str               # CLI binary (codex, gemini, claude)
├── dispatch_modes: dict[str, ModeConfig]  # per-mode args
├── model_flag: str            # -m or --model
├── model: str | None          # primary model (None = CLI default)
└── model_fallbacks: list[str] # ordered fallback chain

ModeConfig
└── args: list[str]            # CLI args for this mode

ReviewOrchestrator (uses CliVendorAdapters)
├── adapters: dict[str, CliVendorAdapter]  # keyed by agent_id
├── discover_reviewers() → list[ReviewerInfo]
├── dispatch_all_reviews(review_type, dispatch_mode, artifacts_path) → list[DispatchResult]
├── wait_for_results(dispatches, timeout) → list[ReviewResult]
└── classify_error(stderr: str) → ErrorClass  # capacity | auth | transient | unknown

ReviewerInfo
├── vendor: str ("claude_code" | "codex" | "gemini")
├── agent_id: str
├── cli_config: CliConfig | None  # None if agent has no cli section
└── available: bool

DispatchResult
├── vendor: str
├── process: subprocess.Popen | None
├── output_path: Path
├── started_at: datetime
└── timeout_seconds: int

ReviewResult
├── vendor: str
├── success: bool
├── findings_path: Path | None
├── findings: dict | None  (parsed JSON)
├── model_used: str | None     # which model actually produced the result
├── models_attempted: list[str] # all models tried (for manifest)
├── elapsed_seconds: float
└── error: str | None
```

The `CliVendorAdapter` is a single generic class — one instance per agent, parameterized by `CliConfig` from `agents.yaml`. The `ReviewOrchestrator` loads all agent configs, creates adapters for agents with a `cli` section, and manages discovery, selection, parallel dispatch, and result collection.

**Generic command construction** (no vendor-specific code):
```python
def build_command(self, mode: DispatchMode, prompt: str, model: str | None = None) -> list[str]:
    mode_config = self.cli_config.dispatch_modes[mode.value]
    cmd = [self.cli_config.command, *mode_config.args]
    effective_model = model or self.cli_config.model
    if effective_model:
        cmd.extend([self.cli_config.model_flag, effective_model])
    cmd.append(prompt)
    return cmd
```

**Adding a new vendor** requires only a new entry in `agents.yaml` — zero Python code changes.

### 2. Consensus Synthesizer (`scripts/consensus_synthesizer.py`)

New script in `skills/parallel-implement-feature/scripts/`:

```
ConsensusSynthesizer
├── load_findings(paths: list[Path]) → list[VendorFindings]
├── match_findings(findings: list[VendorFindings]) → list[FindingMatch]
├── compute_consensus(matches: list[FindingMatch]) → ConsensusReport
└── write_report(report: ConsensusReport, output: Path)

FindingMatch
├── primary: Finding
├── matched: list[Finding]  (from other vendors)
├── match_score: float  (0.0 = no match, 1.0 = exact)
└── match_basis: str  ("location+type", "description_similarity", etc.)

ConsensusReport
├── review_type: str
├── target: str
├── reviewers: list[ReviewerSummary]
├── quorum_met: bool
├── consensus_findings: list[ConsensusFinding]
├── total_unique_findings: int
├── confirmed_count: int
├── unconfirmed_count: int
├── disagreement_count: int
```

### 3. Finding Matching Algorithm

Findings from different vendors are matched using:

1. **Exact location match**: Same file path + line range + finding type → high confidence match
2. **Semantic match**: Same file path + similar description (Jaccard similarity on tokens) → medium confidence
3. **Type match**: Same finding type across different files on the same logical concern → low confidence
4. **No match**: Finding unique to one vendor → unconfirmed

Threshold: match_score >= 0.6 for "confirmed" status.

### 4. Integration with Existing Orchestrator

Modify `integration_orchestrator.py`:

```python
# Before (single reviewer):
def record_review_findings(self, package_id: str, findings: dict) -> None: ...

# After (multi-vendor):
def record_review_findings(
    self,
    package_id: str,
    findings: dict,
    vendor: str | None = None,
) -> None: ...

def record_consensus(self, package_id: str, consensus: dict) -> None: ...

def check_integration_gate(self) -> IntegrationGateStatus:
    # Enhanced: use consensus findings for gate decisions
    # Confirmed findings with disposition=fix → BLOCKED_FIX
    # Unconfirmed findings → WARNING (don't block)
    # Disagreements → BLOCKED_ESCALATE
```

### 5. Generic CLI Dispatch (Config-Driven)

There are no per-vendor adapter classes. The `CliVendorAdapter` builds the command from `agents.yaml` config:

**Example: Codex review dispatch** (from config `codex-local.cli.dispatch_modes.review.args = [exec, -s, read-only]`):
```bash
# build_command(mode="review", prompt="<prompt>", model=None)
codex exec -s read-only "<prompt>"

# build_command(mode="review", prompt="<prompt>", model="o3")  # fallback
codex exec -s read-only -m o3 "<prompt>"
```

**Example: Gemini review dispatch** (from config `gemini-local.cli.dispatch_modes.review.args = [--approval-mode, default, -o, json]`):
```bash
# build_command(mode="review", prompt="<prompt>", model=None)
gemini --approval-mode default -o json "<prompt>"

# build_command(mode="review", prompt="<prompt>", model="gemini-2.5-pro")  # fallback
gemini --approval-mode default -o json -m gemini-2.5-pro "<prompt>"
```

**Example: Claude alternative_impl dispatch** (from config `claude-code-local.cli.dispatch_modes.alternative_impl.args = [--print, --allowedTools, "Read,Grep,Glob,Write,Edit,Bash"]`):
```bash
claude --print --allowedTools "Read,Grep,Glob,Write,Edit,Bash" "<prompt>"
```

All examples above are generated by the same `build_command()` method — no vendor-specific logic. Updating CLI flags is a YAML edit in `agents.yaml`.

## Data Flow

```
1. Orchestrator completes package implementation
2. Orchestrator calls review_dispatcher.discover_reviewers()
   → [codex-local (cli), gemini-local (cli)]
3. Orchestrator calls review_dispatcher.dispatch_all_reviews("implementation", artifacts_path)
   → Spawns parallel subprocess per vendor
   → Each vendor runs review skill, writes findings JSON
4. Orchestrator calls review_dispatcher.wait_for_results(dispatches, timeout=300)
   → Collects all findings JSONs
5. Orchestrator calls consensus_synthesizer.compute_consensus(findings_list)
   → Matches findings across vendors
   → Produces consensus report
6. Orchestrator calls integration_orchestrator.record_consensus(pkg_id, consensus)
7. Orchestrator calls integration_orchestrator.check_integration_gate()
   → Uses consensus (confirmed findings block, unconfirmed warn)
```

## Output Path Convention

Per-vendor findings and consensus reports live under a `reviews/` subdirectory within the change:

```
openspec/changes/<change-id>/
├── reviews/
│   ├── findings-codex-plan.json        # Per-vendor findings (plan review)
│   ├── findings-gemini-plan.json
│   ├── findings-codex-impl-wp-backend.json  # Per-vendor findings (impl review, per package)
│   ├── findings-gemini-impl-wp-backend.json
│   ├── consensus-plan.json             # Consensus report (plan review)
│   ├── consensus-impl-wp-backend.json  # Consensus report (impl review, per package)
│   └── review-prompt.md                # Prompt template used for dispatch
├── review-findings-plan.json           # Legacy single-vendor path (backward compat)
└── ...
```

**Naming pattern**: `findings-<vendor>-<review_type>[-<package_id>].json`

### Orchestrator Storage Model

The orchestrator's internal storage changes from single-vendor to multi-vendor:

```python
# Before: Dict[package_id, findings_dict]
self._review_findings: dict[str, dict[str, Any]] = {}

# After: Dict[package_id, Dict[vendor, findings_dict]]
self._vendor_findings: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
# Plus consensus keyed by package_id
self._consensus: dict[str, dict[str, Any]] = {}
```

The `record_review_findings()` method remains backward-compatible: if `vendor` is None, it stores under the key `"_default"`.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Vendor CLI not found | Skip vendor, log warning, proceed with available vendors |
| Vendor timeout | Kill process, mark as timed out, proceed with available findings |
| Vendor produces invalid JSON | Log error, skip vendor's findings, proceed |
| No vendors available | Fall back to self-review (orchestrating agent reviews its own work) |
| All vendors fail | Emit warning, proceed without review (human must review manually) |
| Quorum not met (< 2 responses) | Proceed with warning in consensus report |
| Model capacity exhausted (429) | Retry with fallback model, then skip vendor if all models fail |
| Auth expired / login required | Surface error to user with vendor-specific re-login command |

### AD-8: Model Fallback on Capacity Errors

**Decision**: When a vendor returns a 429 / `MODEL_CAPACITY_EXHAUSTED` error, the adapter SHALL retry with fallback models from `cli.model_fallbacks` before giving up.

**Observed behavior** (live test, 2026-03-26): Gemini CLI failed with `MODEL_CAPACITY_EXHAUSTED` on `gemini-3-pro-preview` after 10 internal retries. The CLI's own retry loop doesn't try a different model — it retries the same model with backoff. Our adapter catches this and retries with `cli.model_flag <fallback>`.

**Implementation**: On first attempt, the adapter uses `cli.model` (or omits the flag if null, using CLI default). If the process exits non-zero and stderr matches a capacity error pattern, it retries with each model in `cli.model_fallbacks` in order. Max retries = len(model_fallbacks).

**Error classification** (`classify_error()` in ReviewOrchestrator): Parses stderr to detect error class. Patterns are vendor-agnostic where possible:
- `429`, `RESOURCE_EXHAUSTED`, `capacity`, `rate limit` → `ErrorClass.CAPACITY`
- `401`, `UNAUTHENTICATED`, `token expired`, `login required` → `ErrorClass.AUTH`
- `500`, `503`, `UNAVAILABLE` → `ErrorClass.TRANSIENT`
- Everything else → `ErrorClass.UNKNOWN`

### AD-9: Surfacing Auth Errors to the User

**Decision**: When a vendor fails due to authentication issues (expired token, missing login), the adapter SHALL surface a clear, actionable error message to the user with the vendor-specific re-login command.

**Rationale**: Auth failures are not transient — retrying or falling back to another model won't help. The user needs to take action. These errors should NOT be silently swallowed like capacity errors.

**Error classification**: The adapter parses stderr to distinguish:

| Error class | Detection pattern | Adapter behavior |
|------------|-------------------|-----------------|
| **Auth expired** | `401`, `UNAUTHENTICATED`, `token expired`, `login required` | Surface to user: "Gemini auth expired. Run `gemini login` to re-authenticate." |
| **Capacity exhausted** | `429`, `RESOURCE_EXHAUSTED`, `capacity` | Retry with fallback model |
| **Other transient** | `500`, `503`, `UNAVAILABLE` | Retry once, then skip |
| **Unknown** | Any other non-zero exit | Log stderr, skip vendor |

**User-facing messages**:
```
[WARN] Gemini review failed: auth expired.
       Run: gemini login
       Then retry: /parallel-review-plan <change-id>

[WARN] Codex review failed: login required.
       Run: codex login
       Then retry: /parallel-review-plan <change-id>
```

These messages are printed to stderr by the orchestrator, making them visible regardless of output capture.

## Security: Subprocess Invocation

**All vendor adapters MUST use `subprocess.run()` or `asyncio.create_subprocess_exec()` with list arguments.** Shell invocation (`shell=True`) is prohibited — prompts and paths may contain metacharacters.

```python
# CORRECT — list args, no shell
subprocess.run(
    ["codex", "exec", "-s", "read-only", prompt],
    capture_output=True, text=True, timeout=timeout,
)

# WRONG — shell injection risk
subprocess.run(f'codex exec -s read-only "{prompt}"', shell=True)
```

The design examples use shell-style notation (`$REVIEW_PROMPT`) for readability — actual implementation uses list form.

## Testing Strategy

- **Unit tests**: Finding matching algorithm, consensus computation, adapter CLI construction
- **Integration tests**: End-to-end dispatch with mock CLI responses (fixture JSON files)
- **No e2e tests**: Actual vendor dispatch requires live CLIs (tested manually)
