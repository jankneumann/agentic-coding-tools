# Downstream notice: gen-eval consumers with their own contracts

> From: `jankneumann/agentic-coding-tools`, change `trace-requirements-to-contracts`
> To: any consumer with an `openspec/contracts/<capability>/` CLI or OpenAPI
> contract of their own — `agentic-assistant` / `establish-cli-gen-eval-coverage`
> (ACA roadmap item `ri-06`) named specifically, since `derive-descriptors-from-contracts`
> pointed them at authoring one (DS-3 in that change's own notice)
> Contract: `CONTRACT_VERSION` unaffected — **stays at 2**

**The one-line version, read first: nothing here requires you to do
anything.** Both new opt-ins are opt-ins. If you never add a `traceability:`
(CLI) or `x-traceability` (OpenAPI) block to an operation, and you never
create a `traceability-exclusions.yaml`, your contract validates exactly as
it did before this change and the new gate never looks at it.

**Correction to how a downstream notice from this lineage should be read,
after DS-2 in the `derive-descriptors-from-contracts` notice had to be
rewritten mid-implementation for promising a change that had not shipped
yet.** This notice describes only what is committed on this branch as of the
commit that ships it, not what the change's own plan intends to land later
in the same PR. Where something is still pending, it is named as pending,
not summarized as done.

---

## What this change adds

1. **Two new promoted schemas** —
   `openspec/contracts/gen-eval-framework/schemas/traceability.schema.json`
   and `traceability-exclusions.schema.json` — plus an optional
   `traceability` property on `cli-contract.schema.json`'s command, flag, and
   positional objects (and the OpenAPI equivalent, `x-traceability`, on an
   operation). All additions are optional with no default value, so an
   existing contract that declares none of them is still schema-valid,
   byte-for-byte, after this change.
2. **`packages/gen-eval/scripts/check_traceability.py`** — a new,
   independent gate script. It reads `openspec/specs/<capability>/spec.md`
   for requirement identifiers and your contracts for citations; it does not
   change how any existing gen-eval script (`generate_tool_descriptor.py`,
   `check_coverage_completeness.py`, the CLI itself) behaves, and it does not
   run as part of any of them.
3. **A new phase in `skills/validate-feature/SKILL.md`** (section 7.0b) that
   invokes the gate above at `--scope change --change <id>` during
   spec-compliance validation, but **only when both
   `packages/gen-eval/scripts/check_traceability.py` and
   `openspec/contracts/` exist** — it prints an explicit `SKIP` naming
   whichever is missing otherwise. If your repository does not vendor
   `packages/gen-eval/` at that path, or has no `openspec/contracts/`
   directory, this phase is a no-op for you: it was written specifically so
   that shipping it via `install.sh` cannot fail validation in a repo that
   has neither.

## What is NOT in this change (yet)

The full-capability CI sweep (wiring the same gate into `.github/workflows/ci.yml`
so every contract in every capability is checked on every PR/merge-group/push)
is a separate task in the same OpenSpec change, gated on human authoring work
that had not landed as of this commit. If you are reading this notice from a
copy of `packages/gen-eval/` vendored after that lands, the CI wiring is real;
if you are reading it before, do not assume a repository-wide sweep runs
anywhere yet. Either way it is **this repository's** CI, not something that
runs against your contracts unless you vendor the workflow file too.

## Your tool contract is affected only if you opt in (D6/D13)

Restating the one-liner at the top with the mechanism, because "only if you
opt in" is a claim worth being able to check yourself:

- **Forward** (an operation cites the requirement it serves) is opt-in **per
  contract document** (D6). Adding one `traceability:` block to one operation
  in your CLI or OpenAPI contract commits every *other* operation in that
  same document to the same standard — cite something or carry a written
  `excluded.reason`. A document with zero `traceability:` blocks anywhere in
  it is reported as `untraced`, never failed.
- **Reverse** (a requirement is cited by something) is opt-in **per
  capability**, and the switch is the mere *existence* of
  `openspec/contracts/<your-capability>/traceability-exclusions.yaml` (D13).
  No such file in your capability's directory means reverse completeness is
  reported, never enforced, for you.

Both switches are yours to flip, on your own schedule. Nothing in this
change flips either one for you, and nothing in `check_traceability.py`
scans for contracts outside `openspec/contracts/` to enforce this on.

## If you do want to opt in

1. Author requirements in your own `openspec/specs/<capability>/spec.md` (you
   likely already have these).
2. Add `traceability: { requirements: [<capability>.<slug>, ...] }` (CLI) or
   `x-traceability` (OpenAPI) to the operations that serve them, or
   `traceability: { excluded: { reason: "..." } }` for the ones that
   legitimately serve none — see
   `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml` for a
   fully-opted-in worked example (every one of its 17 flags carries one or
   the other).
3. Run `python packages/gen-eval/scripts/check_traceability.py --scope
   capability --change <your-change-id>` locally before opting in for real —
   it reports without failing until you have a `traceability:` block or an
   exclusions file in play, so you can see exactly what it would flag before
   committing to either switch.

No timeline is imposed and none is expected of you. This notice exists so
that if and when you do open a contract document and see a schema now
accepting a field it did not before, you know where it came from and that it
changes nothing about your contract until you use it.
