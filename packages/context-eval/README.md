# context-eval

Measures whether ri-12's injected `Semantic code context` section is worth more
to a coding job than the exact-search baseline the job would otherwise fall back
to — and produces a report whose verdict is exactly `pass` or `fail`.

This package exists because the previous attempt did not survive its own
archival. `openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/`
holds a genuinely good ten-case corpus and a runner whose
`REPO_ROOT = HERE.parents[3]` stopped resolving the moment the change was
archived, whose thresholds were Python literals, and whose published verdict was
`BLOCKED (environment) -> WAIVED (operator decision)`. The corpus was worth
rescuing. Nothing else was.

## Layout

```
corpus/
  manifest.yaml         every threshold, every gate, every consumer, the budget
  cases/*.yaml          19 cases, one file each, listed explicitly in the manifest
  responses/*.json      recorded service responses for the tier-0 gates
src/context_eval/
  models.py             frozen views of the corpus documents
  loader.py             load + validate + digest
tests/                  run from the repository root
```

Run the tests with the infra-skills venv, from the repository root:

```
skills/.venv/bin/python -m pytest packages/context-eval/tests/ -q
```

## Where thresholds live

`corpus/manifest.yaml`, and nowhere else.

`test_thresholds_are_not_readable_from_the_scoring_modules` reads every number
the manifest declares — `k`, the four budget bounds, and every value under
`gates[].thresholds` — and fails if any of them appears as a numeric literal
anywhere under `src/`. A threshold that lives in code cannot be reviewed as a
diff against the evidence it gates.

**The residual gap, stated rather than hidden.** Two threshold values are `0`
and `1.0`, and those two are exempt from the literal check: forbidding them
would forbid list indexing and `!= 1` comparisons, and the check would collapse
into noise. So moving `max_rendered_scope_violations: 0` or
`min_expectation_match_rate: 1.0` into Python would not be caught by that test.
Every other declared number would be. When adding a threshold, prefer a value
outside `{0, 1}` for exactly this reason.

## The labelling convention

Everything the gates compute is measured against hand labels, so the labels are
the standard — not the index's own relevance scores. If you add a case, match
this convention or the corpus will be measuring two different things.

**`expected_files`** — the archived definition, preserved: *any* of these
appearing in an arm's top-k file list counts as a `hit_at_k`. On a rescued case
this field is never edited, because editing it would break comparability with
the numbers the case was originally measured under.

**`must_touch`** — the files a competent engineer must actually open to answer
the query *completely*. This is a stricter statement than `expected_files` and
is allowed to be smaller than it. `T7` is the worked example: its three archived
`expected_files` are preserved, but only `event_bus.py` computes an exponential
delay — `guardrails.py`'s sole match is a comment and `merge_train.py`'s are
re-queue prose — so `must_touch` names one file. A task is not answered by
finding a file that merely mentions the words.

**`evidence_spans`** — the line ranges a competent engineer would actually have
to read. Derived by opening the file, never inferred from the path. Include a
signature and docstring when the docstring is the answer (`T9`'s "atomically…
dependencies satisfied"); include the body when the body is the answer (`T6`'s
Kahn loop). Never a whole file: `evidence_density` is rendered lines inside
spans over all rendered lines, so a generous span quietly rewards a bloated
section. Prefer several tight spans to one loose one. Line numbers are
current-tree, and `test_every_evidence_span_lies_inside_its_file` fails when a
file shrinks under one.

**`scope.read_allow` / `scope.deny`** — the narrowest work-package-shaped scope
under which a real coding job could legitimately have issued this query,
expressed as the repository-relative globs ri-08's `index_scopes()` produces.
Never `**`. `deny` carries `**/.venv/**` on every case that declares a scope,
matching what every `work-packages.yaml` in this repository declares. Two
constraints on the choice: the scope must *contain* the case's own `must_touch`
files — `T8` is scoped to `agent-coordinator/database/migrations/**` rather than
`src/**` because its answer is a SQL expression, and a case whose scope excluded
its own answer would be unwinnable by construction — and an empty `read_allow`
is a deliberate fail-closed declaration, not an oversight.

**`consumer`** — the coding job whose SKILL.md query rule would plausibly have
produced this query. Exactly one per case: per-consumer do-no-harm is absolute,
and a case counted under two consumers would let one consumer's gain offset
another's regression.

**`category`** — descriptive metadata only. See below.

