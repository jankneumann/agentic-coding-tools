# Session Log: side-effects-validation-v2

---

## Phase: Plan (2026-04-10)

**Agent**: claude-opus-4-6 | **Session**: planning-rebase-from-pr72

### Decisions
1. **3-PR split strategy** -- Split the 5-feature bundle from PR #72 into 3 independently mergeable PRs (assertions+sideeffects, semantic+packs, e2e+integration) to prevent the merge conflict accumulation that killed the original PR.
2. **Preserve all design decisions D1-D7** -- The original proposal's architecture (extend ExpectBlock, side-effects as sub-blocks, prohibit inverse matching, semantic independence, deep matching algorithm, per-category manifests, visibility filtering in generator) remains valid.
3. **Model consolidation in PR 1** -- Move ManifestEntry/ScenarioPackManifest from models.py to manifest.py as sole definition, reducing duplication.
4. **Per-category manifest split in PR 2** -- Replace monolithic manifest.yaml (97 entries, 584 lines) with 12 per-category files to reduce merge conflict surface.
5. **Coordinated tier** -- Coordinator available with full capabilities; work packages support parallel execution.

### Alternatives Considered
- **Single PR (same as PR #72)**: Rejected because the single-PR approach caused the original merge conflict problem. 3-PR split reduces each PR's diff to ~600-700 lines instead of 3,400.
- **Trim scope to core only**: User chose full scope -- all 5 features from PR #72 will be ported.
- **Leave manifest models duplicated**: User chose to consolidate in manifest.py for cleaner architecture.
- **Keep monolithic manifest file**: User chose per-category split to reduce conflict surface.

### Trade-offs
- Accepted slightly more overhead (3 PRs, 3 review cycles) over risk of another conflict-killed PR
- Accepted model growth (ExpectBlock: 8 -> 14 fields) over introducing a new assertion model class (keeps scenario YAML format familiar)
- Accepted O(n*m) deep matching for body_contains over more efficient but complex algorithm (scenario lists are small)

### Open Questions
- [ ] Verify that `harness-engineering-features` (0/21 tasks) does not overlap with gen-eval evaluation changes

### Context
This plan re-creates the work from PR #72 (add-side-effects-validation) which was abandoned due to accumulating merge conflicts after main evolved significantly (17K+ lines deleted on main while the PR was in flight). The new plan preserves all design decisions but bases the implementation on the current codebase state and splits delivery into 3 independent PRs.
