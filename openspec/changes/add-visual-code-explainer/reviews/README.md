# Review artifacts

Per-round vendor checkpoints live under `../.review-cache/`:
- `round-1/` — PLAN_REVIEW evidence
- `round-1-implementation/` — IMPL_REVIEW evidence (slimmed; pi raw archived outside the tree)

The gate-time ledger lives under `../.review-ledger/`.
Do not treat intermediate `converge-result` snapshots as the plan or implementation contract;
OpenSpec proposal/design/specs/tasks/work-packages and the skill/atlas sources are authoritative.
