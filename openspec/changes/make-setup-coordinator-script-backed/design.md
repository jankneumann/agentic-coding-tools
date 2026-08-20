# Design — make-setup-coordinator-script-backed

## Context

`setup-coordinator` is a 359-line `SKILL.md` with no `scripts/` directory and no
test suite. The work is to extract its *deterministic* half into one tested
entrypoint and leave its *narrative* half as narration. This is not a
bash-to-Python translation: there is no runnable unit to port, because the bash
fragments are model instructions inside code fences, not executables.

## Decisions

### D1 — Hybrid detection: reuse `vendor_health` unmodified, layer presence locally

`vendor_health.check_all_vendors()` already covers CLI-on-PATH (`shutil.which`)
and env-var credential resolution, iterating `agents.yaml`. The missing layer is
home-directory config artifacts.

The module is **owned by the `vendor-ux` spec** across 8 requirements, including
`Health Check Dimensions` (which specifies a model-access probe) and `Probe
Cost`. It also carries an explicit inline constraint at lines 99-101: *"D6 still
holds: this is env-var resolution, not an inference probe."*

Modifying it would drag this change into that spec's territory and force a
second delta reconciling presence-only detection with a probe-oriented
requirement set. Calling it unmodified costs nothing and keeps the blast radius
inside `setup-coordinator`.

**Rejected**: extending `vendor_health` (Approach 2) — see proposal.

### D2 — Import `atomic.py` from `project-context-runtime`, with inline fallback

`skills/project-context-runtime/scripts/atomic.py` provides
`atomic_write_json(target, data) -> (changed, sha256)` with tmp → fsync →
`os.replace` → parent-dir fsync, plus byte-identical no-op detection that
returns `False` without touching the filesystem. That no-op behavior directly
implements the idempotency scenario in the spec, so reusing it removes code
rather than adding it.

`skills/refresh-architecture/scripts/arch_utils/provenance.py:43-55` is the
precedent: a guarded `from atomic import ...` with an inline fallback definition
when the runtime is not bundled. This change follows it exactly.

Two constraints discovered during planning:
- Import the `atomic` module **by flat name** after a `sys.path` insert, not via
  the package facade — `skills/tests/project-context-runtime/test_cross_process.py:82-84`
  asserts `atomic_write_json` is deliberately *not* re-exported by `__init__.py`.
- `cross_skill_dependencies["setup-coordinator"]` currently reads
  `["coordination-bridge"]` and must gain `parallel-infrastructure` and
  `project-context-runtime`.

**Rejected**: a private `_atomic_write_json` (the `playwright-validator`
precedent). Defensible for packageability, but it would reimplement no-op
detection that `atomic.py` already has and already tests.

### D3 — `configure` mutates only the settings file

MCP registration and hook installation stay as `make -C "$COORDINATOR_DIR"
mcp-setup` / `hooks-setup` invocations narrated in `SKILL.md`. They are already
a public interface, and wrapping them would couple a skill that must work
*without* `agent-coordinator/` to a coordinator checkout.

This keeps exactly one mutating operation in the script, which is what makes the
atomicity and minimal-diff requirements checkable.

### D4 — `SKILL.md` reduced to ~120-150 lines

Knowledge content stays: the transport-model table, the when-to-use-HTTP
guidance, and the troubleshooting list are model-facing knowledge that a script
cannot carry. Improvised glue goes. Target is a file short enough that a model
follows every step, without discarding the reference value.

### D5 — Four-state detection model, `unknown` is not a failure

Observed on macOS during planning:

| Vendor | CLI | Config artifact | State |
|---|---|---|---|
| claude | `claude` | `~/.claude.json`, `~/.claude/` | detectable |
| codex | `codex` | `~/.codex/auth.json` | detectable |
| grok | `grok` | `~/.grok/auth.json` | detectable |
| pi | `pi` | `~/.pi/agent/auth.json` | detectable |
| antigravity | `agy` | none found at any depth ≤ 3 | **not detectable** |

Antigravity is a VS Code fork that keeps credentials outside its dotfile
directory, consistent with there being no `agy login`. Collapsing "undetectable"
into `config_missing` would make the tool emit a remediation instruction for a
command that does not exist, every single run.

Hence four states — `ready`, `cli_missing`, `config_missing`, `unknown` — with
`unknown` reported honestly rather than guessed. The artifact paths are **data,
not code**: a table keyed by vendor, so adding a vendor is a data edit.

### D6 — Minimal-diff settings writes, and why the deny-list bug is the dangerous one

Three of the four defects (relative path, whole-file reformat, non-atomic write)
produce *visible* wrong behavior. The fourth does not: the guard
`grep -q 'mcp__coordination__\*'` matches the string anywhere in the file, so a
`deny` entry causes the tool to conclude the permission is already allowed and
skip the add — reporting success while doing nothing.

Silent failure is the defect class this change exists to remove, so the fix is
structural: parse the JSON and check membership **in the `allow` list
specifically**, never a textual scan of the file.

Minimal-diff is asserted directly: load, mutate only `permissions.allow`,
compare every other top-level key for byte-identity. The live repository file
has a `disabledMcpjsonServers` sibling key that makes this testable with a
realistic fixture.

### D7 — Tests must construct the failure cases, not observe them

The repository's own `.claude/settings.local.json` has only an `allow` list and
no `deny` key, so the deny-list defect is **latent**. A test asserting against
the real file would pass vacuously and prove nothing.

Every defect gets a fixture that reproduces it in `tmp_path`. Per the repo's
"gates must fail before work" convention, each test must fail against the
current shell-fragment behavior — otherwise it is decoration.

## Risks

| Risk | Mitigation |
|---|---|
| `atomic.py` absent in an installed payload | Inline fallback per the `refresh-architecture` precedent; covered by a spec scenario |
| New test dir invisible to CI | `testpaths` registration is its own task with its own verification; the repo has two recorded incidents of exactly this |
| Flat-module name collision across skills | Entrypoint is named `setup_coordinator.py`, not a generic `config.py`/`models.py` |
| `__init__.py` shadowing in the test dir | Suite omits `__init__.py`, following `skills/tests/worktree/` |
| Detection drifts from `vendor_health` | Detection calls it rather than reimplementing; only the home-dir layer is local |

## Notes on validation coverage

`parallel_zones.py --validate-packages` will be run but makes **no claim** about
this change: `parallel_zones.json` is keyed on code symbols and contains zero
`skills/` entries. It is reported as *not applicable*, not as passing evidence.
