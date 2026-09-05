# Testing Policy

Companion to the [skills guide](skills.md). Two skills own the two directions of
this policy: [`test-driven-development`](../../skills/test-driven-development/SKILL.md)
governs which tests get **written**; [`simplify-implementation`](../../skills/simplify-implementation/SKILL.md)
governs which get **removed**.

## Tests must justify their presence

A test earns its place by failing when behavior breaks. Judge a test by what it
would catch, not by the coverage number it moves.

**A test that must be edited whenever the source changes is not a good test.** It
asserts implementation, not behavior. Because it gets rewritten to match whatever
the code now does, it never contradicts a change — it only taxes every commit,
and it anchors the production structure it reaches into. Suites full of these
make refactoring expensive and then get blamed on the refactor.

Corollaries:

- **Prefer state-based tests** (inputs → outputs, errors, side effects) over
  interaction mocks. Structure should be free to move without rewriting tests.
- **Coverage is a diagnostic, not a target.** A line covered only by a
  source-mirroring assertion is not covered.
- **Deleting a low-value test is a net improvement**, not a coverage regression —
  but see the ordering rule below before deleting anything.
- **A regression test tied to a bug or incident stays**, however trivial it looks.
  Someone already paid for it in production.

## The traceability hierarchy

"Justify its presence" has an operational form: **a test is justified iff it has
a path up to a goal.** Validation flows up that path; localization flows down it.

```
Goal                                        VISION.md — why
 └─ Spec clause                             OpenSpec requirement + WHEN/THEN — what
     ├─ Acceptance test   ONE per scenario. Proves composition, not partitions.
     ├─ Invariant test    Security / perf / property / concurrency.
     │                    Traces to the goal directly, cutting across scenarios.
     └─ Seam              Interface with ≥1 consumer — the STABLE tier
         ├─ Contract test Pins inputs / outputs / errors. Where behavior lives.
         └─ Function      Single responsibility: maps to ≤1 clause
             └─ Unit test ONLY where it adds a partition or a localization
                          boundary the contract test cannot cheaply express
```

**Line coverage measures where execution reached. Meaningful coverage measures
which spec clause would go red.** A line reached only by a test with no upward
path is not covered in any sense that matters.

Rules that follow:

1. **Every test has a path up.** No path → orphan → delete candidate. The smells
   in the `simplify-implementation` Delete catalog are how orphans usually
   present; "no upward path" is the general case behind all of them.
2. **Every spec clause has ≥1 test at some tier.** None → the coverage gap that
   actually matters. OpenSpec scenario IDs make this computable.
3. **Each tier adds something the tier above cannot** — a localization boundary
   or an input partition. Otherwise the test is `duplicative`. "Every function
   gets a unit test" is the rule that manufactures change-detectors; a glue
   function composed into a contract-tested seam needs none.
4. **Behavior is pinned at the seam.** Below-seam tests are scaffolding: they may
   be deleted once the seam test passes, and are never the sole pin for a
   behavior. A prune ledger's `covered-by:` should point at the seam tier or
   above.
5. **Validation flows up, localization flows down.** An acceptance failure with
   every unit test green says the bug is in composition. That diagnostic is the
   whole reason lower tiers exist.
6. **Function → clause mapping is a design diagnostic.** Zero clauses → glue, no
   unit test. One clause → the function that deserves one. Many clauses → split.

The test-pyramid *shape* is then a derived quantity, not an asserted rule:
partitions live low and composition lives high, so the distribution follows
from where the equivalence classes are.

### What counts as a consumer

A seam is justified by a consumer. A consumer is **either**:

- **present** — a production caller found by a repo-wide reference search; or
- **specified** — named in an **active, approved** OpenSpec change: a directory
  under `openspec/changes/<id>/`, not archived, not a draft proposal, not a
  roadmap item, not a "we'll need this later" comment.

A specified consumer is a consumer with a delivery commitment; anything less is
the speculative abstraction the `simplify-implementation` rationalization table
already rejects. The distinction gives a lifecycle for free: when the change
lands, the justification becomes "present"; when the change is archived without
landing, the seam becomes an orphan and a prune candidate.

A specified consumer justifies the seam's **contract** — its shape and its
contract test — never the implementation-coupled tests below it, and never the
seam's current internals. Behavior-preserving simplification inside a kept seam
stays allowed.

Cite it where a future reader will look:

```python
# CHESTERTON: kept for openspec/changes/<change-id>
```

on the seam or its contract test. A future orphan-detection pass can then verify
the change is still active and lapse the justification when it is not.

### Making the trace cheap

A trace that costs effort to declare will rot. The intended convention is a
marker on the test naming the OpenSpec scenario it pins, for example
`@pytest.mark.spec("<capability>/<scenario-slug>")`, so that orphan tests,
orphan clauses, and code reached only by unmarked tests become a script's
output rather than a judgment. The marker convention and its checker are a
separate change; adopt the marker on new tests now so the checker has something
to read when it lands.

## Removing tests: order and gates

Test removal is the one edit that reduces the evidence available to every edit
after it, so it is ordered and ledgered. The full workflow, catalogs, and reason
codes live in [`skills/simplify-implementation/SKILL.md`](../../skills/simplify-implementation/SKILL.md); the
rules that bind repo-wide:

1. **Characterize before you prune.** Behavioral pins must exist before
   implementation-coupled tests come out. Prune first and every later change is
   unverified.
2. **Prune commits are test-only.** `test(<scope>): remove <smell> tests for <surface>`.
   Never mixed with the production edit they enable — `git bisect` cannot tell
   them apart otherwise.
3. **Every removal is justified in a ledger**: a reason code, plus the surviving
   test named in `covered-by:` whenever the removed test covered real behavior.
   There is no "re-add coverage later".
4. **Gate it.** `skills/simplify-implementation/scripts/check_test_prune.py --base <B0> --head <B1> --ledger <path>`
   enforces (2) and (3). Baseline `check_test_contract.py` and the dual-run at
   `<B1>`, the post-prune tip.
5. **Do not prune a surface you are not also simplifying.** Pruning alone is a
   coverage reduction with no offsetting gain.

## Test-induced seams

Production code that exists only so a test can reach inside it — mock-only
interfaces, `_for_testing` hooks, factory-of-one indirection, constructor params
defaulted at every production call site — is test debt living in the production
tree. It usually cannot be removed while the implementation-coupled test still
exists, which is why pruning and simplifying belong in the same workflow.

A seam may be removed only when it has **no consumer** — neither a present
production caller (repo-wide reference search) nor a specified one in an active
OpenSpec change (see [What counts as a consumer](#what-counts-as-a-consumer)) —
*and* the behavior it served is still pinned. A green suite cannot distinguish an
unused seam from an untested production caller, and a reference search cannot
see a consumer that has not been written yet; check both.

## Tests for skills in this repo

Skill tests live in `skills/tests/<skill-name>/` and run with
`skills/.venv/bin/python -m pytest skills/tests/`. Content-invariant tests
(`test_skill_md.py`) are held to the same bar as any other test: assert the
structural properties whose loss would make the skill wrong — phase ordering,
gates being wired into checklists, required frontmatter — not the presence of
particular sentences. A skill's prose should be rewritable without touching its
tests.
