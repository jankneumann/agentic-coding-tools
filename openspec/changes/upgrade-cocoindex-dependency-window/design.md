# Design: upgrade-cocoindex-dependency-window

Decision IDs here are local to this change (U1…). They amend, not replace, **D8** of
`openspec/changes/archive/2026-07-20-add-semantic-code-search/design.md` and **D9** of
`openspec/changes/archive/2026-07-25-complete-incremental-semantic-indexing/design.md`.

## Frozen surface inventory

What `code_search_pkg` actually imports from upstream (from `indexer_pg.py`,
`embedding_config.py`), and what each target version does to it.

| Surface | Used as | 1.0.18 → 1.0.26 / 0.2.37 → 0.2.42 (this change) | cocoindex 1.1.0–1.1.1 (follow-up) | cocoindex 1.2.0 (out of scope) |
|---|---|---|---|---|
| `coco.App`, `AppConfig`, `Environment`, `Settings.from_env`, `ContextProvider` | app construction | unchanged API; 1.0.24 fixes LMDB writer lock hang on long `App.update()` (#2426); 1.0.25 adds `Environment.close()` (#2481) | 1.1.0: opening a still-open `db_path` raises a `RuntimeError` naming `Environment.close()` (#2561) | — |
| `coco.ContextKey[...]` (8 module-level keys) | context identity | unchanged | docs warn two `ContextKey`s for one resource can collide (#2609/#2610) | duplicate declaration of a `ContextKey` in one run raises `AlreadyDeclaredError` (ValueError subclass, #2672) |
| `@coco.fn(memo=True)`, `coco.use_context`, `coco.map` | memoized per-file processing | 1.0.20 target invalidation through memoization fixed (#2346); 1.0.26 memoized calls join caller frame | **one-time effect:** memo fingerprints of values with shared sub-objects change (#2411) — memoized work may re-run once; 1.1.1 fixes memoized function losing target states when tracked state changed (#2660) | warm runs skip state-store writes (#2784) |
| `coco.mount_each`, `component_subpath`, `Symbol` | per-file components | unchanged | mounting one path twice already an error; message improved | duplicate `mount_each` key → `AlreadyDeclaredError` |
| `cocoindex.connectors.localfs` (`walk_dir`, `File`) | source enumeration | unchanged | **key normalization:** case-only rename and `./a` vs `a` no longer change an item's key (#2598); one-time re-key possible | — |
| `cocoindex.ops.text.RecursiveSplitter`, `detect_code_language` | fallback chunking | unchanged | unchanged | **chunk output change:** text after a grammar root node is no longer dropped (#2786) → chunking fingerprint must move |
| `cocoindex.resources.chunk.Chunk` | chunk type | unchanged | unchanged | — |
| `cocoindex.resources.schema.VectorSchema` | `__coco_vector_schema__` | unchanged | serde fix only for `dtype=np.float32` *class*; we pass `np.dtype(np.float32)` instance, unaffected (#2536) | — |
| `cocoindex_code.chunking.CHUNKER_REGISTRY` | AST chunker lookup | unchanged in 0.2.38–0.2.42 (chunking.py not in compare diff) | — | 0.2.43 fingerprints chunkers at import time (#299) |
| `cocoindex_code.file_walk.build_matcher` | changed-path matcher | **signature grows** optional 4th param `max_file_size: int \| None = None` (backward compatible, positional call with 3 args still valid); 0.2.40 inverted-gitignore traversal fix (#239) | — | — |
| `cocoindex_code.settings.load_project_settings` | `language_overrides` | `ProjectSettings` gains `max_file_size`; `EmbeddingSettings.__post_init__` validates MPS watermark ratios; default include patterns add `.dart`, `.ex`, `.exs` (we do not use upstream include patterns — `IndexingPolicy` owns eligibility) | — | — |
| `cocoindex_code.shared.CODEBASE_DIR`, `EMBEDDER`, `INDEXING_EMBED_PARAMS` | context keys | unchanged (`EMBEDDER` still `ContextKey(..., detect_change=True)`) | — | — |
| transitive `pathspec` | `IndexingPolicy` matcher | **1.1.1 → 0.12.1** (0.2.42 caps `<1.0`) — see U3 | — | — |
| transitive `mcp` | not imported by code-search | 1.28.1 → 2.3.0 (0.2.40 "support MCP Python SDK v2", #242) | — | — |

## Decisions

### U1 — Keep D8 (hard pin); move the window inside 1.0

`cocoindex[sentence-transformers]>=1.0.17,<1.1.0`, `cocoindex-code==0.2.42`, locked to cocoindex
1.0.26. D8's rationale — young upstream, deliberate upgrade PRs, loud tripwire — is unchanged and
this upgrade is itself evidence for it: an unreviewed merge of #693 would have shipped a fail-open
deny rule (U3).

### U2 — Coupling rule (D8 amendment)

The code-search cocoindex window MUST be a subset of the cocoindex requirement declared by the
pinned cocoindex-code release. Enforced by a CI test that reads `uv.lock` (no extras needed):

- the locked `cocoindex-code` version equals the `==` pin in `pyproject.toml`;
- the locked `cocoindex` version satisfies the pyproject window;
- the pyproject window's upper bound is ≤ the upper bound cocoindex-code declares — taken from a
  constant recorded in the test with its PyPI source URL, because `uv.lock` does not record
  upstream `requires_dist` ranges. When the cocoindex-code pin moves, the constant must be updated
  from https://pypi.org/pypi/cocoindex-code/<ver>/json, which is the deliberate review step.

The live `requires_embedder` test additionally reads
`importlib.metadata.requires("cocoindex-code")` and checks the same rule against the installed
metadata, so the constant cannot drift silently on a developer machine.

### U3 — Matcher-independent policy evaluation

`IndexingPolicy` decisions MUST NOT depend on the installed pathspec major. pathspec 0.12.x
compiles `**` to `.*` without `re.DOTALL`, so a path containing `\n` escapes `src/**`-style
deny rules while `**/*.py` includes still match (fail-open). Options for the implementer, in order
of preference:

1. Compile the policy patterns through a small `GitWildMatchPattern` subclass whose regex is
   compiled with `re.DOTALL` (confirm the subclassing hook — e.g. `pattern_to_regex` — on both
   0.12.1 and 1.x before relying on it), passed as a pattern class rather than a registered
   factory name — keeps gitignore semantics, no new dependency.
2. Evaluate deny/read rules on a path whose control characters are mapped to a sentinel that no
   wildcard excludes — rejected as default because it changes which literal patterns can match.
3. Treat any path containing a control character as `ineligible` (fail-closed). Acceptable as a
   defence-in-depth addition, not as the fix, because it changes the existing NUL-safe manifest
   contract that `test_source_manifest` pins (tab and newline names are currently indexed).

Also switch off the deprecated `"gitignore"` factory name on 0.12 (emits `DeprecationWarning`).

Verification runs the policy test under the locked pathspec 0.12.1 and once more with
`uv run --with pathspec==1.0.4` so both majors are proven equal.

### U4 — Pipeline fingerprint follows the pin

`cli_models._PIPELINE_PAYLOAD` records `cocoindex` and `cocoindex_code`. Both move, so
`PIPELINE_FINGERPRINT` changes and the `Fingerprinted Indexing Contract` requirement makes every
existing ready index non-reusable — one full re-index per repo. `policy.version` does **not** bump:
with U3 the effective policy decisions equal the pre-upgrade behavior under pathspec 1.1.1. A test
asserts the payload's window equals the pyproject window, removing a third hand-maintained copy.

### U5 — Defer cocoindex 1.1; record trigger

Blocked: no cocoindex-code release (≤ 0.2.43) or default-branch `pyproject.toml` permits
`cocoindex>=1.1`. Trigger for the follow-up change: a cocoindex-code release whose PyPI
`requires_dist` admits `cocoindex>=1.1.1` (1.1.0 excluded because 1.1.1 fixes memo target-state
loss, #2660, which our `@coco.fn(memo=True)` path could hit). The follow-up must (a) bump
`_PIPELINE_PAYLOAD` (memo fingerprint one-time effect #2411; localfs re-key #2598), (b) remove the
dependabot ignore from U6, (c) re-run the two-revision incrementality e2e. If the target becomes
1.2, it must also bump the chunking fingerprint (#2786) and audit `ContextKey` declarations for
`AlreadyDeclaredError` across repeated `create_app` calls in one process.

### U6 — Dependabot

Dependabot's `uv` ecosystem entry for `/packages/code-search` gains
`ignore: [{dependency-name: "cocoindex", versions: [">=1.1.0"]}]` with a comment citing U5. The
implementing PR body states `Supersedes #693, #730`; after merge the implementer closes #693
("superseded by <PR>") and #730 ("superseded by <PR>; unsatisfiable with every released
cocoindex-code, see U5").

## Rejected alternatives

- **uv `override-dependencies` to force 1.1** — metadata would lie to non-uv installers; runs an
  undeclared combination; contradicts D8.
- **Vendor cocoindex-code symbols** — viable future escape hatch (proposal Approach 3, Open
  Question 3), not justified while upstream is active.
- **Merge #693 as-is and fix the policy later** — ships the fail-open deny rule.

## Sources

- cocoindex releases: https://github.com/cocoindex-io/cocoindex/releases/tag/v1.1.0,
  https://github.com/cocoindex-io/cocoindex/releases/tag/v1.1.1,
  https://github.com/cocoindex-io/cocoindex/releases/tag/v1.2.0, 1.0.19–1.0.26 at
  https://github.com/cocoindex-io/cocoindex/releases
- cocoindex-code releases: https://github.com/cocoindex-io/cocoindex-code/releases/tag/v0.2.38
  … https://github.com/cocoindex-io/cocoindex-code/releases/tag/v0.2.43
- cocoindex-code diff 0.2.37…0.2.42:
  https://github.com/cocoindex-io/cocoindex-code/compare/v0.2.37...v0.2.42
- Declared ranges: https://pypi.org/pypi/cocoindex-code/0.2.42/json,
  https://pypi.org/pypi/cocoindex-code/0.2.43/json,
  https://github.com/cocoindex-io/cocoindex-code/blob/main/pyproject.toml
- Original pins: https://github.com/cocoindex-io/cocoindex-code/blob/v0.2.37/pyproject.toml
- pathspec behavior: reproduced with `uv run --with pathspec==0.12.1|1.0.4` (see session-log);
  #693 CI run https://github.com/jankneumann/agentic-coding-tools/actions/runs/42555450924
