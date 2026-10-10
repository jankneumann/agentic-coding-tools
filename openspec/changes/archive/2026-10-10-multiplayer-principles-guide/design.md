# Design: Publish the multiplayer collaboration principles guide

## Context

The `multiplayer-collaboration` roadmap derives 19 follow-on changes from ten principles
(P1-P10). Those principles, the single-principal assumption table, and the solo/team
vocabulary currently live only in `openspec/roadmaps/multiplayer-collaboration/proposal.md`,
which is archived when the roadmap completes. This change publishes them as a linked guide
and guards the guide's structure with a test. It changes no runtime behavior.

The source of truth for the guide's content is the roadmap proposal: principle titles and
statements, the eight-row assumption table, and each capability's *Serves* line.

## Decisions

### D1. Capability: keep `multiplayer-collaboration`

The requirements go in a new capability `multiplayer-collaboration`, the same capability
every sibling change in the roadmap targets. This change is the first to create
`openspec/specs/multiplayer-collaboration/spec.md` on archive.

- *Alternative*: put the requirements in `skill-workflow` or `harness-engineering`.
  Rejected: the guide is the vocabulary reference for exactly the capability the siblings
  extend; splitting it from them would scatter the epic across specs.

### D2. Mode vocabulary is defined here, detected by `ownership-map`

The guide defines:

- **Principal**: a human on whose behalf an action is taken (P1).
- **Solo mode**: the ownership resolver yields exactly one distinct human principal for
  the repository. This holds when `openspec/owners.yaml` is absent and also when it names
  only one human principal.
- **Team mode**: the resolver yields two or more distinct human principals.
- **Solo-mode guarantee**: in solo mode no multiplayer capability adds a prompt, an
  approval gate, or a PR checkpoint that did not exist before the roadmap. Capabilities
  may add passive output in solo mode (for example a PR ledger section from
  `reviewer-shaped-prs`, commit trailers from `attribution-trailers`), provided it
  requires no human action. Without this clause the guarantee would contradict those
  siblings' solo-mode acceptance outcomes.
- Until `ownership-map` (ri-02) ships, there is no resolver and every repository is in
  solo mode by definition.

The guide owns the definition; `ownership-map` owns detection and must implement this
definition or amend the guide in the same PR.

- *Alternative A*: solo mode iff `owners.yaml` is absent (the literal wording of ri-02's
  acceptance outcome). Rejected: a solo developer who writes an `owners.yaml` naming only
  themselves would suddenly receive team-mode gates for no collaborative benefit.
- *Alternative B*: leave the definition to ri-02. Rejected: the roadmap states this item
  exists to fix the vocabulary before code depends on it.

### D3. Principle-to-implementer mapping is derived from the roadmap

Each principle carries two machine-readable lines, taken by inverting each roadmap
capability's *Serves* line:

- `**Existing:**` — markdown links whose targets are relative paths from
  `docs/guides/` to files or directories in the repository, e.g.
  `[approval.py](../../agent-coordinator/src/approval.py)`. Symbol names (`decided_by`)
  go in prose after the link, never as link targets.
- `**Planned:**` — a comma-separated list of change-ids, each in backticks and nothing
  else in backticks on that line.

Either line may be absent (write `**Existing:** none` / `**Planned:** none`), but every
principle must have at least one entry across the two. Starting mapping (the implementer verifies
against the roadmap and may add existing mechanisms):

