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

### AD-2: Vendor Adapter Pattern

**Decision**: Abstract vendor-specific CLI invocation behind a `ReviewDispatcher` protocol with per-vendor adapters.

```python
class ReviewDispatcher(Protocol):
    def dispatch_review(
        self,
        review_type: Literal["plan", "implementation"],
        artifacts_path: Path,
        output_path: Path,
        timeout_seconds: int = 300,
    ) -> DispatchResult: ...
```

**Adapters**:
- `ClaudeCodeDispatcher` — `claude code --skill review-plan --input <path> --output <path>`
- `CodexDispatcher` — `codex exec --prompt <review-prompt> --context <artifacts>`
- `GeminiDispatcher` — `gemini code --prompt <review-prompt> --context <artifacts>`

**Rationale**: CLI interfaces evolve independently. Adapters isolate change. Adding a new vendor means adding one adapter file.

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

### AD-6: Dispatch Mode with Per-Vendor Flag Profiles

**Decision**: Introduce a `DispatchMode` enum (`review`, `alternative_plan`, `alternative_impl`) that maps to vendor-specific CLI flags for non-interactive execution, sandbox permissions, and output format.

Each mode determines three things per vendor:
1. **Non-interactive invocation** — how to suppress user prompts
2. **Permission scope** — read-only vs write access
3. **Output handling** — how to capture structured findings

**Flag profiles per vendor and mode**:

| Mode | Codex | Gemini | Claude |
|------|-------|--------|--------|
| `review` | `exec -s read-only` | `--approval-mode default -o json` | `--print --allowedTools 'Read,Grep,Glob'` |
| `alternative_plan` | `exec -s workspace-write` | `--approval-mode auto_edit -o json` | `--print --allowedTools 'Read,Grep,Glob,Write,Edit'` |
| `alternative_impl` | `exec -s workspace-write` | `--approval-mode yolo -o json` | `--print --allowedTools 'Read,Grep,Glob,Write,Edit,Bash'` |

**Rationale**:
- **Codex** `exec` is inherently non-interactive (headless). Sandbox mode (`-s`) controls write access: `read-only` for reviews, `workspace-write` for implementations.
- **Gemini** uses `--approval-mode` to control tool approval: `default` (prompts, but read-only tools auto-approve), `auto_edit` (auto-approve edits), `yolo` (auto-approve everything). `-o json` for structured output.
- **Claude** uses `--print` for non-interactive output. `--allowedTools` restricts which tools the agent can use.

**Trade-off**: Flag profiles are hardcoded per vendor, not user-configurable. This is intentional — wrong flags could cause agents to hang waiting for input or write outside their scope. If vendors change their CLI, we update the adapter.

### AD-7: Non-Interactive Guarantee

**Decision**: Every vendor adapter MUST guarantee that subprocess invocation never blocks on user input. If the CLI lacks a reliable non-interactive mode, the adapter MUST NOT dispatch to that vendor.

**Verification**: Each adapter implements a `can_dispatch()` check that verifies the CLI binary exists and supports headless mode. For example:
- Codex: presence of `exec` subcommand (always non-interactive)
- Gemini: presence of `--approval-mode` flag (verified via `--help` output parsing or known minimum version)
- Claude: presence of `--print` flag

**Timeout as safety net**: Even with non-interactive flags, the dispatcher enforces a hard timeout. If a process doesn't produce output within the timeout, it's killed — this catches cases where a vendor update introduces an unexpected prompt.

## Component Design

### 1. Review Dispatcher (`scripts/review_dispatcher.py`)

New script in `skills/parallel-implement-feature/scripts/`.

Two layers: **VendorAdapter** (per-vendor protocol) and **ReviewOrchestrator** (multi-vendor coordination).

