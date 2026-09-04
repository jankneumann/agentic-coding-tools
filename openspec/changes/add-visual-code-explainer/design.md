# Design — add-visual-code-explainer

## Context

Two visualization skills exist and both are artifact-first: `codebase-atlas`
renders the whole graph to one HTML page; `refresh-architecture` emits Mermaid
views at fixed zoom levels. Neither answers a narrow question quickly. The
source of the adopted pattern (humanlayer `show-me`, MIT) is prompt-only and
ungrounded. This design adds the question-first entry point while keeping the
repository's provenance and coverage principles intact.

Constraints inherited from in-flight changes (see `proposal.md` → Impact):
`rewrite-skill-frontmatter` removes `triggers:`; `apply-progressive-disclosure-
oversized-skills` caps `SKILL.md` at 500 lines and references at one level;
`invert-skill-test-suite-to-behavioural` wants three behavioural scenarios per
user-invocable skill; `collect-uncollected-skill-tests` requires a `testpaths`
entry and forbids bare-named helper modules that collide across skills.

## Decisions

### D1 — Prompt-only skill; the only new code is an atlas flag

`skills/explain-code/` contains `SKILL.md` and `references/*.md`, no `scripts/`.
Grounding calls `<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py
--tree`. Rationale: the catalogue works *because* it is prose (Approach 1 vs 2
in the proposal); the one place determinism pays is the call tree, and the
atlas already holds the symbol adjacency (`build_view_model()["symbolEdges"]`).

### D2 — Freshness is decided by the existing `--check` contract

