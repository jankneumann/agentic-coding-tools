# Tasks — make-setup-coordinator-script-backed

Sizing per the plan-feature Task Sizing Reference. No task exceeds M.
Test tasks precede the implementation they verify (TDD red → green).

## Phase 1 — Scaffolding and detection

- [ ] 1.1 Create `skills/tests/setup-coordinator/conftest.py` — `sys.path` insert of
      `parents[2]/"setup-coordinator"/"scripts"`; **no** `__init__.py` in the dir
      **Spec scenarios**: setup-coordinator "Suite is collected by CI"
      **Design decisions**: D7
      **Dependencies**: None
      **Size**: XS

- [ ] 1.2 Register `"tests/setup-coordinator"` in `testpaths` in `skills/pyproject.toml`
      **Spec scenarios**: setup-coordinator "Suite is collected by CI"
      **Dependencies**: 1.1
      **Size**: XS
      **Verify**: collection must list the new suite *before* any test exists —
      an unregistered dir is silently skipped, which is the recorded failure mode

- [ ] 1.3 Write failing tests for harness detection — four states, `unknown` for a
      vendor with no declared artifact, and the presence-≠-validity disclaimer
      **Spec scenarios**: "Vendor fully present", "Vendor CLI absent",
      "Vendor has no detectable config location", "Presence is not validity"
      **Design decisions**: D1, D5
      **Dependencies**: 1.1
      **Size**: M
      **Note**: fixtures fake `PATH` and a temp HOME — never read the real `~`

- [ ] 1.4 Implement `detect-harnesses` — call `vendor_health.check_all_vendors()`
      unmodified, layer the home-dir artifact table, classify into four states
      **Spec scenarios**: same as 1.3
      **Design decisions**: D1, D5
      **Dependencies**: 1.3
      **Size**: M

- [ ] 1.5 Checkpoint: run tests, review diff, verify scope

## Phase 2 — Settings writer

- [ ] 2.1 Write failing tests for the settings writer — one per defect: sibling-key
      preservation, deny-list-only case, idempotent re-run, atomic replace,
      cwd independence, and collapsing individual entries into the wildcard
      **Spec scenarios**: "Wildcard added to a settings file with unrelated keys",
      "Wildcard present only in the deny list", "Idempotent re-run",
      "Concurrent reader safety", "Working directory independence"
      **Design decisions**: D6, D7
      **Dependencies**: 1.1
      **Size**: M
      **Note**: each test must fail against the current `SKILL.md:211-232` behavior

- [ ] 2.2 Implement the settings writer — absolute root resolution, parse-and-check
      `permissions.allow` membership, minimal mutation
      **Spec scenarios**: as 2.1
      **Design decisions**: D6
      **Dependencies**: 2.1
      **Size**: M

- [ ] 2.3 Wire `atomic_write_json` from `project-context-runtime` with the guarded
      inline fallback
      **Spec scenarios**: "Sibling skill unavailable", "Concurrent reader safety"
      **Design decisions**: D2
      **Dependencies**: 2.2
      **Size**: S

- [ ] 2.4 Checkpoint: run tests, review diff, verify scope

## Phase 3 — CLI surface

- [ ] 3.1 Write failing tests for the CLI contract — subcommand dispatch, exit-code
      discipline, `--json` exclusivity, usage-on-no-subcommand
      **Spec scenarios**: "Subcommand dispatch", "Machine-readable output",
      "No subcommand supplied"
      **Dependencies**: 1.1
      **Size**: S

- [ ] 3.2 Implement the argparse surface — `main(argv=None) -> int`,
      `cmd_*(args) -> int` handlers, per-subcommand `--json` with
      `dest="json_output"`
      **Spec scenarios**: as 3.1
      **Dependencies**: 3.1, 1.4, 2.2
      **Size**: M

- [ ] 3.3 Write failing tests for profile resolution — `--profile` precedence over
      `COORDINATOR_PROFILE`, default `local`
      **Dependencies**: 1.1
      **Size**: S

- [ ] 3.4 Write failing tests for `agents.yaml` location resolution — `AGENTS_YAML`
      precedence, `$COORDINATOR_DIR` fallback, non-zero exit when neither resolves
      **Spec scenarios**: "Agents file resolved from configuration"
      **Dependencies**: 1.1
      **Size**: S

- [ ] 3.5 Checkpoint: run tests, review diff, verify scope

- [ ] 3.6 Implement `check` — profile resolution against the YAML directly plus
      precondition checks
      **Spec scenarios**: "Agents file resolved from configuration"
      **Design decisions**: D3
      **Dependencies**: 3.3, 3.4, 3.2
      **Size**: M

- [ ] 3.7 Implement `report` — capability-flag summary rendering
      **Dependencies**: 3.6
      **Size**: S

- [ ] 3.8 Implement `configure` — settings write only; emit the `make mcp-setup` /
      `hooks-setup` commands as reported next steps rather than running them
      **Design decisions**: D3
      **Dependencies**: 3.2, 2.3
      **Size**: S

- [ ] 3.9 Checkpoint: run tests, review diff, verify scope

## Phase 4 — Manifest, SKILL.md, and gates

- [ ] 4.1 Add `parallel-infrastructure` and `project-context-runtime` to
      `cross_skill_dependencies["setup-coordinator"]` in `skills/install-manifest.json`
      **Spec scenarios**: "Sibling skill unavailable"
      **Design decisions**: D2
      **Dependencies**: 3.2
      **Size**: XS
      **Note**: single edit to one list — the "and" in this title is one outcome,
      not two, so the splitting heuristic does not apply

- [ ] 4.2 Register the entrypoint in `smoke_entrypoints` with `args: ["--help"]`
      **Dependencies**: 4.1
      **Size**: XS

- [ ] 4.2a Checkpoint: run tests, review diff, verify scope

- [ ] 4.3 Rewrite `SKILL.md` to ~120-150 lines — keep the transport table,
      when-to-use-HTTP guidance, and troubleshooting list; replace every bash
      fragment with a script invocation
      **Design decisions**: D4
      **Dependencies**: 3.4, 3.5
      **Size**: M

- [ ] 4.4 Add `test_skill_md.py` importing from `skill_invariants` (not `conftest`)
      **Dependencies**: 4.3
      **Size**: XS

- [ ] 4.5 Verify the dependency-direction gate reports no `agent-coordinator`
      import from `skills/setup-coordinator/`
      **Spec scenarios**: "Dependency direction enforced"
      **Dependencies**: 4.1
      **Size**: XS

- [ ] 4.6 Run `bash skills/install.sh --check` to confirm the standalone payload
      **Dependencies**: 4.2, 4.3
      **Size**: XS

- [ ] 4.7 Checkpoint: run full skills suite, ruff, review diff, verify scope

## Verification

- [ ] V.1 `skills/.venv/bin/python -m pytest skills/tests/setup-coordinator/ -v` — all green
- [ ] V.2 Confirm the new suite appears in collection from the repo pytest config
      (proves 1.2 landed; an unregistered dir fails open and looks identical to zero tests)
- [ ] V.3 `cd skills && uv run ruff check .` — clean at the locked ruff version
- [ ] V.4 `openspec validate make-setup-coordinator-script-backed --strict`
- [ ] V.5 Confirm `SKILL.md` line count is within the 120-150 target
- [ ] V.6 Confirm no test reads or writes the operator's real `~` or the repo's own
      `.claude/settings.local.json`
