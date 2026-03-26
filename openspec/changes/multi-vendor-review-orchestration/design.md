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

## Component Design

### 1. Review Dispatcher (`scripts/review_dispatcher.py`)

New script in `skills/parallel-implement-feature/scripts/`:

```
ReviewDispatcher
├── discover_reviewers() → list[ReviewerInfo]
├── dispatch_review(vendor, type, artifacts, output) → DispatchResult
├── dispatch_all_reviews(type, artifacts) → list[DispatchResult]
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

Each adapter implements the `ReviewDispatcher` protocol:

**CodexAdapter**:
```bash
codex exec \
  --prompt "$(cat review-prompt.md)" \
  --context-dir "$ARTIFACTS_PATH" \
  --output "$OUTPUT_PATH/findings-codex.json" \
  --timeout 300
```

**GeminiAdapter**:
```bash
gemini code \
  --prompt "$(cat review-prompt.md)" \
  --context-dir "$ARTIFACTS_PATH" \
  --output "$OUTPUT_PATH/findings-gemini.json" \
  --timeout 300
```

**ClaudeAdapter** (for self-review or when Claude is the secondary reviewer):
```bash
claude code \
  --prompt "$(cat review-prompt.md)" \
  --context-dir "$ARTIFACTS_PATH" \
  --output "$OUTPUT_PATH/findings-claude.json" \
  --timeout 300
```

Note: Exact CLI flags will vary as these tools evolve. Adapters isolate this.

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

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Vendor CLI not found | Skip vendor, log warning, proceed with available vendors |
| Vendor timeout | Kill process, mark as timed out, proceed with available findings |
| Vendor produces invalid JSON | Log error, skip vendor's findings, proceed |
| No vendors available | Fall back to self-review (orchestrating agent reviews its own work) |
| All vendors fail | Emit warning, proceed without review (human must review manually) |
| Quorum not met (< 2 responses) | Proceed with warning in consensus report |

## Testing Strategy

- **Unit tests**: Finding matching algorithm, consensus computation, adapter CLI construction
- **Integration tests**: End-to-end dispatch with mock CLI responses (fixture JSON files)
- **No e2e tests**: Actual vendor dispatch requires live CLIs (tested manually)
