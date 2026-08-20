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
      an unregistered dir is silently skipped, which is the recorded failure mode.
      Run `--collect-only` with **no path argument**: naming the directory
      bypasses `testpaths` entirely and passes identically whether or not 1.2 landed

- [ ] 1.3 Write failing tests for harness detection — four states, `unknown` for a
      vendor with no declared artifact, and the presence-≠-validity disclaimer
      **Spec scenarios**: "Vendor fully present", "Vendor CLI absent",
      "Vendor has no detectable config location", "Presence is not validity"
      **Design decisions**: D1, D5
      **Dependencies**: 1.1
      **Size**: M
      **Note**: fixtures fake `PATH` and a temp HOME — never read the real `~`

- [ ] 1.3a Write failing tests for roster resolution and network abstinence —
      `AGENTS_YAML` wins over `$COORDINATOR_DIR/agents.yaml`; an unresolvable
      roster exits non-zero naming both paths tried; with `COORDINATION_API_URL`
      pointed at an unroutable host no request is attempted on either path
      **Spec scenarios**: "Agents file resolved from configuration",
      "Agent roster is never fetched over the network"
      **Design decisions**: D1a
      **Dependencies**: 1.1
      **Size**: S
      **Note**: `load_agents_yaml` only honours an explicit path when it
      `.exists()`, so a missing resolved path silently falls through to the
      network branch — the miss must be caught before the call, not after

- [ ] 1.3b Write failing tests for roster filtering — `-local` agents only,
      vendor key is the agent-id stem, one entry per vendor, agents with an
      empty `cli.command` excluded
      **Spec scenarios**: "Remote and command-less agents are excluded"
      **Design decisions**: D1b
      **Dependencies**: 1.1
      **Size**: S
      **Note**: the current roster has `claude-remote` and `codex-remote`; an
      unfiltered pass-through double-counts `claude` and `codex`

- [ ] 1.4 Implement `detect-harnesses` — resolve and verify the roster path
      locally, call `vendor_health.check_all_vendors(path)` unmodified with it,
      filter to `-local`, layer the home-dir artifact table, classify into four
      states in the order cli_missing → unknown → ready/config_missing
      **Spec scenarios**: same as 1.3, 1.3a, 1.3b
      **Design decisions**: D1, D1a, D1b, D5
      **Dependencies**: 1.3, 1.3a, 1.3b
      **Size**: M

- [ ] 1.5 Checkpoint: run tests, review diff, verify scope

## Phase 2 — Settings writer

- [ ] 2.0 Transcribe `SKILL.md:211-232` verbatim into
      `skills/tests/setup-coordinator/legacy_shim.py` as
      `legacy_add_permission(settings_path)` — faithful to the substring guard
      and the `json.dumps(..., indent=2)` whole-file rewrite
      **Design decisions**: D7
      **Dependencies**: 1.1
      **Size**: S
      **Why**: today's behavior is markdown, not code, so "the test must fail
      against current behavior" has no referent until the fragment is
      executable. The shim makes the red phase real and keeps it reproducible

- [ ] 2.1 Write failing tests for the settings writer — one per defect: sibling-key
      preservation, deny-list-only case, idempotent re-run, atomic replace,
      cwd independence, non-canonical input preservation, and collapsing
      individual entries into the wildcard
      **Spec scenarios**: "Wildcard added to a settings file with unrelated keys",
      "Wildcard present only in the deny list", "Idempotent re-run",
      "Settings file is not in canonical JSON form", "Concurrent reader safety",
      "Working directory independence"
      **Design decisions**: D6, D7
      **Dependencies**: 1.1, 2.0
      **Size**: M
      **Note**: parametrize each case over `{legacy_shim, new writer}` and assert
      fail-on-legacy / pass-on-new. Prefer "the unified diff touches only lines
      inside `permissions.allow`" over key-by-key equality — the latter accepts
      reindentation and key reordering

- [ ] 2.2 Implement the settings writer — absolute root resolution, parse-and-check
      `permissions.allow` membership, minimal mutation, `sort_keys=False`,
      indentation inherited from the input file
      **Spec scenarios**: as 2.1
      **Design decisions**: D6
      **Dependencies**: 2.1
      **Size**: M

