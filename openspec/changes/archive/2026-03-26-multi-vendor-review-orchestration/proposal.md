# Proposal: Multi-Vendor Review Orchestration

## Summary

Add the ability for a primary agent (e.g., Claude Code) to dispatch plan and implementation reviews to different AI vendors (Codex, Gemini) and synthesize their findings into a consensus report that drives the integration gate.

## Motivation

Currently, the parallel workflow's review skills (`/parallel-review-plan`, `/parallel-review-implementation`) are vendor-agnostic by design — they take file-based input and produce structured JSON findings. However, there is no orchestration layer to:

1. **Dispatch reviews to specific vendors** — a Claude agent can't currently ask Codex or Gemini to run a review
2. **Collect multi-vendor findings** — no mechanism to gather findings from N reviewers and synthesize consensus
3. **Trigger alternative plans/implementations** — no way to request that a different vendor produce a competing proposal

Multi-vendor review catches blind spots that single-vendor review misses. Different models have different strengths — one may catch security issues another misses, or propose a simpler architecture the primary agent overlooked.

## User Story

> As a developer using the parallel workflow, I want Claude to automatically dispatch plan and implementation reviews to Codex and Gemini, so that I get diverse perspectives before merging, without manually running each review myself.

## Scope

### In Scope

- **Review dispatch**: Orchestrator dispatches review skills to available agents via CLI subprocess (Codex CLI, Gemini CLI) or work queue
- **Vendor discovery**: Use `discover_agents()` to find available reviewers, with capability filtering
- **Consensus synthesis**: Collect findings from multiple vendors, produce a merged consensus report with agreement/disagreement annotations
- **Integration gate enhancement**: Gate decisions use multi-vendor consensus (e.g., "2/3 reviewers flagged this as critical")
- **Alternative generation**: Optionally request a different vendor produce an alternative plan or implementation for a work package
- **Skill updates**: Update `/parallel-review-plan` and `/parallel-review-implementation` dispatch logic
- **Review dispatcher script**: New Python script that handles vendor selection, CLI invocation, output collection

### Out of Scope

- Cloud agent dispatch via HTTP API (future work — this focuses on CLI-accessible agents)
- New coordinator database tables (reuse existing work queue + discovery)
- Changes to the review findings schema (already vendor-agnostic)
- Automated conflict resolution between disagreeing vendors (human escalation)

## Design Sketch

### Architecture

```
Orchestrating Agent (Claude Code)
         │
         ├─── discover_agents(capability="review") ──→ Coordinator DB
         │         │
         │         ▼
         │    Available reviewers: [codex-local, gemini-local]
         │
         ├─── dispatch_review("codex", artifacts_path) ──→ codex exec skill
         ├─── dispatch_review("gemini", artifacts_path) ──→ gemini exec skill
         │         │                                              │
         │         ▼                                              ▼
         │    findings-codex.json                     findings-gemini.json
         │
         ├─── synthesize_consensus([findings-codex, findings-gemini])
         │         │
         │         ▼
         │    consensus-report.json
         │
         └─── integration_gate(consensus-report) ──→ PASS | BLOCKED
```

### Dispatch Mechanism

Two dispatch modes:

1. **CLI subprocess** (primary, works today): `codex exec --skill review-plan ...` or equivalent Gemini command. Each CLI tool runs the review skill in its own sandbox and writes findings JSON to a known output path.

2. **Work queue** (future, requires agent polling): Submit a `review` task to the coordinator work queue with `preferred_agent_type=codex`. A Codex agent polling the queue picks it up and executes.

### Consensus Model

- **Agreement**: If 2+ vendors flag the same location with the same finding type and criticality >= medium, mark as `confirmed`
- **Disagreement**: If only 1 vendor flags something, mark as `unconfirmed` (lower confidence, still surfaced)
- **Escalation**: If vendors disagree on disposition (one says `fix`, another says `accept`), escalate to human
- **Quorum**: Configurable minimum reviewer count (default: 2). If fewer respond, degrade gracefully with warning

### Output Artifacts

- `reviews/findings-<vendor>.json` — Per-vendor findings (existing schema)
- `reviews/consensus-report.json` — Synthesized consensus (new schema extending review-findings)
- `reviews/review-manifest.json` — Metadata: which vendors reviewed, timing, quorum status

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Codex/Gemini CLI not installed | Medium | Review degrades to single-vendor | Graceful fallback with warning |
| Vendor timeout (slow response) | Medium | Blocks integration gate | Configurable timeout, proceed with available findings |
| Findings explosion (too many) | Low | Human overwhelm | Dedup + consensus reduces noise |
| CLI interface changes | Medium | Dispatch breaks | Abstract behind vendor adapter pattern |

## Success Criteria

1. Claude can dispatch a plan review to Codex and receive structured findings back
2. Claude can dispatch an implementation review to Gemini and receive structured findings back
3. Consensus synthesis produces a merged report from 2+ vendor findings
4. Integration gate correctly uses consensus (confirmed findings block, unconfirmed warn)
5. Graceful degradation when a vendor is unavailable (falls back to single-vendor review)
