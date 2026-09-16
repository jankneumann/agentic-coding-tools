# Plan Findings — add-visual-code-explainer

## Iteration 1 (2026-09-16) — autopilot-plan-iterate

`openspec validate add-visual-code-explainer --strict` passed before and after fixes.

### Findings

| # | Dimension | Criticality | Finding | Resolution |
|---|---|---|---|---|
| 1 | consistency / assumptions | high | D2 and proposal Selected Approach claimed `run_architecture.py --check` uses exit `2` for drift. Live contract: exit `0` fresh, exit `1` when provenance is not fresh. Exit `2` belongs to `build_atlas.py --check` (stale HTML page). | Corrected D2, D4 aside, proposal Selected Approach, session-log decision 2. Spec already used "exit 0 only / non-zero". |
| 2 | consistency / clarity | medium | D5 ungrounded template `(graph <stale\|absent\|check failed>)` omitted `symbol not in graph` and did not define disclosure for non-call-tree forms; "copies footer verbatim" conflicted with `Grounding:` + `;` vs footer `·`. | Expanded D5 reason set; clarified footer→disclosure mapping; added skill-workflow scenario "Non-call-tree form is not graph-backed"; updated tasks 2.2/2.5. |
| 3 | consistency / parallelizability | medium | `work-packages.yaml` package descriptions omitted tasks 1.5, 2.7–2.8, and 3.5 even though `tasks.md` and merge depends_on require them. | Widened WP task ranges to 1.1–1.5, 2.1–2.8, 3.1–3.5; bumped `plan_revision` to 2. |
| 4 | consistency / clarity | medium | Proposal "What Changes" still promised behavioural scenarios in "replay-harness shape"; D7 already specified deterministic CI checks + optional harness. | Aligned proposal Tests bullet with D7. |
| 5 | completeness | medium | Session-log open question still asked about `show-me` vs `explain-code` after Gate 2 rename; Context still said `skills/show-me/`. | Closed OQ; fixed Context naming. |

### Left as low (no churn)

- Proposal NFR node/edge counts (1,903 / 1,199) slightly behind current committed graph (~1,953 / 1,228); timing NFR still uses the committed graph.
- `tiny_graph` has no cycle/import edges by default; task 1.1 already builds derived fixtures.

### Outcome

Medium+ findings fixed in plan artifacts only. Ready for PLAN_REVIEW.

## PLAN_REVIEW round 1 (2026-09-16) — adjudication

Multi-vendor converge (antigravity, claude_code, codex, grok; pi failed JSON)
returned `adjudication_required` for 6 high unconfirmed judgment findings
(blocking_count 0; 1 confirmed medium). Conductor adjudication applied:

| Cluster | Finding ids | Resolution |
|---|---|---|
| Disclosure vs ask/redirect | 1, 6, 12 | Exempt clarification + whole-repo redirect from `Grounding:`; disclosure applies to sketching replies only |
| Fixture "node ids" wording | 13 | Assert printed nodes match fixture `(name, file)`; format does not emit ids |
| Missing atlas WHEN/THEN | 3 (confirmed), 14 | Added scenarios: default hops/direction, hops clamp, `--no-coverage`, exit 1; task 1.1 covers them |
| D7 enum / footer mapping | 17 | Strengthened D7/task 2.2/proposal Tests for closed reason tokens + footer→disclosure mapping |
| stale vs check-failed | 5, 7, 20 | First-match reason order in D5/spec (`absent` → `check failed` → `stale` → …) |
| Coverage substring phrasing | 9, 16 | Spec aligned with D5: copy after `· ` / before trailing ` covered`, re-append |

Artifacts updated; `plan_revision` → 3. Re-run converge.

## PLAN_REVIEW round 2 (2026-09-16) — adjudication

Second converge (5/5 vendors) again returned `adjudication_required` for 3
single-vendor high judgment findings (0 confirmed, 0 blocking):

| Finding | Resolution |
|---|---|
| Narrow-question vs ambiguous WHEN overlap | Qualify narrow-question scenario to resolvable targets only |
| "SHALL NOT open any file" vs read-only grounding | Permit read-only graph/source access; forbid create/modify/browser side effects |
| Residual atlas SHALL without WHEN/THEN | Added footer shape, resolution precedence, unique-name, direction-both scenarios; fixed `(+n more)` hop-depth wording |
| Frontmatter/distribution SHALL gaps (medium) | Added triggers/category/tail and portable/deps/`skill-base-dir` scenarios |

Ledger items from rounds 1–2 retired after adjudication (`retired` is not
reopened on merge). `plan_revision` → 4. Re-run converge.

## PLAN_REVIEW round 3 (2026-09-16) — adjudication

| Finding | Resolution |
|---|---|
| Stale slimmed `reviews/converge-result.json` contradicted plan-findings | Removed process snapshot from the change tree; reviews/README.md points at `.review-cache` |
| Task 1.1 omitted four new atlas scenarios | Extended task 1.1 test scope + Spec scenarios list |

`plan_revision` → 5. Re-run converge.

## PLAN_REVIEW round 4 (2026-09-16) — adjudication

| Finding | Resolution |
|---|---|
| `--tree` spawn/unexpected exit undefined after fresh `--check` | Map to `graph check failed` + source fallback; new scenario |
| `form not graph-backed` claimed without requiring source read | Require source read before non-call-tree sketches |
| proposal.md still said every answer / any non-zero = stale | Aligned What Changes + Coverage honesty NFR with D5 |

`plan_revision` → 6. Re-run converge.

## PLAN_REVIEW converged (2026-09-16)

`converge()` returned `converged=True` after round-4 adjudication fixes
(proposal/D5/spec/task alignment). Quorum met; no blocking ledger items;
no adjudication leftovers. Ready for IMPLEMENT.
