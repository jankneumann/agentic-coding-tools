# Plan Review — make-setup-coordinator-script-backed

You are an independent plan reviewer. Review the OpenSpec plan artifacts for
change-id `make-setup-coordinator-script-backed`. This is **round 2**: a
PLAN_ITERATE pass already landed fixes, so review the artifacts as they exist
on disk right now.

## Artifacts to read (read-only — do NOT modify any file)

All paths are relative to the repository root you are running in:

- `openspec/changes/make-setup-coordinator-script-backed/proposal.md`
- `openspec/changes/make-setup-coordinator-script-backed/design.md`
- `openspec/changes/make-setup-coordinator-script-backed/tasks.md`
- `openspec/changes/make-setup-coordinator-script-backed/specs/setup-coordinator/spec.md`
- `openspec/changes/make-setup-coordinator-script-backed/contracts/harness-report.schema.json`
- `openspec/changes/make-setup-coordinator-script-backed/contracts/README.md`
- `openspec/changes/make-setup-coordinator-script-backed/work-packages.yaml`

## What the change does

`skills/setup-coordinator/SKILL.md` is 359 lines of narrated bash with no
`scripts/` dir and no tests. The change extracts the deterministic half into a
tested `scripts/setup_coordinator.py` with four subcommands
(`detect-harnesses`, `check`, `configure`, `report`), fixes four defects in the
permission-allowlist step, adds harness presence detection, and cuts SKILL.md
to 120-150 lines.

## Ground truth you MUST verify against, not assume

The plan makes many claims about existing repository files. **Open those files
and check.** A finding that a claim is wrong is more valuable than a finding
that a claim is missing. Files worth checking:

- `skills/setup-coordinator/SKILL.md` (esp. lines 211-232, the allowlist step,
  and the frontmatter)
- `skills/parallel-infrastructure/scripts/vendor_health.py`
  (`load_agents_yaml`, `check_all_vendors`, `check_vendor`)
- `skills/project-context-runtime/scripts/atomic.py`
  (`atomic_write_bytes`, `atomic_write_json`, `canonical_json_bytes`)
- `skills/project-context-runtime/scripts/__init__.py`
- `skills/refresh-architecture/scripts/arch_utils/provenance.py` (the claimed
  guarded-import precedent)
- `skills/shared/validate_install_manifest.py` (the payload linter rules the
  design says constrain the rewrite)
- `skills/install-manifest.json` (`cross_skill_dependencies`,
  `smoke_entrypoints` — check the actual shape/schema)
- `skills/pyproject.toml` (`testpaths`)
- `skills/tests/_shared/skill_invariants.py` (`assert_tail_block_present`)
- `skills/tests/install_sh/test_consumer_portability.py`
- `skills/validate-feature/scripts/linters/dependency_direction.py` (does it
  accept `--skills-root`?)
- `skills/install.sh` (does it accept `--check`?)
- `agent-coordinator/agents.yaml` (the roster: which agents end in `-local`,
  which have a `cli.command`, what `type` values exist)
- `.claude/settings.local.json` (the live settings file shape)

## Highest-value review targets

1. **Verification-step executability.** `work-packages.yaml` declares
   verification `command:` strings. Do they actually run? Check argparse flags
   exist, paths exist, the interpreter has the needed packages, and that a
   shell one-liner does what its comment claims. A gate that errors for the
   wrong reason, or that passes vacuously, is a defect.
2. **Contract vs spec vs implementation-plan consistency.** Does
   `harness-report.schema.json` admit exactly what the spec requires, and
   nothing the spec forbids? Are there fields the tasks never populate, or
   spec clauses the schema cannot express?
3. **Task/scope decomposition.** `write_allow` overlap between wp-core and
   wp-integration is declared intentional — is the argument sound? Are there
   files a task must edit that no package's `write_allow` covers?
4. **Design claims that are wrong.** The design cites specific file:line
   references. Check them.
5. **Testability.** Every spec scenario should map to something a test can
   assert. Flag scenarios that are untestable as written, and tests described
   in tasks.md that would pass vacuously.

## Output

Emit **only** a single JSON document on stdout, no prose before or after, no
markdown fence, conforming to `openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "make-setup-coordinator-script-backed",
  "reviewer_vendor": "<your vendor/model name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness",
      "severity": "critical",
      "type": "spec_gap",
      "criticality": "high",
      "description": "Critical: <what is wrong, citing file and line>",
      "resolution": "<the specific edit that fixes it>",
      "disposition": "fix",
      "file_path": "openspec/changes/make-setup-coordinator-script-backed/design.md",
      "line_range": {"start": 40, "end": 48}
    }
  ]
}
```

Field rules (the validator rejects violations):

- `axis` — exactly one of `correctness`, `readability`, `architecture`,
  `security`, `performance`. Required.
- `severity` — one of `critical`, `nit`, `optional`, `fyi`, `none`. Required.
  The `description` MUST begin with the matching prefix (`Critical:`, `Nit:`,
  `Optional:`, `FYI:`; `none` findings need no prefix).
- `type` — one of `spec_gap`, `contract_mismatch`, `architecture`, `security`,
  `performance`, `style`, `correctness`, `observability`, `compatibility`,
  `resilience`, `behavioral_failure`. Required.
- `criticality` — `low`, `medium`, `high`, `critical`. Required.
- `disposition` — `fix`, `regenerate`, `accept`, `escalate`. Required, and
  coherent with severity (`critical`/`nit` → `fix`; `optional`/`fyi`/`none` →
  `accept`; anything else → `escalate` with justification in `resolution`).
- `file_path` and `line_range` are optional but strongly preferred — they are
  what lets cross-vendor consensus match your finding to another reviewer's.

Reserve `severity: critical` for things that would produce a wrong or broken
implementation if the plan were followed as written. Include at least one
`severity: none` positive observation. Do not pad with restatements of the
plan's own caveats — the plan already documents its known constraints in
design.md "Risks" and the work-packages comments; a finding that repeats one of
those without adding new information is noise.