| Principle | Existing mechanisms | Planned changes |
|---|---|---|
| P1 Principals are explicit | `agent-coordinator/src/approval.py` (`decided_by`), `agent-coordinator/src/audit.py` | `ownership-map`, `causal-trace-ids`, `attribution-trailers`, `owner-routed-escalation`, `attention-budgets-digests` |
| P2 Own decisions, not labor | `agent-coordinator/src/work_queue.py` | `ownership-map`, `owned-intent-blocks`, `contract-dependencies`, `team-work-queue`, `queue-dispatch-owner-acceptance` |
| P3 Intent is single-writer | `TRUST_POSTURE.md` | `ownership-map`, `owned-intent-blocks`, `team-work-queue`, `reconcile-skill`, `owner-routed-escalation`, `attention-budgets-digests` |
| P4 Contracts before divergence | `skills/plan-feature/` (`contracts/`), `skills/implement-feature/` (`wp-contracts`) | `plan-time-collision-detection`, `coordinator-contract-overlap`, `declare-early-draft-pr`, `contract-dependencies`, `queue-dispatch-owner-acceptance`, `consumer-contract-tests` |
| P5 Concerns are executable | `skills/gen-eval/` | `consumer-contract-tests`, `reconcile-skill` |
| P6 Reconcile insight, not diffs | `skills/parallel-infrastructure/scripts/variant_descriptor.py` (`synthesize_variants`), `skills/audit-choices/` | `reconcile-skill`, `reviewer-shaped-prs` |
| P7 Detect collisions early | `agent-coordinator/src/feature_registry.py` | `plan-time-collision-detection`, `coordinator-contract-overlap`, `declare-early-draft-pr` |
| P8 Attention is scarce | `agent-coordinator/src/event_bus.py` (`classify_urgency`) | `declare-early-draft-pr`, `reviewer-shaped-prs`, `owner-routed-escalation`, `attention-budgets-digests`, `intervention-capture`, `trust-posture-calibration` |
| P9 Traceable; interventions are signals | `agent-coordinator/src/audit.py`, `agent-coordinator/src/handoffs.py`, `skills/session-log/` | `causal-trace-ids`, `attribution-trailers`, `intervention-capture`, `trust-posture-calibration`, `toolkit-consistency` |
| P10 Agents work the queue | `agent-coordinator/src/work_queue.py`, `docs/guides/work-queue-truth-projection.md` | `team-work-queue`, `queue-dispatch-owner-acceptance`, `owner-routed-escalation`, `attention-budgets-digests` |

Where one roadmap capability was split into two roadmap items (for example
*Ownership-routed escalation and attention budgets* into `owner-routed-escalation` and
`attention-budgets-digests`), every resulting change-id inherits the capability's
*Serves* list.

`multiplayer-simulation-harness` serves all principles and is cited once in the guide's
introduction rather than under every principle.

- *Alternative*: cite capability *titles* instead of change-ids. Rejected: titles are not
  machine-checkable; change-ids resolve through `change_dir()` and survive archival.

### D4. No status column; shipped-ness is derived, not written

The per-skill table names the delivering change-id but does not carry a "planned/shipped"
status. The guide states that a team-mode behavior is shipped once its change is archived
and that, once shipped, `openspec/specs/multiplayer-collaboration/spec.md` is normative.

- *Alternative*: a status column, with a test asserting `shipped` iff the change is
  archived. Rejected: the archive commit made by `/cleanup-feature` after merge would turn
  main red on the day each sibling lands — the exact failure mode the OpenSpec path
  stability rule exists to prevent.
- *Alternative*: a status column with no test. Rejected: it drifts silently, and agents
  would read stale "planned" rows as current truth.

### D5. Per-skill table scope

Rows cover exactly the skills or scripts whose behavior a roadmap acceptance outcome
alters: `plan-feature`, `implement-feature`, `validate-feature`, `autopilot`,
`autopilot-roadmap`, `supervise`, `cleanup-feature`, `reconcile` (new, from
`reconcile-skill`), and `install.sh` (from `toolkit-consistency`). `iterate-on-plan` and
`prototype-feature` are deliberately excluded: no roadmap outcome changes their behavior
(`reconcile-skill` reuses `synthesize_variants()` without altering `/prototype-feature`).
Adding a row later requires a sibling change whose outcome alters that skill. Columns:
*Skill*, *Solo mode*, *Team mode*, *Delivered by*. A skill whose solo behavior is
unchanged says "Unchanged" in the *Solo mode* cell; any other *Solo mode* cell may
describe only passive output (D2), never a new prompt, gate, or checkpoint. The guard
test checks cells are non-empty; content accuracy is a review check. The same holds for the `## Modes` definitions of solo and team mode:
the guard test checks the section's required terms and guarantee sentence, not that the
definition is right, so the definition has no test scenario and is checked in review. The implementer derives cells from the
sibling changes' roadmap acceptance outcomes (`roadmap.yaml`), not from scaffold spec
text.