The skill runs `python3 "<skill-base-dir>/../refresh-architecture/scripts/
run_architecture.py" --check` and treats **exit 0 only** as fresh. Exit 2
(drift), exit 1 (error), a missing script, or a missing graph all mean
*ungrounded*. Rationale: `--check` is the read-only half of the
`architecture-refresh` contract that the atlas already mirrors; re-deriving
freshness from `git_sha` in prose would be a second, weaker definition. The
skill **never** runs `--ensure` or the full pipeline (proposal: "never
triggers a refresh on its own").

### D3 — `--tree` output format

```
build_atlas.py --tree <target> [--hops N] [--direction out|in|both] [--graph PATH]
```

- Root line: `<name>  (<file>:<line>)  [<kind>]`.
- Children indented two spaces per hop, sorted by `name` then `id`; direction
  `out` lists callees (edges where the node is `s`), `in` lists callers, `both`
  prints two labelled sections `callees:` / `callers:`.
- A node already printed on the current path is emitted once with the suffix
  `(cycle)` and not expanded. A node beyond `--hops` is not printed; the parent
  line gets the suffix `(+<n> more)` so truncation is visible.
- `--hops` default `2`, maximum `4` (matches the page's hop slider,
  `atlas_render.py`). Values above 4 are clamped with a stderr note.
- Edge type is appended only when it is not `calls` (e.g. `[imports]`), so the
  common case stays quiet.
- Trailing footer: `graph @ <sha7> · <language> <percent>% covered` per language
  present, taken from `build_view_model(measure=True)` — the same `Coverage`
  values the page banner uses. `--no-coverage` suppresses it.

Determinism: children sorted, no timestamps, no random ids. Byte-identical for a
fixed graph and arguments (NFR "Determinism").

### D4 — Target resolution

`<target>` resolves in this order and stops at the first hit: exact node `id`;
unique symbol `name`; a file path or basename matching a module, in which case
the root is the module and hop 1 is the module's own symbols (aggregated view,
mirroring the page's "selecting a file gives the aggregated module view").
Ambiguous names print the candidate ids to stderr and exit `2`; no match exits
`2` with `not found`. Exit `1` remains input/IO errors, `0` success — consistent
with the existing `build_atlas.py` codes.

### D5 — Disclosure line

Every reply ends with exactly one line, never omitted, never collapsed:

- grounded: `Grounding: graph @ <sha7>; python 14% / sql 37% covered`
- ungrounded: `Grounding: source read, unverified (graph <stale|absent|check failed>)`

The grounded form copies the footer `--tree` prints (D3) so the two cannot
drift. The percentages are the atlas's optimistic upper bound and the reference
file says so.

### D6 — Frontmatter without `triggers:`; explicit key test

`SKILL.md` frontmatter: `name`, `description` (third person, capability + when
to use), `category: Architecture`, `tags`, `user_invocable: true`,
`related: [codebase-atlas, refresh-architecture]`. `test_skill_md.py` asserts
those keys directly and does **not** call `assert_required_keys_present` (whose
`REQUIRED_FRONTMATTER_KEYS` still lists `triggers`). When
`rewrite-skill-frontmatter` lands and updates that tuple, the test can switch
back to the shared helper; until then both orderings pass (NFR
"Compatibility"). The description carries the trigger condition — "when the
user asks how a specific piece of the code works or connects, not for a
whole-repository view (use codebase-atlas for that)".

### D7 — Behavioural scenarios: harness-shaped, CI-wired at the deterministic edge

Three scenarios are authored as fixtures under `skills/tests/explain-code/scenarios/`
in the trajectory-scenario harness format when that harness is available in
the checkout; otherwise as pytest tests marked `e2e`. Independently of the
harness, three **deterministic** tests always run in CI and encode the same
three behaviours at the level the prompt can be checked without an LLM:

1. `SKILL.md` instructs the disclosure line for both grounded and ungrounded
   paths (D5 strings present in the grounding reference).
2. `SKILL.md` instructs redirecting whole-repository questions to
   `/codebase-atlas` (string present, and the atlas is in `related:`).
3. `SKILL.md` instructs never running `--ensure` or the analysis pipeline
   (D2/D9 strings present; the skill cannot silently trigger a refresh).

The fourth behaviour — "a grounded call tree cannot invent symbols" — is
asserted where the code lives: `tests/codebase-atlas/test_atlas_tree.py`
checks that `--tree` on the `tiny_graph` fixture prints only fixture node ids.
Keeping it there lets `wp-skill` and `wp-atlas-tree` run in parallel without
`wp-skill` importing code it does not own.

Rationale: the inversion change is 0/10 tasks; this change must be green on
today's CI and must not block on it.

### D8 — Module layout inside the atlas

The BFS and formatter live in `skills/codebase-atlas/scripts/atlas_tree.py`
(prefixed name; `collect-uncollected-skill-tests` forbids bare `tree`/`models`
names that collide across skills under flat collection). `build_atlas.py`
gains the flags and dispatches to it before the render path, after
`build_view_model()`.

### D9 — What the skill refuses

- It does not write files. Text and Mermaid go inline in the reply.
- It does not open a browser and does not need an interactive-capability
  check (it never serves anything). This keeps it outside the gate
  `add-visual-plan-review` D6 defines.
- It does not answer "show me the whole architecture"; it names
  `/codebase-atlas` and stops.

## Task decomposition notes

Nine task titles contain the word "and". Each was checked against the
"and"-splitting heuristic and kept deliberately, because in every case the
conjunction joins *inputs to one outcome*, not two outcomes:

- 1.1, 2.1, 2.2 — "write one test file covering X and Y". The outcome is one
  file; splitting by assertion would produce tasks that cannot be checked off
  independently.
- 1.3 — "wire the flags into `parse_args()` and dispatch in `main()`". A flag
  that parses but does not dispatch is not a shippable half.
- 2.3, 2.4, 2.5 — "write file F with sections A and B". One file per task
  already; 2.4 writes five sibling references that share one template and are
  meaningless apart.
- 3.1 — "merge the `wp-atlas-tree` and `wp-skill` branches". Two inputs, one
  merge commit.
- 3.4 — "run the verification block", whose steps are listed with commas.

The one title that did hide two outcomes — the original 3.1, which merged the
branches *and* regenerated the mirrors — was split into 3.1 and 3.2.

## Risks

| Risk | Mitigation |
|---|---|
| Graph is stale most of the time today (refresh failed during planning), so most answers will be ungrounded | That is the honest state; the disclosure line exposes it, and the redirect to `/refresh-architecture` is one line in the reference. Usage of the ungrounded path is itself the evidence the codeviz proposal says it needs. |
| Basename-only coverage matching over-reports | Reference file states the number is a ceiling; D5 reuses the atlas footer so the caveat is in one place. |
| `rewrite-skill-frontmatter` merges first and changes `REQUIRED_FRONTMATTER_KEYS` | D6 test asserts keys explicitly; no dependency on the tuple. |
| `apply-progressive-disclosure-oversized-skills` lands with a stricter cap | `SKILL.md` targets ≤ 150 lines with a test guard; references are one level deep by construction. |
| Trajectory harness format changes before this lands | D7 keeps the CI-wired tests deterministic and harness-independent. |

## Verification

- Static: `openspec validate add-visual-code-explainer --strict`;
  `skills/install.sh --check-only` (manifest and portability rules).
- Unit: `skills/.venv/bin/python -m pytest skills/tests/codebase-atlas
  skills/tests/explain-code`.
- Determinism: run `--tree` twice on the committed graph and `cmp` the outputs.
- Timing: `--tree` on the committed graph ≤ 2 s (asserted in
  `test_atlas_tree.py`, skipped if the committed graph is absent).