- [ ] 2.3 Wire `atomic_write_bytes` (**not** `atomic_write_json`) from
      `project-context-runtime` with the guarded inline fallback
      **Spec scenarios**: "Sibling skill unavailable", "Concurrent reader safety",
      "Settings file is not in canonical JSON form"
      **Design decisions**: D2
      **Dependencies**: 2.2
      **Size**: S
      **Note**: `atomic_write_json` routes through `canonical_json_bytes`
      (`sort_keys=True, indent=2`), which re-sorts the live settings file's
      top-level keys and makes the idempotent re-run rewrite the file. Serialize
      locally, hand finished bytes to `atomic_write_bytes`

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

- [ ] 3.4 Extend the 1.3a roster-resolution tests to cover `check` — the same
      resolver is shared by `check` and `detect-harnesses`, so assert the shared
      helper is reused rather than re-deriving precedence per subcommand
      **Spec scenarios**: "Agents file resolved from configuration"
      **Dependencies**: 1.3a
      **Size**: XS
      **Note**: resolution itself is specified and tested in 1.3a; this task
      exists only to pin that `check` does not grow a second copy of it

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
      fragment with a script invocation; add the required tail block
      **Design decisions**: D4, D8, D9
      **Dependencies**: 3.6, 3.7, 3.8
      **Size**: M
      **Note**: the file has no `## Common Rationalizations` / `## Red Flags` /
      `## Verification` block today and the invariant in 4.4 requires all three
      with ≥3 entries each — budget ~25-30 lines for it. Invoke the entrypoint as
      `<skill-base-dir>/scripts/setup_coordinator.py`; a literal
      `skills/setup-coordinator/scripts/...` in an executable context is rejected
      by the payload linter (D8), as are markdown links outside the payload

- [ ] 4.4 Add `test_skill_md.py` importing from `skill_invariants` (not `conftest`)
      **Dependencies**: 4.3
      **Size**: XS
      **Note**: this introduces the tail-block requirement rather than merely
      asserting it — the file has never satisfied it

- [ ] 4.5 Verify the dependency-direction gate reports no `agent-coordinator`
      import from `skills/setup-coordinator/`
      **Spec scenarios**: "Dependency direction enforced"
      **Dependencies**: 3.2
      **Size**: XS

- [ ] 4.5a Run `skills/tests/install_sh/` — the manifest edits in 4.1/4.2 change
      the inputs of a suite this package cannot write to
      **Spec scenarios**: "Entrypoint loads in a consumer payload with no source checkout"
      **Dependencies**: 4.2
      **Size**: XS
      **Note**: `test_consumer_portability.py` executes every `smoke_entrypoints`
      entry inside a freshly installed payload with `PYTHONPATH` stripped, so
      4.2 turns `--help` into a portability gate

- [ ] 4.6 Run `bash skills/install.sh --check` to confirm the standalone payload
      **Dependencies**: 4.2, 4.3
      **Size**: XS

- [ ] 4.7 Checkpoint: run full skills suite, ruff, review diff, verify scope

## Verification

- [ ] V.1 `skills/.venv/bin/python -m pytest skills/tests/setup-coordinator/ -v` — all green
- [ ] V.2 Confirm the new suite appears in collection from the repo pytest config
      **with no path argument** (proves 1.2 landed; an unregistered dir fails open
      and looks identical to zero tests, and naming the dir bypasses `testpaths`)
- [ ] V.3 `cd skills && uv run ruff check .` — clean at the locked ruff version
- [ ] V.4 `openspec validate make-setup-coordinator-script-backed --strict`
- [ ] V.5 Confirm `SKILL.md` line count is within the 120-150 target
- [ ] V.6 Confirm no test reads or writes the operator's real `~` or the repo's own
      `.claude/settings.local.json`
- [ ] V.7 Confirm every legacy-shim parametrization fails on the shim and passes on
      the new writer — a case that passes on both proves nothing
- [ ] V.8 `detect-harnesses --json` validates against
      `contracts/harness-report.schema.json`, run with an explicit `AGENTS_YAML`
      and the same interpreter as the suite (system `python3` has no `pyyaml`)
