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

### D1a — This skill resolves `agents.yaml` itself and passes an explicit path

"Call it unmodified" is not "call it with no arguments". `load_agents_yaml`
(`vendor_health.py:110-155`) resolves in this order:

```
AGENTS_YAML          (only if set AND the file exists)
  → HTTP GET $COORDINATION_API_URL/agents/dispatch-configs   ← network I/O
  → $CWD/agent-coordinator/agents.yaml                       ← cwd-dependent
  → {}                                                       ← empty, no error
```

That chain contradicts this change's spec three ways: there is **no
`$COORDINATOR_DIR/agents.yaml` step at all**, it silently reaches the network,
and it fails *open* — an unresolvable roster yields an empty report and exit 0
rather than the required non-zero "missing input". The sharpest edge: the
explicit-path branch is guarded by `explicit.exists()`, so passing a path that
does **not** exist falls straight through to the network branch.

So `setup_coordinator.py` owns resolution:

1. Resolve `AGENTS_YAML`, else `$COORDINATOR_DIR/agents.yaml`.
2. Verify the resolved path exists and is readable; if not, report both paths
   tried and return non-zero. Never delegate the miss.
3. Call `check_all_vendors(resolved_path)` with the verified path.

`check_all_vendors` is still called unmodified — only the argument changes — and
the network branch becomes unreachable by construction, because step 2
guarantees `explicit.exists()`. A test SHALL set `COORDINATION_API_URL` to an
unroutable value and assert no request is attempted on either the resolve-ok or
the resolve-fail path.

### D1b — `-local` agents only; the vendor key is the agent-id stem

`check_all_vendors` returns every agent carrying a `cli` block. In the current
roster that is seven entries, including `claude-remote` and `codex-remote`,
which are dispatch destinations rather than harnesses installed on this host.
Reporting them would double-count `claude` and `codex` and would assert
host-local presence about a remote runner.

The rule, stated once so implementation and contract cannot drift:

- Include an agent iff its `agent_id` matches `<vendor>-local` **and** its
  `cli.command` is a non-empty string.
- `vendor` is `agent_id` with the `-local` suffix removed.
- `agent_type` is the agent's `type` field (`VendorHealth.vendor_type`).
- Every other agent is skipped silently — not an error, and not `unknown`.

The non-empty-command guard is load-bearing: `check_vendor` defaults a missing
command to `""`, while the contract declares `cli_command` with `minLength: 1`,
so such an agent would emit a report that fails its own schema.

### D2 — Import `atomic.py` from `project-context-runtime`, with inline fallback

`skills/project-context-runtime/scripts/atomic.py` provides the durability
primitive this change needs: tmp file → fsync → `os.replace` → parent-dir fsync,
plus byte-identical no-op detection that returns `False` without touching the
filesystem.

**Import `atomic_write_bytes`, not `atomic_write_json`.** This is the one
correction that matters most in this design, because the obvious choice is
wrong:

`atomic_write_json` serializes through `canonical_json_bytes`, which is
`json.dumps(..., sort_keys=True, indent=2)` (`atomic.py:31-40`). Canonical form
is exactly right for the generated manifests that module was built for, and
exactly wrong here. Applied to `.claude/settings.local.json` it would:

1. **Re-sort every top-level key** — the live file's insertion order is
   `["permissions", "disabledMcpjsonServers"]`; sorted order is the reverse. So
   `atomic_write_json` *is* the whole-file reformat this change exists to
   remove. It would trade defect #2 for a tidier version of defect #2, and the
   spec bullet "preserve all unrelated keys, values, and **ordering**" would be
   violated by the fix itself.
2. **Break the idempotency scenario.** Canonical bytes for the live file are
   not equal to the live file's bytes. So a re-run against a file that already
   carries the wildcard would still rewrite it — `changed=True` — contradicting
   "SHALL NOT be modified". The no-op detection that D2 was chosen for only
   fires when the input already happens to be canonical, which is the case
   this skill will almost never meet, because Claude Code writes that file, not
   this skill.

The seam is therefore at bytes, not at objects: `setup_coordinator.py` does its
own `json.dumps` preserving the parsed insertion order (`sort_keys=False`) and
the file's existing indent, then hands the finished bytes to
`atomic_write_bytes`. All the durability and no-op value of the sibling module
is retained; only the canonicalizer is left behind. `refresh-architecture`
imports at exactly this granularity — `atomic_write_bytes` and
`canonical_json_bytes` as separate names — which is why that seam exists.

