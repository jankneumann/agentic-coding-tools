# Design: add-decision-index

## Problem framing

The workflow already produces Decision records (at every phase boundary, via `session-log.md`). The gap is that Decisions get buried inside per-change folders that eventually move to `openspec/changes/archive/`, making cross-change, per-capability archaeology (*"how did we arrive at the current worktree permission model?"*) practically impossible. The fix is not a new write-side artifact — it is a read-side projection organized by the axis people actually query along: **OpenSpec capability**.

## Architectural overview

Two-stage pipeline, implemented as a new emitter pass inside the existing archive-intelligence walker:

```
openspec/changes/**/session-log.md           ← WRITE SIDE (already exists)
        │  (walker: skills/explore-feature/scripts/archive_index.py)
        │
        │  Stage 1: extract tagged Decisions
        ▼
decision_index_entries: List[TaggedDecision]  ← intermediate, in-memory
        │
        │  Stage 2: group by capability, resolve supersession
        ▼
docs/decisions/<capability>.md                ← READ SIDE (new)
docs/decisions/README.md                      ← generated, explains the axis
```

### Why a new emitter pass (not a new walker)

`archive_index.py` already walks `openspec/changes/**/session-log.md` to build `docs/factory-intelligence/archive-index.json`. A parallel walker would:
- Duplicate the archive-discovery + incremental-indexing logic
- Keep two mental models for "which changes exist"
- Risk divergence when one walker sees a change the other doesn't

By adding the emitter as a *consumer* of the same walk, we get incremental regeneration, consistent metadata, and one source of truth for "what's in the archive".

### Why inline backtick tags (not sidecar YAML, not phase-level tags)

Three forcing constraints drove this:

**1. Sanitizer compatibility.** `sanitize_session_log.py` already allowlists kebab-case identifiers up to 52 chars AND does not scan backtick inline code. A tag of the form `` `architectural: <capability>` `` passes both filters, so **zero sanitizer changes are required**. This is the simplest possible extension — no new rules, no risk of over-redaction.

**2. Write-once economy.** Agents already write Decision bullets in session-log. Adding an inline tag is a keystroke; authoring a parallel YAML sidecar doubles the write surface and risks divergence between prose and structured data.

