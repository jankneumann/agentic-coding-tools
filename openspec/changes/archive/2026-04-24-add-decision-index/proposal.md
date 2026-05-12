# Change: add-decision-index

## Why

The workflow already captures architectural decisions in `session-log.md` (per-change, with Decisions / Alternatives / Trade-offs / Context — the canonical MADR template). But decisions get buried in per-change folders that eventually move to `openspec/changes/archive/<date-prefixed-id>/`. Reconstructing *"how did we arrive at the current worktree permission model?"* today requires knowing the change history chronologically (`add-worktree-isolation` → `streamline-worktree-permissions`) and reading two separate session-logs in order. Nobody actually does this, so the institutional reasoning atrophies.

The gap is not a missing record — it is a missing **read-side projection**. Session-log is the write side (produced at every phase boundary). What's missing is a navigable, per-capability, reverse-chronological view of the architectural decisions that shaped each spec in `openspec/specs/`.

Aligning the projection to existing spec capabilities (16 today: `agent-coordinator`, `skill-workflow`, `software-factory-tooling`, etc.) gives every "why is X the way it is?" question an obvious place to look — the same folder name under `docs/decisions/` as the capability lives under in `openspec/specs/`. This extends the existing Archive Intelligence Pipeline (`software-factory-tooling` spec, `skills/explore-feature/scripts/archive_index.py`) which already walks `session-log.md` files; we add a new emitter rather than a parallel walker.

## What Changes

### 1. Tag schema in session-log Phase Entries (skill-workflow spec)
Extend the Phase Entry template in `skills/session-log/SKILL.md` to allow an optional inline ``` `architectural: <kebab-case-capability>` ``` marker on individual Decision bullets:

```markdown
### Decisions
1. **Pin worktrees during overnight pauses** `architectural: software-factory-tooling` — prevents GC during idle
2. **Use `--` separator for parallel agent branches** `architectural: software-factory-tooling` — `/` would collide with parent feature branch ref
```

Per-bullet granularity lets a single phase contribute to multiple capability indices. The tag uses backtick inline code (sanitizer does not scan backticks) and kebab-case identifiers (sanitizer allowlists them up to 52 chars), so **zero changes to `sanitize_session_log.py` are required**.

### 2. Decision-index emitter in archive-intelligence (software-factory-tooling spec)
Extend `skills/explore-feature/scripts/archive_index.py` with a new emitter pass that, for each indexed change, extracts Decision bullets with `architectural:` tags from `session-log.md`, groups them by capability, and writes/updates `docs/decisions/<capability>.md` — one file per capability, reverse-chronological, with back-references to the originating session-log phase entry and explicit `Supersedes:` / `Superseded by:` links when a later change reverses an earlier decision.

Output layout:
```
docs/decisions/
  README.md                          # meta: how to read, how it's maintained
  agent-coordinator.md
  skill-workflow.md
  software-factory-tooling.md
  ...                                # one per capability in openspec/specs/
```

Each capability file is a reverse-chronological timeline of tagged Decisions, with sections per change and cross-references.

### 3. Conservative backfill of archived session-logs with a durable review queue
Walk every change under `openspec/changes/archive/` (12 of 66 archives contain `session-log.md` — the convention is recent). Extract every untagged Decision as a backfill candidate and classify via a keyword heuristic. Commit the resulting `backfill-proposals.json` as a durable review queue alongside the feature. An initial agent-review pass applies tags for the subset of proposals that obviously describe cross-change architectural patterns; the remainder stay in the queue for subsequent curation passes.

Backfill method: **heuristic classifier + conservative agent review**. `skills/explore-feature/scripts/backfill_decision_tags.py` proposes capability assignments based on keyword matching (e.g., "worktree" → `software-factory-tooling`, "coordinator" → `agent-coordinator`, "session-log" → `skill-workflow`) with margin-based confidence scores. An agent reviews the proposals and applies tags only where title + rationale obviously describe a cross-change pattern. The goal is **coverage of pivotal decisions, not exhaustive labeling** — auto-applying keyword-high-confidence proposals would poison the index with false positives, because keyword-match confidence and architectural-significance are orthogonal signals.

### 4. `make decisions` target + CI staleness check
Add a new Makefile target following the `make architecture` precedent (Makefile:120-127). CI runs `make decisions` and fails if `git diff docs/decisions/` is non-empty after regen, catching stale indices caused by missing tags or forgotten regen. Introducing this is a bonus generalizable pattern — `make architecture` could adopt the same CI check in a follow-up.

## Impact

**Affected specs** (split deltas):
- **`skill-workflow`** — ADDED Requirement: "Phase Entry Decision Tagging"
- **`software-factory-tooling`** — ADDED Requirement: "Per-Capability Decision Index Emitter"