`skills/refresh-architecture/scripts/arch_utils/provenance.py:43-55` is the
precedent for **the wiring only** — a guarded `from atomic import ...` with an
inline fallback definition when the runtime is not bundled. Copy that shape.

**Do not copy its fallback body.** `provenance.py:55-61` defines a fallback
named `_atomic_write_bytes` whose final statement is:

```python
target.write_bytes(payload)
```

That is a plain in-place write. The name promises atomicity the body does not
deliver — acceptable for a provenance digest, but not here: reproducing it
would reintroduce defect #3 (non-atomic write) on precisely the path this
change's spec declares supported, and it would do so under a name that reads as
if the defect were fixed. That is the same shape as the deny-list bug: a guard
whose name asserts a property its implementation lacks.

The inline fallback in this change MUST perform a real
tmp-write → `fsync` → `os.replace` sequence. A fallback is a degradation in
*dependency availability*, never in *correctness guarantees* — the spec
requires atomicity on every path, not only when a sibling skill happens to be
installed.

Two constraints discovered during planning:
- Import the `atomic` module **by flat name** after a `sys.path` insert, not via
  the package facade — `skills/tests/project-context-runtime/test_cross_process.py:82-84`
  asserts `atomic_write_json` is deliberately *not* re-exported by `__init__.py`.
- `cross_skill_dependencies["setup-coordinator"]` currently reads
  `["coordination-bridge"]` and must gain `parallel-infrastructure` and
  `project-context-runtime`.

**Rejected**: a private `_atomic_write_bytes` (the `playwright-validator`
precedent). Defensible for packageability, but the guarded-import-with-fallback
shape already gives packageability without a second copy of `os.replace`
sequencing.

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

Absence from that table is itself meaningful and must not be an error. A vendor
present in `agents.yaml` but not in the table has *no declared artifact*, which
is the definition of `unknown` — so a roster gaining a sixth harness degrades to
an honest "we don't know" rather than to a crash or a spurious
`config_missing`. State precedence is fixed: `cli_missing` is evaluated first
(it is decidable without the table at all), then `unknown` when no artifact is
declared, then `ready`/`config_missing` from the artifact check.

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

Concretely, "minimal diff" means three things, all of which are separately
assertable:

- `json.loads` into a `dict` (insertion order preserved), mutate only
  `permissions.allow`, re-serialize with `sort_keys=False`.
- Reuse the input file's indentation and trailing-newline convention rather
  than imposing one; detect it from the input, default to `indent=2` plus one
  trailing newline when the file is absent or minified.
- The strongest available assertion is not "keys are equal" but "the unified
  diff between input and output touches only lines inside
  `permissions.allow`". Prefer that formulation in tests — it catches
  reindentation and key reordering that a key-by-key equality check silently
  accepts.

### D7 — Tests must construct the failure cases, and the "before" must be executable

The repository's own `.claude/settings.local.json` has only an `allow` list and
no `deny` key, so the deny-list defect is **latent**. A test asserting against
the real file would pass vacuously and prove nothing. Every defect therefore
gets a fixture that reproduces it in `tmp_path`.

The repo's "gates must fail before work" convention says each test must fail
against the behavior that ships today. Taken literally that is unsatisfiable
here: today's behavior is a bash-and-Python fragment *inside a markdown fence*.
There is nothing to import and nothing to run, so "run the test against the old
code" has no referent, and an instruction with no referent gets quietly
dropped.

The resolution is to make the "before" executable: transcribe `SKILL.md:211-232`
verbatim into `skills/tests/setup-coordinator/legacy_shim.py` as
`legacy_add_permission(settings_path)`, faithful down to the `grep`-equivalent
substring guard and the `json.dumps(..., indent=2)` rewrite. Then every
settings-writer test is parametrized over `{legacy, new}` and asserts
`xfail`-on-legacy / pass-on-new.

This buys three things a one-shot manual check does not: the red phase is real
and reproducible, the four defects are documented as executable claims rather
than prose, and the shim keeps failing forever, so a future refactor that
reintroduces any of them is caught. The shim is test-only — it lives under
`skills/tests/`, is never shipped in the payload, and is never imported by the
entrypoint.