**3. Per-bullet precision.** A single phase entry can easily contain Decisions targeting multiple capabilities (e.g., a worktree-isolation phase may carry one decision about branch naming — `software-factory-tooling` — and another about skill-workflow ordering — `skill-workflow`). Per-bullet tagging supports this naturally; phase-level tags would force either a one-capability-per-phase discipline (unnatural) or a "multiple phase tags" schema (ambiguous when bullets don't map 1:1 to tags).

## Data model

### TaggedDecision (intermediate, in-memory)

```python
@dataclass(frozen=True)
class TaggedDecision:
    capability: str                 # e.g., "skill-workflow" — must match openspec/specs/<capability>/
    change_id: str                  # e.g., "2026-02-06-add-worktree-isolation"
    phase_name: str                 # e.g., "Plan", "Implementation", "Plan Iteration 2"
    phase_date: date                # extracted from `## Phase: <name> (<YYYY-MM-DD>)`
    title: str                      # the bullet's **bold title** (before ` — `)
    rationale: str                  # prose after ` — `
    supersedes: str | None          # change-id#decision-ref the later decision explicitly supersedes
    source_offset: int              # byte offset into session-log.md for stable back-references
```

### Extraction regex (anchored, deterministic)

```
r'^(\d+)\.\s+\*\*(?P<title>[^*]+)\*\*\s+`architectural:\s+(?P<capability>[a-z0-9][a-z0-9-]{0,50}[a-z0-9])`\s*(?:`supersedes:\s+(?P<supersedes>[^`]+)`\s*)?—\s*(?P<rationale>.+)$'
```

Chosen over a more permissive parser because: (a) we want a single canonical tag placement to keep the read side deterministic, (b) malformed tags should surface as warnings, not be silently interpreted.

## Supersession mechanism

Explicit, not inferred. A later Decision declares it supersedes an earlier one via a second inline backtick span:

```markdown
1. **Replace Beads with built-in tracker** `architectural: agent-coordinator` `supersedes: 2026-02-xx-add-beads-integration#D1` — built-in tracker reduces ...
```

The emitter resolves supersession by (a) parsing the `supersedes:` span, (b) locating the referenced Decision in the already-extracted set, (c) annotating both directions (`Supersedes` on new, `Superseded by` on old) in the output markdown.

Inferred supersession (e.g., "later Decision in same capability touching same topic") was rejected: it introduces heuristic calls that would be wrong often enough to damage trust in the index.

## Backfill strategy (conservative pass + durable review queue)

Original plan called for a "systematic full pass" over the ~30+ archived session-logs. Implementation revealed the classifier's keyword-match confidence is orthogonal to architectural-significance: of 141 untagged candidates across 12 archived session-logs (only 12 of 66 archived changes have session-logs — the convention predates the rest), 52 came back as keyword-high-confidence but a substantial fraction of those were procedural or one-off, not pattern-setting. Auto-applying them would poison the index on day one with false positives.

Revised three-step backfill actually shipped:

1. **Extract candidate Decisions.** `skills/explore-feature/scripts/backfill_decision_tags.py` walks every archived session-log and emits every untagged `**Title** — rationale` line as a candidate, with bullet position preserved. No file edits.
2. **Heuristic classifier proposes capability.** Keyword-to-capability mapping (e.g., `worktree|branch|merge_worktrees` → `software-factory-tooling`, `coordinator|lock|claim|queue` → `agent-coordinator`, `session-log|sanitize|phase entry` → `skill-workflow`). Classifier emits proposed assignments with margin-based confidence scores into `openspec/changes/add-decision-index/backfill-proposals.json`.
3. **Agent review + conservative apply.** Agent reviews proposals and applies tags only when title+rationale obviously describe a cross-change architectural pattern. Decisions that pass the keyword heuristic but read as procedural/one-off are left untagged — the goal is **coverage of pivotal decisions, not exhaustive labeling**. Initial pass applied 8 tags across 3 archived session-logs spanning `configuration`, `merge-pull-requests`, and `agent-coordinator`. The remaining proposals stay queued in `backfill-proposals.json` as a durable review queue for later passes.

Combined with the feature's own plan-phase decisions (9 tags across `skill-workflow` and `software-factory-tooling`), the shipped index covers 5 capabilities with 17 tagged decisions — enough to validate the end-to-end pipeline while leaving room for the index to grow as more decisions get curated.

Rejected alternatives for backfill:
- **Pure heuristic auto-apply**: too many miscategorizations; the classifier's margin-based confidence is a keyword signal, not an architectural-significance signal.
- **Pure manual**: ~141 candidates is too much unaided human work for a one-shot pass; incremental curation against the classifier's proposals is the path that scales.
- **Skip backfill, tag only going forward**: would leave the index empty for months and deliver no immediate "how did we get here" value; the conservative pass is a middle ground.

## Make target + CI staleness check

```makefile
decisions:
\tpython3 skills/explore-feature/scripts/archive_index.py --emit-decisions
.PHONY: decisions
```

CI step (new):
```yaml
- name: Verify decision index is up to date
  run: |
    make decisions
    git diff --exit-code docs/decisions/ \
      || (echo "docs/decisions/ is stale. Run 'make decisions' and commit." && exit 1)
```

This pattern is a generalization worth introducing for `make architecture` as well (separate follow-up) — today neither runs in CI, which means stale generated artifacts can land on main undetected.

## Trade-offs accepted

| Accepted | Over | Because |
|---|---|---|
| Inline backtick tags | YAML sidecars | Single write, existing sanitizer works, zero process shift |
| Per-bullet tags | Per-phase tags | Precision for multi-capability phases; no 1:1-or-list ambiguity |
| Explicit supersession | Inferred supersession | Wrong-but-confident inference damages trust; explicit is verifiable |
| Extend archive-intelligence emitter | Standalone walker | One source of truth for archive contents; reuses incremental indexing |
| Heuristic + agent review backfill | Pure heuristic | Miscategorizations on day one would kill adoption |
| Capability files (one per `openspec/specs/<cap>/`) | Single global index file | Questions are asked per-capability; scrolling a monolithic file doesn't serve "how did we get to X?" |
| Generated README | Hand-maintained README | Capability set changes over time (16 today, will grow); hand-maintenance diverges |

## Open questions (to resolve during implementation)

- **Supersession syntax exact form.** Proposed `\`supersedes: <change-id>#<ref>\`` but the `#<ref>` part needs a convention. Options: decision index within phase (`#D2`), decision title hash (`#7a3f`), or phase name + index (`#plan/2`). Recommend decision index within phase (`#D2`) — simplest and stable.
- **Phase-entry ID scheme for back-references.** Session-logs don't currently have stable per-phase-entry anchors. Need a deterministic anchor scheme (e.g., `{change-id}/{phase-slug}/D{n}`) to render `→ session-log: …` links that survive re-sanitization.
- **Handling `session-log.md` not present.** Some archived changes predate session-log convention. The emitter should silently skip changes with no session-log, not warn (too noisy).