**Affected code**:
- `skills/session-log/SKILL.md` — template documentation (no Python change)
- `skills/explore-feature/scripts/archive_index.py` — new emitter pass
- `skills/explore-feature/scripts/decision_index.py` — NEW: classifier + per-capability markdown generator
- `skills/explore-feature/tests/test_decision_index.py` — NEW
- `Makefile` — new `decisions` target
- `.github/workflows/ci.yml` — new staleness check
- `docs/decisions/**` — NEW, one file per capability + README

**Affected workflows**:
- Every workflow skill that appends to session-log gains the *option* to tag Decisions. Not mandatory — untagged Decisions remain valid. Agents that want their architectural calls captured in the index add the inline tag.

**Backward compatibility**:
- Untagged Decisions continue to work exactly as today
- No changes to `sanitize_session_log.py` logic
- No changes to `append_phase_entry()` signature — the template is just extended with an optional inline span

**Explicit non-goals**:
- NOT a replacement for `session-log.md` — session-log remains the per-change write-side source of truth
- NOT a replacement for `docs/lessons-learned.md` — that's cross-change *patterns*; this is per-capability *decisions*
- NOT a global ADR numbering scheme — no `ADR-0007` style identifiers; index is organized by capability, not by global ordinal
- NOT a new skill — this is an extension of two existing skills (session-log template, archive-intelligence emitter)

## Approaches Considered

### Approach A: Emitter extension to archive-intelligence (**Recommended**)

Extend `archive_index.py` with a new emitter pass. Walks session-logs once, emits both the existing machine-readable index *and* the new human decision index. Tags live inline in session-log.md Decision bullets as ``` `architectural: <cap>` ``` markers.

**Pros:**
- Single walker — no duplicate I/O across session-logs
- Reuses the incremental-indexing logic already built for `archive_index.py`
- Clean ownership: tagging in `skill-workflow`, emission in `software-factory-tooling` — matches existing spec boundaries
- Sanitizer works unchanged (backtick + kebab-case are already safe)
- Natural integration with `make architecture`-style CI staleness checks

**Cons:**
- Couples the decision index's freshness to archive-intelligence's indexing cadence
- Requires coordination across two spec deltas (skill-workflow + software-factory-tooling)

**Effort:** M

### Approach B: Standalone walker under session-log skill

Add `skills/session-log/scripts/build_decision_index.py` as an independent tool. Runs independently of archive-intelligence; has its own walker over `openspec/changes/**/session-log.md`.

**Pros:**
- Simpler mental model — one skill owns both the write side (template) and the read side (index generation)
- Looser coupling — decision index ships independently of archive-intelligence changes
- Easier to prototype in isolation

**Cons:**
- Duplicates I/O patterns already in `archive_index.py` (both walkers read the same session-log files)
- Two places to maintain "which archived changes exist and what's their metadata"
- Spec ownership is muddier — session-log is infrastructure; cross-change aggregation conceptually belongs with archive-intelligence

**Effort:** S-M

### Approach C: Structured sidecar file per change

Instead of inline tags on session-log Decision bullets, each change gets `openspec/changes/<id>/decisions.yaml` enumerating tagged decisions (category, title, rationale, supersedes). Archive-intelligence aggregates these sidecars.

**Pros:**
- Machine-readable from day one (no markdown parsing)
- Explicit data separated from prose avoids ambiguity about what's "architectural"
- Sidecar is easy to validate against a JSON schema

**Cons:**
- Duplicates content already written in session-log.md Decisions sections — agents write the same decision twice, or the sidecar becomes the source of truth and session-log gets demoted (substantial process shift)
- Backfill requires authoring ~30 new YAML files rather than editing existing markdown
- New artifact class for agents to produce at every phase boundary — more workflow surface area
- Loses the "just tag what matters in the existing prose" economy

**Effort:** L

---

## Selected Approach

**Approach A — Emitter extension to archive-intelligence** (confirmed at Gate 1).

Rationale: (1) user's explicit preference for extending archive-intelligence over a standalone walker; (2) per-bullet tag granularity aligns with A's inline backtick-tag model; (3) split spec deltas match A's ownership boundaries; (4) sanitizer compatibility is already proven (backticks + kebab-case identifiers are allowlisted, so zero sanitizer changes are required).

Approaches B (standalone walker) and C (YAML sidecars) were considered and rejected. Approach B duplicates I/O across `archive_index.py` and a new walker. Approach C's process shift (write decisions twice, or demote session-log to a YAML-driven artifact) is a heavier change than the indexing gap justifies — can be revisited separately if session-logs later move toward structured data for other reasons.
