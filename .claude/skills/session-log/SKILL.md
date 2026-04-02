# Session Log — Infrastructure Skill

Provides utilities for appending structured decision records to `session-log.md` (per-change) and `docs/merge-logs/YYYY-MM-DD.md` (per-merge-session). Each workflow skill calls these at phase boundaries to build a living decision record.

## Scripts

### `scripts/extract_session_log.py`

Append-based utilities for session log and merge log management.

**Functions:**

- `append_phase_entry(change_id, phase_name, content, session_log_path=None)` — Append a phase entry to `session-log.md`. Creates the file with header if missing. Returns the Path.
- `append_merge_entry(date, content, merge_log_path=None)` — Append a merge session entry to a dated merge-log file. Creates the file with header if missing. Returns the Path.
- `count_phase_iterations(phase_prefix, session_log_path)` — Count existing iteration entries for auto-incrementing `<N>` in phase names like "Plan Iteration 2".
- `generate_self_summary_prompt(change_id)` — Reference template for structuring phase entries (optional utility).

**Usage from Python:**

```python
from extract_session_log import append_phase_entry, count_phase_iterations

n = count_phase_iterations("Plan Iteration", "openspec/changes/my-change/session-log.md") + 1
append_phase_entry("my-change", f"Plan Iteration {n}", content)
```

**Usage from SKILL.md (agent writes directly):**

Skills embed the phase entry template directly. The agent writes the markdown content, then the skill runs sanitization. The Python functions are optional consistency helpers.

### `scripts/sanitize_session_log.py`

Detects and redacts secrets, high-entropy strings, and environment-specific paths from session log content before it is committed to git. Supports in-place operation (same path for input and output).

```bash
# In-place sanitization (recommended)
python3 scripts/sanitize_session_log.py session-log.md session-log.md

# Separate output
python3 scripts/sanitize_session_log.py input.md output.md

# Dry run
python3 scripts/sanitize_session_log.py input.md output.md --dry-run
```

**What gets redacted**: AWS keys, GitHub tokens, Anthropic/OpenAI keys, connection strings, private key headers, password fields, high-entropy strings (>4.5 bits/char, >20 chars).

**What is preserved**: Git SHAs, UUIDs, OpenSpec change-ids, file paths (normalized), kebab-case identifiers.

**Exit codes**: 0 = success, 1 = sanitization error (do NOT commit the output).

## Phase Entry Template

Each workflow phase appends a section following this structure:

```markdown
---

## Phase: <phase-name> (<YYYY-MM-DD>)

**Agent**: <agent-type> | **Session**: <session-id-or-N/A>

### Decisions
1. **<Decision title>** — <rationale>

### Alternatives Considered
- <Alternative>: rejected because <reason>

### Trade-offs
- Accepted <X> over <Y> because <reason>

### Open Questions
- [ ] <unresolved question>

### Context
<2-3 sentences: what was the goal, what happened>
```

**Section names must be identical across all skills**: Decisions, Alternatives Considered, Trade-offs, Open Questions, Context.

**When no decisions were made** (e.g., validation passed cleanly): include Context, write "No significant decisions required" in Decisions, omit other sections.

## Append-Sanitize-Verify Flow

Every skill follows this 3-step pattern:

1. **APPEND**: Agent writes phase entry to session-log.md (or merge-log)
2. **SANITIZE**: Run `sanitize_session_log.py` on the file (in-place)
3. **VERIFY**: Agent reads sanitized output and checks:
   - All phase entry sections are present (or intentionally omitted)
   - No `[REDACTED:*]` markers in prose where original had no secrets
   - Markdown structure is intact
   - If over-redacted: rewrite without the triggering pattern, re-sanitize (one attempt max)
   - If sanitization exits non-zero: do NOT commit, log warning, continue workflow

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

## Phase Names

| Skill | Phase Name |
|-------|-----------|
| plan-feature | `Plan` |
| iterate-on-plan | `Plan Iteration <N>` |
| implement-feature | `Implementation` |
| iterate-on-implementation | `Implementation Iteration <N>` |
| validate-feature | `Validation` |
| cleanup-feature | `Cleanup` |
| merge-pull-requests | (uses merge-log, not session-log) |

## Integration

This skill is called by workflow skills at phase boundaries:
- **Skills that commit**: plan-feature, implement-feature, cleanup-feature, iterate-on-plan, iterate-on-implementation — include session-log.md in existing commit
- **Skills that need a dedicated commit**: validate-feature — commit session-log.md separately
- **Merge log**: merge-pull-requests writes to `docs/merge-logs/YYYY-MM-DD.md`

## Tests

```bash
skills/.venv/bin/python -m pytest skills/session-log/scripts/ -v
```
