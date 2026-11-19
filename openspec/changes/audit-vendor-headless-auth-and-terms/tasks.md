# Tasks: audit-vendor-headless-auth-and-terms

## 1. Audit table

- [x] 1.1 Write failing tests for the table's invariants
  - File: `skills/tests/vendor-status/test_vendor_auth_audit_table.py`
  - Spec scenarios: Every vendor has every lane; A verdict carries its governing sentence; An unaddressed lane lists what was searched; The table is dated; Prohibited or unaddressed unattended use is marked; Every mechanics field has an evidence level; Observed is claimed only with a host and date; Documented is claimed only with a source
  - Design: D1, D2, D3, D4, D5
  - Size: S
- [x] 1.2 Research terms and mechanics for the four vendors against live pages
  - Four research sub-agents, one per vendor. Size: M
- [x] 1.3 Write `docs/guides/vendor-auth-audit.yaml`
  - Depends on: 1.1, 1.2
  - Size: M

Checkpoint: `skills/.venv/bin/python -m pytest skills/tests/vendor-status -q` passes.

## 2. Observation script

- [x] 2.1 Write failing tests for the observation script
  - File: `skills/tests/vendor-status/test_observe_vendor_auth.py`
  - Spec scenarios: Metadata is reported without content; A refresh write is detected; An unknown vendor is refused
  - Design: D6
  - Size: S
- [x] 2.2 Implement `skills/vendor-status/scripts/observe_vendor_auth.py` and sync runtime copies
  - Depends on: 2.1
  - Size: S

Checkpoint: both test files pass.

## 3. Guide and corrections

- [ ] 3.1 Write failing tests for the guide and the corrected statements
  - File: `skills/tests/vendor-status/test_vendor_auth_audit_docs.py`
  - Spec scenarios: The guide covers every vendor and lane; The Claude strategy note records its verification; The factory proposal no longer cites the wrong reason
  - Size: S
- [ ] 3.2 Write `docs/guides/vendor-auth-audit.md` and index it
  - Depends on: 1.3, 3.1
  - Size: M
- [ ] 3.3 Correct the quotes in `claude-auth-strategy.md` and add the verification note
  - Depends on: 1.2
  - Size: S
- [ ] 3.4 Correct `docs/proposals/factory-local-cloud-split.md`
  - Depends on: 1.3
  - Size: S

Checkpoint: all three test files pass; `openspec validate audit-vendor-headless-auth-and-terms --strict` is valid.

## 4. Host observation (operator)

- [ ] 4.1 Run the observation script and the host procedure for each vendor on an operator host, and raise the evidence levels in the table
  - Cannot be done in the cloud container: three CLIs are absent and none is logged in. The roadmap item stays open until this is done.
  - Size: S