### D8 — The payload linter constrains how the new files may be written

`skills/shared/validate_install_manifest.py` runs over every `portable` skill,
and `setup-coordinator` is portable. Three of its rules bind this change and
are cheaper to design around than to discover at the gate:

- **`.py` files**: a line matching `skills/<skill>/scripts…` *and* containing
  any of `subprocess|command|cmd|runner|hook` is rejected as a "canonical
  skills runtime path". The `configure` next-steps output and any `--help`
  epilog must therefore not print the entrypoint's own repo-relative path on a
  line that also uses those words.
- **`.md` files**: the same path pattern is rejected in an "executable
  context" — inside a fence, at line start, after a verb like run/invoke/use,
  or in a table cell — unless the line uses the `<skill-base-dir>` or
  `<project-root>` placeholder. So `SKILL.md` invokes the entrypoint as
  `<skill-base-dir>/scripts/setup_coordinator.py`, never as
  `skills/setup-coordinator/scripts/setup_coordinator.py`.
- **Markdown links** in `SKILL.md` must resolve to a file inside the installed
  payload. Links out to `agent-coordinator/` or repo docs will fail the gate.

A useful side effect: `<skill-base-dir>/../<skill>` is also the only form the
linter reads as a cross-skill dependency (`_SIBLING_REFERENCE_RE`). A
`sys.path` insert in Python is invisible to it, so the
`cross_skill_dependencies` entries added in task 4.1 are documentation for
humans and `install.sh`, not something the scan will derive on its own — and
over-declaring is not an error, so the entries are safe to add regardless.

### D9 — The `SKILL.md` line budget must fund a tail block that does not exist yet

`skills/tests/_shared/skill_invariants.py` enforces `assert_tail_block_present`
for any skill whose frontmatter does not set `user_invocable: false`.
`setup-coordinator`'s frontmatter does not set it, so the invariant applies: the
file needs `## Common Rationalizations`, `## Red Flags`, and `## Verification`,
in that order, with at least three rows/items each.

Today's 359-line `SKILL.md` has none of them. So task 4.4 — adding
`test_skill_md.py` — is not a free assertion over the rewrite; it introduces a
requirement the file has never met. Roughly 25-30 lines of the 120-150 budget
are pre-committed to the tail block before any narration is written, which
makes the effective budget for transport table + HTTP guidance + troubleshooting
+ invocations about 90-120 lines. Plan the cut against that number, not against
150.

## Risks

| Risk | Mitigation |
|---|---|
| `atomic.py` absent in an installed payload | Inline fallback per the `refresh-architecture` precedent; covered by a spec scenario |
| `pyyaml` absent in a consumer payload | `vendor_health.load_agents_yaml` imports `yaml` lazily inside the function, so import-time load is safe; the entrypoint catches `ImportError` at call time and degrades detection with a reported warning, matching the sibling-unavailable scenario |
| New test dir invisible to CI | `testpaths` registration is its own task with its own verification; the repo has two recorded incidents of exactly this. The verification must collect **without** a path argument — passing the directory explicitly bypasses `testpaths` and proves nothing |
| Flat-module name collision across skills | Entrypoint is named `setup_coordinator.py`, not a generic `config.py`/`models.py` |
| `__init__.py` shadowing in the test dir | Suite omits `__init__.py`, following `skills/tests/worktree/` |
| Detection drifts from `vendor_health` | Detection calls it rather than reimplementing; only the home-dir layer is local |
| Registering the entrypoint in `smoke_entrypoints` silently widens the gate | `skills/tests/install_sh/test_consumer_portability.py` executes every registered entrypoint inside a freshly installed payload with `PYTHONPATH` stripped. That suite is outside wp-integration's `write_allow` but is invalidated by its manifest edit, so wp-integration runs it as an explicit verification step |
| Detection reaches the network | Resolution is owned locally and the path is verified before the call (D1a); a test pins `COORDINATION_API_URL` to an unroutable value |

## Notes on validation coverage

`parallel_zones.py --validate-packages` will be run but makes **no claim** about
this change: `parallel_zones.json` is keyed on code symbols and contains zero
`skills/` entries. It is reported as *not applicable*, not as passing evidence.
