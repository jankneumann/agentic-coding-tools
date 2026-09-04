# Testing Policy

Companion to the [skills guide](skills.md). Two skills own the two directions of
this policy: [`test-driven-development`](../../skills/test-driven-development/SKILL.md)
governs which tests get **written**; [`simplify`](../../skills/simplify/SKILL.md)
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

## Removing tests: order and gates

Test removal is the one edit that reduces the evidence available to every edit
after it, so it is ordered and ledgered. The full workflow, catalogs, and reason
codes live in [`skills/simplify/SKILL.md`](../../skills/simplify/SKILL.md); the
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
4. **Gate it.** `skills/simplify/scripts/check_test_prune.py --base <B0> --head <B1> --ledger <path>`
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

A seam may be removed only when a **repo-wide reference search** shows no
remaining non-test consumer *and* the behavior it served is still pinned. A green
suite cannot distinguish an unused seam from an untested production caller.

## Tests for skills in this repo

Skill tests live in `skills/tests/<skill-name>/` and run with
`skills/.venv/bin/python -m pytest skills/tests/`. Content-invariant tests
(`test_skill_md.py`) are held to the same bar as any other test: assert the
structural properties whose loss would make the skill wrong — phase ordering,
gates being wired into checklists, required frontmatter — not the presence of
particular sentences. A skill's prose should be rewritable without touching its
tests.
