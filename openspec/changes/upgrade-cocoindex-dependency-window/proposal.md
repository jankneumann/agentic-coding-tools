# Change: upgrade-cocoindex-dependency-window

> Capability: `code-search`
> Effort: S–M
> Supersedes: dependabot PRs #730 (cocoindex `<1.1.0` → `<1.2.0`) and #693 (cocoindex-code 0.2.37 → 0.2.42)
> Architecture layer: Execution (indexing pipeline in `packages/code-search`); the Coordination layer
> (`agent-coordinator`) is touched only through its lockfile, because it depends on `code-search-pkg`
> by path.

## Why

`packages/code-search` deliberately hard-pins its upstream indexing stack — design decision **D8**
of `add-semantic-code-search` ("Hard pin and fixture tripwire for the upstream dependency") and its
refinement **D9** of `complete-incremental-semantic-indexing` ("Freeze and tripwire the upstream
API", window `cocoindex>=1.0.13,<1.1.0` + `cocoindex-code==0.2.37`). Two dependabot PRs now ask to
move that window, and both are red on `code-search-tests` because
`tests/test_cocoindex_revision_compat.py` freezes the pin strings. D8 says upgrades are deliberate
PRs, so the operator asked for a planned upgrade instead of merging the bots' diffs.

Research against the official sources (see `design.md` § Sources) changes the shape of the
request:

1. **cocoindex 1.1.x cannot be installed alongside any released cocoindex-code.** Every
   cocoindex-code release up to and including the latest (0.2.43, 2026-11-05) — and the
   `pyproject.toml` on its default branch — declares `cocoindex[litellm]>=1.0.17,<1.1.0`
   (https://pypi.org/pypi/cocoindex-code/0.2.42/json,
   https://github.com/cocoindex-io/cocoindex-code/blob/main/pyproject.toml). `uv pip compile` of
   `cocoindex>=1.1.1,<1.2.0` + `cocoindex-code==0.2.42` is unsatisfiable. Merging #730 would only
   widen a range that the resolver can never use: a no-op that silently loosens the D8 contract.
2. **cocoindex-code 0.2.42 is installable, but it changes a security-relevant transitive dependency.**
   0.2.42 adds the cap `pathspec>=0.12.1,<1.0`. The universal `uv.lock` for code-search therefore
   moves pathspec 1.1.1 → 0.12.1. Under pathspec 0.12, the `**` wildcard compiles to `.*` without
   DOTALL, so `src/**` does not match a path containing a newline. `IndexingPolicy` deny rules use
   the same matcher, so a deny rule such as `src/private/**` stops matching
   `src/private/x\ny.py` while an include rule `**/*.py` still matches it: **the deny rule fails
   open.** (Reproduced locally; also the second failure in #693's CI run,
   `test_source_manifest.py::test_manifest_enumerates_tracked_paths_nul_safely_and_reads_only_eligible`.)
   The coordinator's own lock keeps pathspec 1.0.4, so the same policy would also evaluate
   differently in the two processes.

So this change **upgrades what is upgradeable now** (cocoindex-code 0.2.42 and the newest cocoindex
1.0.x patch, 1.0.26, up from 1.0.18), **fixes the pathspec regression** that upgrade introduces,
**keeps D8** with an explicit coupling rule that would have rejected #730 mechanically, and records
the cocoindex 1.1 surface analysis plus a concrete trigger so the 1.1 move is a small follow-up the
day upstream relaxes its cap.

## What Changes

- **Pins (D8 kept, values moved):** `packages/code-search/pyproject.toml` `index` extra becomes
  `cocoindex[sentence-transformers]>=1.0.17,<1.1.0` and `cocoindex-code==0.2.42`. The floor rises to
  1.0.17 because that is cocoindex-code 0.2.42's own floor.
- **D8 amendment — coupling rule:** the code-search cocoindex window SHALL be no wider than the
  cocoindex requirement declared by the pinned cocoindex-code release. A tripwire test enforces it
  from `uv.lock`, so a range widening like #730 fails in CI with a message naming the coupling,
  not a bare string mismatch.
- **Relock:** regenerate `packages/code-search/uv.lock` (cocoindex 1.0.18 → 1.0.26, cocoindex-code
  0.2.37 → 0.2.42, pathspec 1.1.1 → 0.12.1, mcp 1.28.1 → 2.3.0 transitively) and
  `agent-coordinator/uv.lock` (path-dependency specifier lines only), matching dependabot's `uv`
  ecosystem.
- **Version-independent policy matching:** `indexing_policy._compile_patterns` SHALL produce the
  same include/deny/read decision for every path, including paths containing `\n`, `\t`, or other
  control characters, under both pathspec 0.12.x and 1.x. A regression test covers deny rules on
  newline paths (the fail-open case).
- **Compat tripwire moves:** `test_cocoindex_revision_compat.py` asserts the new pins, asserts the
  locked versions (no extras needed, so it runs in CI), asserts the coupling rule, and asserts that
  `cli_models._PIPELINE_PAYLOAD` records the same window as `pyproject.toml`. The live
  (`requires_embedder`) test checks the frozen surface on 1.0.x/0.2.42, including the
  `build_matcher(..., max_file_size=None)` signature change.
- **Pipeline fingerprint moves:** `_PIPELINE_PAYLOAD` takes the new window, so
  `PIPELINE_FINGERPRINT` changes and existing ready indexes are rebuilt rather than reused
  (required by the `Fingerprinted Indexing Contract` requirement).
- **Dependabot hygiene:** add an `ignore` entry for `cocoindex` versions `>=1.1.0` on the
  `/packages/code-search` uv entry, with a comment pointing to this change, so the unsatisfiable
  widening is not re-proposed weekly. Remove it in the 1.1 follow-up.
- **PR housekeeping:** the implementing PR says `Supersedes #693, #730`; after it merges, #693 is
  closed as superseded and #730 is closed as superseded/unsatisfiable, each with a link.
- No **BREAKING** API or schema change. Operationally, the fingerprint change triggers one full
  re-index per repository on the next indexing run; rollback is a revert of the PR, after which the
  old fingerprint's indexes (if not yet garbage-collected) become reusable again.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | `uv lock --check` in `packages/code-search` and `agent-coordinator` | exit 0 | CI `code-search-tests`, `docker-smoke-import` |
| Compatibility | code-search test suite (`uv sync --extra dev && uv run pytest`) | 0 failures | CI `code-search-tests` |
| Compatibility | live surface + fixture e2e (`requires_db`, `requires_embedder`) | pass on the locked versions | validate-feature (operator-run, ParadeDB + local embedder) |
| Resilience (security) | policy decisions on control-character paths, pathspec 0.12.1 vs 1.x | identical; 0 deny-rule misses | new unit test run against both majors (`uv run --with pathspec==1.0.4`) |
| Operability | re-index cost after fingerprint change | one full index per repo, no manual migration | validate-feature smoke run |

## Approaches Considered

### Approach 1: Upgrade inside the 1.0 window now, defer 1.1 behind a tripwire (Recommended)

Take cocoindex-code 0.2.42 (the #693 target) and cocoindex 1.0.26, keep `<1.1.0`, fix the pathspec
0.12 matcher regression, add a coupling test and dependabot ignore, and record the 1.1 surface
analysis and trigger in `design.md`.

- **Pros:** every pinned version is one upstream actually declares compatible; picks up real fixes
  (cocoindex 1.0.24 LMDB writer-lock hang on long `App.update()` runs, 1.0.20 target invalidation
  through memoization; cocoindex-code 0.2.40 inverted-gitignore traversal fix in `file_walk`);
  closes the fail-open deny regression before it ships; D8 stays a hard pin.
- **Cons:** does not deliver cocoindex 1.1 (the literal ask of #730); one forced re-index.
- **Effort:** S–M

### Approach 2: Force cocoindex 1.1 with a uv override

Add `[tool.uv] override-dependencies = ["cocoindex>=1.1.1,<1.2.0"]` so uv ignores cocoindex-code's
`<1.1.0` cap.

- **Pros:** delivers 1.1.x now (connector-key fixes, `LogicDep`, batching limits).
- **Cons:** runs cocoindex-code against an engine its maintainers have not declared compatible;
  overrides apply only to `uv` — a plain `pip install code-search-pkg[index]` would still fail to
  resolve, so the package's declared metadata lies; contradicts the purpose of D8; the one-time memo
  fingerprint change in 1.1.0 (#2411) and 1.2's `AlreadyDeclaredError` make silent breakage likely.
- **Effort:** M

### Approach 3: Decouple from cocoindex-code (vendor the four imported symbols)

Copy `CHUNKER_REGISTRY`, `build_matcher`, `load_project_settings`, and the
`CODEBASE_DIR`/`EMBEDDER`/`INDEXING_EMBED_PARAMS` context keys into `code_search_pkg`, drop the
cocoindex-code dependency, and pin cocoindex alone at `<1.2.0`.

- **Pros:** removes the upstream coupling entirely; cocoindex upgrades no longer wait for
  cocoindex-code; drops the transitive pathspec/mcp/litellm churn.
- **Cons:** revises D8/D1's "reuse ~95% of cocoindex-code as a library" premise; we would own the
  tree-sitter chunker registry and its language coverage (0.2.42 just added Elixir; 0.2.43 reworks
  chunker fingerprinting); larger review surface and a chunking-behavior fingerprint change.
- **Effort:** L

### Selected Approach

**Approach 1**, selected as the recommended default (operator not interactively available during
planning — see Open Questions). Approach 2 is rejected outright. Approach 3 is recorded as the
fallback if upstream has not relaxed the cap by the review date in Open Question 3.

## Impact

- **Specs:** `code-search` — delta `specs/code-search/spec.md` adds *Coupled Upstream Dependency
  Window* and *Matcher-Independent Path Policy Evaluation*.
- **Code:** `packages/code-search/pyproject.toml`, `packages/code-search/uv.lock`,
  `packages/code-search/src/code_search_pkg/indexing_policy.py`,
  `packages/code-search/src/code_search_pkg/cli_models.py`,
  `packages/code-search/tests/test_cocoindex_revision_compat.py`,
  `packages/code-search/tests/test_indexing_policy.py`, `agent-coordinator/uv.lock`,
  `.github/dependabot.yml`.
- **Not changed:** `indexer_pg.py` (every imported symbol still exists with a compatible
  signature in 0.2.42 / 1.0.26), query path, registry schema, coordinator code.
- **PRs:** #730 and #693 are closed by the implementer after merge, not by this planning change.

## Open Questions

**Resolved 2026-11-16:** the operator accepted this proposal with every default below as stated.
The implementer treats each default as a decision, not an open question.

Defaults below were chosen by the planner because the operator was not available for the
discovery and approval gates.

1. **cocoindex-code 0.2.42 or 0.2.43?** Default **0.2.42** (the #693 target, CI evidence exists).
   0.2.43 (2026-11-05) also caps `cocoindex<1.1.0`, and its indexer fixes (#287, #299, #301) touch
   upstream's own `indexer.py` and chunker fingerprinting, which we do not use but which would
   change `cocoindex_code.chunking` import-time behavior. Could be taken in the same PR if the
   operator prefers the newest patch.
2. **Add the dependabot `ignore` for cocoindex `>=1.1.0`?** Default **yes**, with a removal task
   in the 1.1 follow-up. Alternative: leave it and close each re-proposal by hand.
3. **When to switch to Approach 3?** Default: re-check cocoindex-code's declared cocoindex range
   when the 1.1 follow-up is next prioritised; if no release permits `>=1.1` by **2027-01-31**,
   open a decoupling proposal instead.
4. **pathspec range.** Default: keep the declared `pathspec>=0.12,<2` and make the matcher
   version-independent, because the coordinator resolves 1.x and code-search resolves 0.12.x from
   the same declaration. Alternative: narrow to `>=0.12.1,<1.0` to match upstream, accepting that
   the coordinator lock is then forced down too.
5. **Floor of the cocoindex window.** Default `>=1.0.17` (cocoindex-code's floor). Alternative:
   `>=1.0.26` so no environment can resolve an engine older than the one tested; the lock pins
   1.0.26 either way.
6. **Re-index on fingerprint change.** Default: accept one full re-index per repository. Confirm no
   deployment depends on a ready index surviving this upgrade.
