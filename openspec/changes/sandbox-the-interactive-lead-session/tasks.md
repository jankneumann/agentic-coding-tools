# Tasks: sandbox-the-interactive-lead-session

## 1. Settings

- [x] 1.1 Write failing tests for the sandbox block of the real settings file
  - File: `skills/tests/session-bootstrap/test_lead_session_sandbox_settings.py`
  - Spec scenarios: Sandbox and auto-allow are on; A host without sandbox prerequisites still works; Toolchain caches are writable; Credential locations are denied; Sibling checkouts are denied and the project is not; Outward commands are excluded; Git hosts are not reachable from inside the sandbox; Network allowlist is limited to registries and the coordinator
  - Design: D1, D2, D3, D4, D9
  - Size: M
- [x] 1.2 Write failing tests for the allow list
  - Same file. Spec scenarios: Readers and interpreters are absent; The list is shorter; Excluded fetch commands stay promptless; Ask rules are content-scoped
  - Design: D5
  - Size: S
- [x] 1.3 Add the `sandbox` block to `.claude/settings.json`
  - Depends on: 1.1
  - Size: S
- [x] 1.4 Remove reader and interpreter rules from `permissions.allow`
  - Adds `git fetch *` and `git pull *`. Depends on: 1.2
  - Size: S

Checkpoint: `skills/.venv/bin/python -m pytest skills/tests/session-bootstrap -q` passes; settings file is valid JSON.

## 2. Irreversible set

- [x] 2.1 Write the test that enumerates the irreversible set
  - File: `skills/tests/session-bootstrap/test_irreversible_set_gated.py`
  - Spec scenarios: Each class has a gate that survives auto-allow; No gated command is also allowed outright
  - Design: D6
  - Size: M
- [x] 2.2 Close any gap the enumeration finds with a deny or content-scoped ask rule
  - Depends on: 2.1. No change to `irreversible_guard.py`.
  - Size: S

Checkpoint: both test files pass; `test_irreversible_guard.py` still passes.

## 3. Probe

- [x] 3.1 Write failing tests for the probe
  - File: `skills/tests/session-bootstrap/test_sandbox_probe.py`
  - Spec scenarios: Probe is skipped where isolation is provided; Probe reports an unenforced denial; Probe does not leak content; Probe targets come from the settings file; The denial is demonstrated on a sandboxed host (with a faked filesystem)
  - Design: D7, D8
  - Size: M
- [x] 3.2 Implement `skills/session-bootstrap/scripts/sandbox_probe.py`
  - Depends on: 3.1
  - Size: M
- [x] 3.3 Sync runtime skill copies
  - `bash skills/install.sh --mode rsync --deps none --python-tools none`. Depends on: 3.2
  - Size: S

Checkpoint: probe tests pass; running the probe in the cloud container prints `skipped`.

## 4. Guidance

- [x] 4.1 Write failing tests for the documentation
  - File: `skills/tests/session-bootstrap/test_lead_session_sandbox_docs.py`
  - Spec scenarios: Claude-specific guidance matches the settings; Guide covers prerequisites and rollback
  - Size: S
- [x] 4.2 Rewrite the matchable-Bash section of `CLAUDE.md`
  - Depends on: 4.1
  - Size: S
- [x] 4.3 Write `docs/guides/lead-session-sandbox.md`
  - Includes the host verification checklist from design.md. Depends on: 4.1
  - Size: S

Checkpoint: full `skills/tests/session-bootstrap` suite passes; `openspec validate sandbox-the-interactive-lead-session --strict` passes.
