# Implementation Findings — define-evidence-ledger-schema-with-immutable-facts

## IMPL_ITERATE iteration 1 (inline; no sub-agent adapter in dispatched child)

| # | Type | Criticality | Finding | Resolution |
|---|------|-------------|---------|------------|
| 1 | correctness | medium | `load_ledger` caught only `OSError` on read. A non-UTF-8 file raised `UnicodeDecodeError` (a `ValueError`), so the CLI crashed with exit 1, which the contract (D9) reserves for "violations found". | `UnicodeDecodeError` now becomes `LedgerLoadError`, which exits 2. Regression test `test_non_utf8_file_exits_two` added first and seen failing. |
| 2 | robustness | low | PyYAML silently keeps the last value for a duplicated mapping key, so a hand-edited YAML ledger with a repeated key loses data without a violation. | Accepted for this change. JSON has the same semantics, so YAML/JSON parity holds. Ledgers are machine-written (ri-03, ri-05). Candidate follow-up if hand-editing becomes common. |
| 3 | determinism | info | Violations sort by path string, so `/facts/10` precedes `/facts/2`. | No change. The order is deterministic, which is what D6 and the CLI test require. Numeric order is not part of the contract. |

No critical or high findings remain. Converged for review.

## IMPL_REVIEW (inline, single vendor `claude_code`; quorum 1 per cloud policy `cloud-container-single-vendor-2026-10-09`)

| # | Type | Criticality | Finding | Resolution |
|---|------|-------------|---------|------------|
| R1 | spec-coverage | info | All 22 scenarios across the 6 requirements map to a test: 19 fixtures named `<code>__<case>`, 8 revision fixtures, the CLI exit-code tests and the `change_dir`-based drift test. | None needed. |
| R2 | contracts | info | The canonical, install_assets and contracts copies of the schema are byte-identical (`cmp`), and `test_schema_copies.py` enforces it. | None needed. |
| R3 | scope | info | Every write is inside the `write_allow` of its work package. No matrix, gate or collection logic leaked in from ri-02 or ri-05. | None needed. |
| R4 | quality | info | `ruff check`, `ruff format --check` and `mypy --strict` are clean on the new module. The skill is registered in the install manifest, testpaths (`ci_coverage` passes) and the workflow guide. | None needed. |

Verdict: **converged**. There are no critical, high or medium findings.
