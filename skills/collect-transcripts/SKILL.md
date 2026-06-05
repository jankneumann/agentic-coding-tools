---
name: collect-transcripts
description: Ingest raw session transcripts from coding-agent harnesses via vendor-specific adapters, normalize to a common event schema, triage for struggle signals, and write structured findings to episodic memory
category: Git Workflow
tags: [transcripts, session-mining, capability-gaps, harness, multi-vendor]
triggers:
  - "collect transcripts"
  - "mine transcripts"
  - "transcript mining"
  - "session transcripts"
---

# Collect Transcripts

Ingest raw session transcripts from supported coding-agent harnesses via vendor-specific adapters, normalize them to a common event schema, triage for struggle signals, and run deep analysis on flagged sessions. Findings are written to episodic memory using the D4 tag schema with `source:transcript-mined`.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--adapter <name>` (claude_code_cli, claude_code_web, codex_cli, codex_web, gemini_cli; default: all available)
- `--threshold <float>` (composite score threshold for deep analysis; default: 5.0)
- `--dry-run` (print planned operations without API calls; default in CI)
- `--enable` (opt-in to actually run LLM analysis; required to make API calls)

## Adapters

| Adapter | Source | Schema Version |
|---------|--------|---------------|
| `claude_code_cli` | `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` | 1.0 |
| `claude_code_web` | CLI bridge via `claude --teleport <session-id>` | 1.0 |
| `codex_cli` | `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl` | rollout-v1 |
| `codex_web` | CLI bridge via `codex cloud` | rollout-v1 |
| `gemini_cli` | `~/.gemini/tmp/<hash>/chats/session-*.json` | chatRecordingService-v1 |

All adapters fail soft (log warning, skip) when their source is unavailable.

## Pipeline

```
1. Discover sessions (per adapter)
2. Normalize to NormalizedEvent schema
3. Sanitize (secrets, entropy, paths) — BEFORE any LLM sees content
4. Triage (score for struggle signals: retries, errors, scope violations, corrections)
5. Deep analyze (flagged sessions only — heuristic or LLM)
6. Write findings to episodic memory (D4 tag schema, source:transcript-mined)
```

## How It Works

1. **Discovery**: Each adapter enumerates available sessions from its source
2. **Normalization**: Raw vendor events -> NormalizedEvent (common schema in `references/event-schema.md`)
3. **Sanitization**: Reuses `session-log` sanitizer extended for tool-call arguments and tool-result outputs
4. **Triage**: Scores each session on retry_count, tool_error_count, scope_violation_count, user_correction_count
5. **Deep Analysis**: Runs on flagged sessions (composite score >= threshold), extracts structured findings
6. **Memory**: Findings written with D4 tags (`failure_type:*`, `capability_gap:*`, etc.) + `source:transcript-mined`

## Model Resolution

- **Triage**: archetype `analyst` (standard tier), configurable via `config.yaml: triage.archetype`
- **Deep analysis**: archetype `reviewer` (premium tier), configurable via `config.yaml: deep_analysis.archetype`
- Both resolve via `agents_config.resolve_model()` from the coordinator

## Prerequisites

- Python 3.11+
- At least one harness's sessions directory accessible on disk
- For web adapters: vendor CLI installed and authenticated

## Steps

### 1. Discover and Normalize

```bash
python3 <agent-skills-dir>/collect-transcripts/scripts/adapters/claude_code_cli.py
```

### 2. Triage

```bash
python3 <agent-skills-dir>/collect-transcripts/scripts/triage.py \
  --events-dir docs/transcripts/$(date +%Y-%m-%d)/ \
  --threshold 5.0 \
  --dry-run
```

### 3. Deep Analysis (flagged sessions only)

```bash
python3 <agent-skills-dir>/collect-transcripts/scripts/deep_analyze.py \
  --events-file docs/transcripts/2026-06-01/session-abc.jsonl \
  --dry-run
```