```
VendorAdapter (Protocol — one per vendor)
├── vendor: str  (e.g., "codex")
├── can_dispatch() → bool
├── dispatch_review(
│       review_type: Literal["plan", "implementation"],
│       dispatch_mode: DispatchMode,
│       artifacts_path: Path,
│       output_path: Path,
│       timeout_seconds: int = 300,
│   ) → DispatchResult
└── Concrete: CodexAdapter, GeminiAdapter, ClaudeAdapter

ReviewOrchestrator (uses VendorAdapters)
├── discover_reviewers() → list[ReviewerInfo]
├── dispatch_all_reviews(review_type, dispatch_mode, artifacts_path) → list[DispatchResult]
└── wait_for_results(dispatches, timeout) → list[ReviewResult]

ReviewerInfo
├── vendor: str ("claude" | "codex" | "gemini")
├── agent_id: str
├── transport: str ("cli" | "mcp" | "http")
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
├── elapsed_seconds: float
└── error: str | None
```

The `VendorAdapter` protocol defines the per-vendor interface. The `ReviewOrchestrator` handles discovery, vendor selection, parallel dispatch, and result collection — it owns the mapping from vendor names to adapter instances.

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

### 5. Vendor CLI Adapters

Each adapter implements the `ReviewDispatcher` protocol. The exact flags vary by dispatch mode (see AD-6).

**CodexAdapter** (review mode):
```bash
codex exec \
  -s read-only \
  "$REVIEW_PROMPT"
# Prompt includes instructions to write findings JSON to stdout
# Output captured from stdout, parsed as JSON
```

**CodexAdapter** (alternative implementation mode):
```bash
codex exec \
  -s workspace-write \
  "$IMPLEMENTATION_PROMPT"
# Working directory set to worktree path
# Writes files directly, commits result
```

**GeminiAdapter** (review mode):
```bash
gemini \
  --approval-mode default \
  -o json \
  "$REVIEW_PROMPT"
# --approval-mode default: read-only tools auto-approved, writes prompt
# -o json: structured output for parsing
```

**GeminiAdapter** (alternative implementation mode):
```bash
gemini \
  --approval-mode yolo \
  "$IMPLEMENTATION_PROMPT"
# --approval-mode yolo: all tool use auto-approved
# Working directory set to worktree path
```

**ClaudeAdapter** (review mode — self-review or secondary reviewer):
```bash
claude \
  --print \
  --allowedTools "Read,Grep,Glob" \
  "$REVIEW_PROMPT"
# --print: non-interactive, output to stdout
# --allowedTools: restrict to read-only tools for reviews
```

**ClaudeAdapter** (alternative implementation mode):
```bash
claude \
  --print \
  --allowedTools "Read,Grep,Glob,Write,Edit,Bash" \
  "$IMPLEMENTATION_PROMPT"
# Full tool access for implementation work
# Working directory set to worktree path
```

Note: Exact CLI flags evolve as these tools update. Adapters isolate this — updating a flag is a one-line change in the adapter, not a workflow change.

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

**Decision**: When a vendor returns a 429 / `MODEL_CAPACITY_EXHAUSTED` error, the adapter SHALL retry with a fallback model before giving up.

**Observed behavior** (live test, 2026-03-26): Gemini CLI failed with `MODEL_CAPACITY_EXHAUSTED` on `gemini-3-pro-preview` after 10 internal retries. The CLI's own retry loop doesn't try a different model — it retries the same model with backoff. Our adapter should catch this and retry with `-m <fallback-model>`.

**Fallback chains per vendor**:

| Vendor | Primary model | Fallback model(s) |
|--------|--------------|-------------------|
| Gemini | (default = gemini-3-pro-preview) | `-m gemini-2.5-pro`, then `-m gemini-2.5-flash` |
| Codex | (default = gpt-5.4) | `-m o3`, then `-m gpt-4.1` |
| Claude | (default = claude-opus-4-6) | `--model claude-sonnet-4-6` |

**Implementation**: The adapter first attempts with the default model (no `-m` flag). If the process exits non-zero and stderr contains `429`, `RESOURCE_EXHAUSTED`, `capacity`, or `rate limit`, the adapter retries with the next model in the fallback chain. Max 1 fallback retry per vendor to avoid compounding delays.

**Stderr parsing**: Each adapter parses vendor-specific error patterns:
- **Gemini**: JSON on stderr with `"code": 429` and `"reason": "MODEL_CAPACITY_EXHAUSTED"`
- **Codex**: Exit code + stderr text containing rate limit messages
- **Claude**: Exit code + stderr error messages

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
