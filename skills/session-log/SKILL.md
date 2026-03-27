# Session Log — Infrastructure Skill

Extracts, sanitizes, and stores agent conversation/session history as a structured `session-log.md` artifact within OpenSpec changes. This preserves decision rationale, trade-offs, and alternatives considered alongside the change artifacts that are committed to git.

## Scripts

### `scripts/extract_session_log.py`

Extracts session context using a 3-tier strategy:

1. **Tier 1 — Session transcript**: Reads Claude Code's local session storage (JSONL) for conversations mentioning the change-id
2. **Tier 2 — Handoff documents**: Compiles context from coordinator handoff document history (JSON)
3. **Tier 3 — Self-summary prompt**: Generates a structured prompt for the agent to summarize from its context window

```bash
# Full extraction (tries tiers 1 → 2 → 3)
python3 scripts/extract_session_log.py \
  --change-id <change-id> \
  --agent-type claude \
  --output session-log.md

# With handoff documents
python3 scripts/extract_session_log.py \
  --change-id <change-id> \
  --handoff-source /path/to/handoffs.json \
  --output session-log.md

# Self-summary prompt only (tier 3)
python3 scripts/extract_session_log.py \
  --change-id <change-id> \
  --prompt-only
```

**Arguments**:
- `--change-id` (required): OpenSpec change-id to extract history for
- `--agent-type`: Agent type — `claude`, `codex`, `gemini`, or `other` (default: `claude`)
- `--handoff-source`: Path to handoff documents JSON file for tier 2 extraction
- `--output`: Output file path (default: stdout)
- `--prompt-only`: Skip tiers 1-2, output self-summary prompt directly

**Exit codes**: 0 = extracted, 1 = error, 2 = self-summary prompt generated (no transcript/handoffs found)

### `scripts/sanitize_session_log.py`

Detects and redacts secrets, high-entropy strings, and environment-specific paths from session log content before it is committed to git.

```bash
python3 scripts/sanitize_session_log.py input.md output.md
python3 scripts/sanitize_session_log.py input.md output.md --dry-run
```

**Arguments**:
- `input`: Path to raw session-log file
- `output`: Path to write sanitized output
- `--dry-run`: Print redaction summary without writing output

**What gets redacted**:
- AWS access keys and secret keys
- GitHub tokens (`ghp_`, `gho_`, etc.)
- Anthropic API keys (`sk-ant-`)
- OpenAI API keys (`sk-`)
- Connection strings (postgresql://, mysql://, etc.)
- Private key headers
- Password/secret fields
- High-entropy strings (>4.5 bits/char, >20 chars)

**What is preserved**:
- Git SHAs, UUIDs, OpenSpec change-ids
- File paths (normalized: `/home/user/` → `~/`)
- Hostnames (internal ones normalized to `[HOST]`)

**Exit codes**: 0 = success, 1 = sanitization error (do NOT commit the output)

## Integration

This skill is called by `linear-cleanup-feature` and `parallel-cleanup-feature` during the session log generation step (between task migration and archive). The cleanup skills handle the orchestration:

1. Call `extract_session_log.py` to get raw session log content
2. Call `sanitize_session_log.py` to redact secrets
3. Commit the sanitized `session-log.md` with the change
4. On any failure, skip and proceed with archive (non-blocking)

## Tests

```bash
# Run from the worktree or repo root
skills/.venv/bin/python -m pytest skills/session-log/scripts/ -v
```