### D6. Authority and precedence

The guide is descriptive. When the guide and a shipped spec disagree, the spec wins and
the guide is corrected in the next change that touches it. Each sibling change that alters
a behavior described in the guide updates the affected guide rows in the same PR. The
guard test enforces only what is mechanical (structure, links, resolvable references).

### D7. Guard test design

`skills/tests/multiplayer-collaboration/test_multiplayer_guide.py`, following the
precedent of `skills/tests/state-artifacts/test_state_artifacts_guide.py`:

- resolve the repository root with `repo_root_from(__file__, 3)`;
- never pin a literal `openspec/changes/<id>/` path (the path-stability guard scans for
  this); change-ids are read from the guide at run time and resolved with `change_dir()`;
- strip any `#fragment` from a link target before resolving it;
- for each principle section (`### P<n>.`), resolve every link target on its
  `**Existing:**` line relative to `docs/guides/` and assert it exists; assert every
  backticked token on its `**Planned:**` line is a change-id that `change_dir()` resolves
  (active or archived), meaning `change_dir(root, id).is_dir()` — `change_dir` returns
  the active path rather than raising when nothing matches; assert the two lines together
  carry at least one entry;
- apply the same change-id check to the *Delivered by* column of the per-skill table and
  the *Addressed by* column of the assumption table: every backticked token in those cells
  is a change-id, and each cell has at least one;
- exercise the change-id resolution helper once against a `tmp_path` repository holding
  only an archived change directory, so the archival scenario is proven rather than
  assumed;
- register the directory in `skills/pyproject.toml` `testpaths` (task 1.2):
  `skills/tests/ci_coverage/test_ci_test_coverage.py` fails for any test directory CI
  does not reach, and running the directory by name bypasses `testpaths`, so the
  omission would otherwise be invisible locally;
- assert section headings by exact text so structural drift fails loudly.

Each assertion message names the principle, row, or link that failed.

### D8. No links into archivable OpenSpec paths

The guide links only to paths that do not move on archival (source files, skills,
`docs/`). It names the roadmap and sibling changes by id in prose or backticks and never
links to `openspec/changes/<id>/` or `openspec/roadmaps/<id>/`, which `/cleanup-feature`
and `/archive-roadmap` relocate. This applies the OpenSpec path stability rule to
documentation; the guard test's `**Existing:**` path check would otherwise fail on the
roadmap's archive day.

- *Alternative*: link to the roadmap proposal for full context. Rejected: the link breaks
  on archival, and the guide restates the content that matters.

## Risks and Trade-offs

- **Coupling to sibling change-ids.** A sibling renamed or superseded via `/refine-roadmap`
  breaks the guard test until the guide is updated. Accepted: that is the drift signal
  the guide needs; the failure message names the stale id.
- **Guide absent from consumer repositories.** `install.sh` does not ship `docs/`, so teams
  installing the toolkit do not get the guide locally. Accepted for this item; installed
  skill text cites principle IDs. Follow-up recorded below.
- **Descriptive content can drift beyond what the test checks** (prose accuracy of team-mode
  cells). Mitigated by D6's same-PR update rule; not mechanically enforced.

## Open Questions

- No sibling roadmap item declares `depends_on: [ri-01]`, so the DAG does not guarantee the
  vocabulary lands before code. Priority 1 and effort S make it likely in practice; a
  `/refine-roadmap` edit adding `ri-01` to `ownership-map` (ri-02) would make it certain.
- Should `install.sh` ship the guide (or a condensed principles card) into consumer
  repositories? Candidate for `toolkit-consistency` (ri-20).
- `ownership-map` (ri-02) must confirm D2's solo-mode definition ("exactly one distinct
  human principal") or amend the guide.
