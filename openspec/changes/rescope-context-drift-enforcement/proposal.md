# Rescope context drift enforcement

## Why

The deterministic context drift gate reports drift accurately and attributes it wrongly.
It cannot be promoted to a required status check while that is true, and the repository
has already decided it wants that promotion.

`docs/guides/session-completion.md:26-67` carries the `gh api` promotion call fully
written out, marked **NOT APPLIED**, blocked on one precondition: *"Do not apply the
promotion until the gate is green on `main`; making a red check required blocks every
merge."* The same section records why abandoning the gate is not an option —
`docs/decisions/` drifted on `main` in the first place (issue #157) because a
non-required check was repeatedly merged past while red.

Three mechanisms currently stop the gate from being reliably green. Only the first was
known when this work was scoped; the other two were verified during planning.

**1. Merge-commit inheritance.** `gate.py:600-650` evaluates whole-tree producer freshness
at the checked-out revision. On a `pull_request` event `actions/checkout` supplies the
*merge commit*, so every open PR inherits whatever drift already exists on `main`.
`docs/merge-logs/2026-08-24.md:26` records the result: the gate failed identically on 12
unrelated PRs including one-line dependabot bumps, and three of nine needed a second
`refresh-branch` after the first.

**2. The base ref means two different things in one report.** `_default_changed_files`
(`gate.py:359`) runs `git diff --name-only <base>...HEAD` against the **local** ref, while
`describe_tree` (`gate.py:735`) compares against `origin/<base>`. Verified on a branch
byte-identical to `origin/main`:

```
--base main         →  outcome: drift,  exit 2      (main...HEAD = 53 files)
--base origin/main  →  outcome: fresh,  exit 0      (origin/main...HEAD = 0 files)
```

The same report simultaneously stated `commits_behind_base_upstream: 0` and derived 53
changed files from being behind. Dependabot is the standing victim: `.github/dependabot.yml`
opens up to 15 PRs every Monday against whatever `main` was, and `CONTEXT_GATE_BASE ?= main`
(`Makefile:476`) is the default.

**3. The gate does not reproduce locally.** Same tree, same commit: CI job `98378668232`
concluded `success` while `make context-drift-gate` locally exits 2. This violates a
ratified scenario — `### Requirement: Deterministic context drift gate` states the gate
"SHALL be invocable identically from a developer checkout and from CI, so that a CI failure
is reproducible with one local command," with a `Gate reproduces locally` scenario. It
currently fails in the inverse direction, which is worse: a developer chasing a local red
has no CI failure to compare against and will assume their own tree is broken.

A fourth, smaller defect surfaced from the same run. Context-impact validation attributes
changed surfaces to any `work-packages.yaml` present in the diff, whether or not that
package produced them. Archiving always moves a `work-packages.yaml` into the diff, so the
archive pass in PR #423 was reported as `wp-integration: undeclared surface 'decisions'` —
blaming an archived change for five `docs/decisions/*.md` files that the archive commit
itself had just regenerated.

## What Changes

### 1. Pin what the base ref means

The gate resolves the base to exactly one revision and records which one it used in the
report. `origin/<base>` is preferred when it resolves, because that is the ref
`describe_tree` already compares against and the one CI's fresh checkout effectively uses;
the local ref is the documented fallback for a detached or offline checkout. The report
gains the resolved revision, so "which base" stops being invisible.

This is a prerequisite for everything below: attribution logic layered on a base whose
meaning is environment-dependent inherits that ambiguity.

### 2. Classify drift as inherited or introduced

On every event the report classifies each blocking finding as **inherited** (already
present at the merge base) or **introduced** (attributable to the branch). Inherited drift
names `main` as its owner. `commits_behind_base_upstream`, already computed at
`gate.py:709-753`, is surfaced in the human-readable output.

Classification uses path-only ancestry inference:
`git diff --name-only <provenance.source_revision>..<merge_base> -- <input_roots>`. If no
relevant path changed between the revision the producer recorded and the merge base, the
base was fresh and the drift is introduced; if some did, it was already stale and the drift
is inherited.

Content fingerprints cannot be used here: `compute_input_fingerprint` reads working-tree
bytes only — `_iter_root_files_git` (`provenance.py:326`) uses
`git ls-files --cached --others --exclude-standard`, which accepts no revision, and
`_discover` (`provenance.py:394`) calls `read_bytes()` on the filesystem path. Path-level
comparison is a sound over-approximation for this coarser question: it can misclassify
introduced drift as inherited only when a file changed and changed back, which is the safe
direction for a gate that is trying to stop blaming branches.

### 3. Make the blocking verdict event-aware

`pull_request` reports; `merge_group` and `push: main` block. A whole-tree freshness claim
is only well-defined at `main`'s tip, and `merge_group` evaluates exactly the prospective
tip before it lands.

This follows the repository's own precedent rather than inventing one.
`requirement-traceability-sweep` (`ci.yml:626`) runs as **one job on all three events** and
branches on `EVENT_NAME: ${{ github.event_name }}` inside a `case` block
(`ci.yml:737-798`) whose `*)` arm exits 1 on any unhandled event. Its comment rejects the
job-level `if:` form explicitly:

> deliberately NOT guarded by an `if:`, because a required check that does not run on
> `merge_group` is not a check on the merge candidate, and an unguarded job on an event
> with no rule below is the unfalsifiable green this gate exists to prevent.

The drift gate adopts the same shape. Introduced drift blocks on **every** event including
`pull_request`; only inherited drift is downgraded to a report there.

### 4. Auto-remediate dependabot pull requests

A CI job regenerates the cheap deterministic producers — `documentation.inventory`,
`decisions.timeline`, `api.contracts` — and commits the result back, **only on pull
requests authored by dependabot**. The `architecture` producer is excluded: it needs
tree-sitter and writes megabytes.

This would be the repository's first `contents: write` job and its first job-level
`permissions:` block; both workflows are `permissions: contents: read` today and
`GITHUB_TOKEN` appears exactly once, as a read token. Restricting to dependabot confines
that escalation to the population that is provably never the cause of context drift, and
which generates ~15 PRs every Monday.

Two documented traps must be designed around. A servo that regenerates on the PR head
without refreshing the base commits artifacts derived from a stale base — the exact failure
`docs/merge-logs/2026-08-24.md:29` describes. And `generate_tool_descriptor.py:570-573`
records that check-mode argv must be byte-identical to write-mode argv, or the checker and
the writer oscillate forever.

### 5. Fix context-impact attribution

Context-impact validation attributes a changed surface to a work package only when that
package's declared scope covers the changed path, rather than to any `work-packages.yaml`
that happens to share the diff.

### 6. Record inherited-versus-introduced evidence

Each gate run appends a `context_gate` event to `docs/merge-logs/metrics.jsonl`. The
`MergeEvent` dataclass (`merge_events.py:28-45`) types `event_type` as an open string, so
this is additive. It gives the advisory→blocking flip evidence, consistent with the
documented `clean_runs_before_flip: 3` vocabulary in `architecture.config.yaml`.

## Acceptance criterion

`context-drift-gate` is green on `main` across real pull requests, and the promotion at
`docs/guides/session-completion.md:47-53` is applied so that
`gh api .../required_status_checks --jq '.contexts'` lists all seven contexts.

The guide instructs deleting its "known gap" section once that holds. That deletion cannot
be done alone: `introduce-fitness-function-gates` wrote the section immediately below it,
which back-references it — *"Same additive endpoint as the `context-drift-gate` promotion
above"* — and `specs/fitness-functions/spec.md:115-116` makes that adjacency normative.
Both notes are rewritten in the same edit, so the claim stays true rather than dangling.

## Approaches Considered

### Approach 1: Pin the base, then classify against it — **SELECTED**

Resolve the base to one recorded revision, then layer inherited/introduced classification
on top using path-only ancestry inference, and make the verdict event-aware.

**Pros**
- Fixes the cause rather than the symptom: findings 2 and 3 are the reason the gate cannot
  be promoted, and no amount of event gating repairs a base that means two things.
- No new expensive operation. `git diff --name-only` over the declared input roots is
  cheaper than the producer run the gate already performs.
- No payload-format change, so every recorded `input_fingerprint` stays valid.
- Reuses two existing seams: `ChangedFilesResolver` (`gate.py:147`) is already injectable,
  and `checkpoint.py:385` already resolves merge bases.

**Cons**
- Path-level inference is an over-approximation; a file that changed and changed back reads
  as inherited.
- Touches the most-depended-upon function in the gate, with `test_gate.py` (~890 lines)
  pinning current behavior.

**Effort**: M

### Approaches not selected

- **Approach 2: Run the gate twice and diff the reports** (L) — exact rather than inferred:
  anything blocking at the base is inherited by definition. Rejected because every producer
  reads working-tree bytes, so a run at the base needs a checkout or
  `git worktree add --detach` there, which contradicts the ratified requirement that the
  gate "SHALL NOT write to the checkout"; it also doubles gate runtime and still leaves the
  base-ref ambiguity unfixed — two runs against an ambiguous base are two ambiguous answers.
- **Approach 3: Event gating only, no attribution** (S) — move the blocking verdict to
  `merge_group` and `push: main` and let `pull_request` report everything. Rejected because
  genuinely-introduced drift would stop blocking too, which is a real coverage regression
  and the opposite direction from `gate-drift-with-mirrors-hooks-and-blocking-ci`; and
  because it leaves `main`'s own gate environment-dependent exactly where the verdict
  becomes authoritative, so the promotion would still not be safe.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Correctness | Gate verdict for one tree across local and CI | identical | Integration (Tier 2) |
| Correctness | Resolved base revision | recorded in every report | Unit (Tier 1) |
| Correctness | Drift present at the merge base, on `pull_request` | classified inherited, never blocking | Unit (Tier 1) |
| Correctness | Drift introduced by the branch, on any event | blocking | Unit (Tier 1) |
| Compatibility | Existing gate exit codes for introduced drift and failures | unchanged | Unit (Tier 1) |
| Security | Jobs holding `contents: write` | exactly one, dependabot pull requests only | Static (Tier 0) |
| Observability | Gate runs recording inherited-vs-introduced evidence | 100% | Integration (Tier 2) |
| Operability | Unhandled CI event | fails loudly, never silently green | Unit (Tier 1) |

## Impact

**Affected specs**
- `project-context-refresh-orchestration` → `specs/project-context-refresh-orchestration/spec.md` (MODIFIED ×4, ADDED ×2)

**Affected code**
- `skills/project-context-refresh/scripts/gate.py` — base resolution, attribution, report shape
- `skills/project-context-refresh/scripts/cli.py` — `--base` semantics and its stale help text
- `skills/validate-packages/scripts/validate_context_impact.py` — scope-aware attribution
- `skills/merge-pull-requests/scripts/merge_events.py` — `context_gate` event type
- `.github/workflows/ci.yml` — event-aware gate, dependabot remediation job
- `Makefile` — `CONTEXT_GATE_BASE` default
- `docs/guides/session-completion.md` — both promotion notes
- `openspec/schemas/context-drift-gate.schema.json` — report gains base and attribution fields

**Affected architecture layers** — Governance (the gate is a fitness function) and
Execution (producers and validators).

**Constraints inherited from other changes**
- `add-skills-lint-ci-gate` (archived in PR #424) put `gate.py`, `cli.py` and
  `orchestrator.py` under a blocking `ruff` gate pinned to 0.16.0 rules.
- `gate-drift-with-mirrors-hooks-and-blocking-ci` (0/10, stub) will fail CI on drift between
  `skills/` and its two mirrors, so `install.sh` must be re-run before push.
- `test_classify_degradation.py:235` hard-pins
  `INFORMATIONAL_PRODUCERS == frozenset({OPENSPEC_PROJECTION})`.
- `test_gate.py:824` parses the `Makefile` to assert the CI invocation matches.

**Relationship to `gate-drift-with-mirrors-hooks-and-blocking-ci`.** That change promotes
advisory CI steps toward blocking on `pull_request`; this one moves a blocking verdict off
`pull_request` for *inherited* drift. These are not opposed. The drift gate's PR-time
whole-tree claim is **ill-defined**, not insufficiently enforced — it asserts something
about a merge commit that no branch author controls. Introduced drift continues to block on
every event.

**Not breaking.** Exit codes are unchanged for introduced drift, failures, and apparatus
errors. What changes is which findings count as blocking on `pull_request`.
