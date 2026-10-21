# Plan Findings — define-evidence-ledger-schema-with-immutable-facts

## PLAN_ITERATE iteration 1 (inline; no sub-agent adapter in dispatched child)

| # | Type | Criticality | Finding | Resolution |
|---|------|-------------|---------|------------|
| 1 | consistency | medium | `signal_same_fact` is unreachable: a fact cannot have both roles, so a self-paired signal always fails a `signal_role_mismatch` check first. | Removed the code from design D6 and contracts/README. tasks.md 2.5 notes the subsumption. |
| 2 | testability | medium | `replacement_is_target` and `reverify_mutated` had no spec scenario. | Added two scenarios to specs/evidence-ledger/spec.md and referenced them from tasks 2.2 and 3.1. |
| 3 | parallelizability | low | The wp-packaging and wp-integration verification ran the whole `tests/install_sh` directory, which is slow and unrelated to this change. | Narrowed to `tests/install_sh/test_install_manifest.py`. Bumped plan_revision to 2. |

No critical or high findings remain. The plan is converged for review.

## PLAN_REVIEW (inline, single vendor `claude_code`; quorum 1 per cloud policy `cloud-container-single-vendor-2026-10-09`)

| # | Type | Criticality | Finding | Resolution |
|---|------|-------------|---------|------------|
| R1 | correctness | high | `yaml.safe_load` resolves unquoted ISO timestamps to `datetime`. A hand-written or ri-03-generated `evidence-ledger.yaml` would then fail `type: string`, and YAML and JSON would diverge. | D8 now specifies a SafeLoader without the timestamp resolver. Added the spec scenario "Unquoted YAML timestamps stay strings" and referenced it from task 2.1. |
| R2 | scope | info | Confirmed that the matrix, root_cause gates and necessity check are absent from the specs and tasks (deferred to ri-02), and that `root_cause` exists only as a status value. | None needed. |
| R3 | contracts | info | Every schema object sets `additionalProperties: false`. The `data` payload is intentionally open. The drift test covers all three copies. | None needed. |

Verdict: **converged**. There are no open critical or high findings.