**`rationale`** — why the case is worth measuring *and* why the labels are what
they are. A labelled case with no argument behind its labels cannot be reviewed.

**`provenance`** — required on anything carried forward. Note that
`recorded_at_revision` is absent on all ten rescued cases: the archived artifact
never recorded which revision its `rg` commands were run against, and inventing
one would be fabricating provenance.

## One inherited ambiguity, resolved

The archived evaluation defined its second gate clause twice, differently.

- `run_eval.py:161` computed `semantic_wins_over_keyword` from **measured**
  baseline misses.
- `eval-set.yaml`'s header described the same clause as `category=semantic-win`,
  a hand-applied **label**.

They disagree, and the disagreement is not cosmetic: under the label definition
a corpus author can manufacture wins by relabelling, with no measurement
involved. The spec text — *"tasks the ripgrep baseline misses"* — agrees with
the code.

**The manifest pins the measured definition.** The gate threshold is named
`min_measured_wins_over_baseline`, and a case counts as a win only if the
baseline measurably missed it *in that run*. `category` survives as descriptive
metadata — it records what the labeller predicted, which is useful to a reader
comparing prediction against outcome, and it is an input to nothing.

## The corpus digest

`loader.corpus_digest()` hashes the bytes of `manifest.yaml`, every case file the
manifest lists, and every response file those cases reference, keyed by
corpus-relative path and sorted. No clock, no `random`, no unordered-set
serialisation — two loads in two processes agree.

Bytes rather than parsed content, deliberately. Reformatting a case file moves
the digest even though the meaning did not change. That is conservative in the
only direction that is safe: ri-13's enablement gate treats a report whose
`corpus_digest` no longer matches as **absent**, so a false mismatch withdraws
an authorization that can be re-earned by re-running, where a false match would
authorize enablement on evidence about a corpus that no longer exists.

Changing any threshold therefore invalidates every existing report. That is the
mechanism replacing a waiver field: an operator who believes a threshold is
wrong changes it here, in public, and the old evidence stops counting.

## What the corpus contains

Nineteen cases across all six consumers ri-12 ships.

| Consumer | Cases | Utility measured? |
|---|---|---|
| `implement-feature` | T2, T5, T6, FC-NO-INDEX-AT-REVISION, ADV-LEAKED-HIT | yes |
| `iterate-on-implementation` | T7, T8, FC-REVISION-MISMATCH | yes |
| `debugging-and-error-recovery` | T1, T10, FC-DEBUG-ADHOC-NO-SCOPE | yes |
| `validate-feature` | T4, T9, FC-SCOPE-REJECTED, ADV-ALL-HITS-FILTERED | yes |
| `parallel-review-implementation` | T3, FC-UNKNOWN-STATE, ADV-DENY-PRECEDENCE | yes |
| `quick-task` | FC-QUICK-TASK-NO-DECLARED-SCOPE | **no** — declared |

`quick-task`'s exemption is a declaration, not an omission. Its SKILL.md
documents that it carries no `change_id` and no `package_id`, so ri-08 has
nothing to resolve and every request returns `out_of_scope` /
`no_declared_scope` with no section rendered. There is no utility to measure,
and inventing a scope for it would be the exact failure ri-12 exists to prevent.
The corpus schema makes `utility_applicable` required precisely so that this
reads as a decision someone can disagree with, rather than as a consumer nobody
noticed was missing.

**Fail-closed cases are scored, not skipped.** "The coding job proceeded by exact
search" is a measurement with a pass and a fail. Each asserts the
`(trigger, reason)` *pair*, because ri-12's state mapping is total and a case
checking only the trigger would pass on the wrong cause.

**Adversarial cases are what make the scope gate evidence.** Measured against a
well-behaved server, a scope gate proves only that the server behaved. The layer
that actually protects the agent is ri-12's own client-side deny re-check, and
three recorded responses exist to make it fire: one leaks a hit outside
`read_allow`, one leaks a hit that is inside `read_allow` and excluded only by a
deny glob (and gives it the highest similarity in the body, so a
filter-after-truncate implementation also fails), and one has nothing survive at
all.

## Design decisions

`openspec/changes/gate-semantic-context-default-enablement/design.md` — D1 (the
package's location), D5 (one budget, both arms), D6 (thresholds as data), D7
(what utility means), D8 (zero-tolerance scope), D10 (rescue the corpus, retire
the runner), D12 (evidence expiry).
