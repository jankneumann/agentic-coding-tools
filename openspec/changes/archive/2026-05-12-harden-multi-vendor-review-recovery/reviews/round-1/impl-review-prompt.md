# IMPL_REVIEW — harden-multi-vendor-review-recovery (Round 1)

You are reviewing the implementation of OpenSpec proposal
`harden-multi-vendor-review-recovery`. Your job is to find correctness,
security, and robustness issues that single-agent self-review may have missed.

## Proposal one-liner

Add a durable on-disk checkpoint of per-vendor review findings BEFORE
synthesis runs, so a synthesizer crash (e.g. the `line_range: "10-20"`
parser bug at `consensus_synthesizer.py:59`) leaves data intact for
manual recovery. The proposal does **not** add automatic recovery — only
durability + observability + path safety.

## Working tree

- cwd: repo root of `agentic-coding-tools` (worktree
  `.git-worktrees/harden-multi-vendor-review-recovery/`)
- branch: `openspec/harden-multi-vendor-review-recovery`
- HEAD: `21acdf3`
- diff range: `44164d9..HEAD` (7 commits, +2165 / -42 across 10 files)

## Files you MUST read before reporting findings

Implementation:
- `skills/parallel-infrastructure/scripts/checkpoint_findings.py` (new, 329 LOC)
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` (modified)
- `skills/autopilot/scripts/convergence_loop.py` (modified — `converge()`
  body around lines 244-296 has the new checkpoint write)

Tests:
- `skills/tests/parallel-infrastructure/test_checkpoint_findings.py`
- `skills/tests/parallel-infrastructure/test_review_dispatcher_migration.py`
- `skills/tests/autopilot/test_convergence_checkpoint.py`
- `skills/tests/autopilot/test_convergence_result_shape.py`
- `skills/tests/autopilot/test_convergence_durability_integration.py`

Proposal context:
- `openspec/changes/harden-multi-vendor-review-recovery/proposal.md`
- `openspec/changes/harden-multi-vendor-review-recovery/design.md`
- `openspec/changes/harden-multi-vendor-review-recovery/specs/skill-workflow/spec.md`
- `openspec/changes/harden-multi-vendor-review-recovery/contracts/`

## Review focus areas

Self-review (IMPL_ITERATE) already caught: ruff F401 unused imports, mypy
strict no-any-return on `read_manifest`, defensive type-narrowing on
`read_vendor_findings`. **Do not re-raise these.** Look for things missed:

1. **Atomic write robustness**: `_atomic_write_json` does
   write→fsync→replace→fsync_parent. Are there platform-specific
   failure modes (macOS APFS vs Linux ext4/xfs) not addressed? What if
   `os.replace` partially succeeds, what if disk is full mid-fsync?

2. **Path safety**: `_validate_path_safety` resolves `artifacts_dir` with
   `strict=False`. If `artifacts_dir` is a symlink whose target is outside
   the repo, can a vendor with a malicious `findings_path` in the manifest
   write outside intended bounds? (Read side checks `relative_to(safe_dir)`,
   but write side?)

3. **Error propagation**: `convergence_loop.py` lines 264-296 wrap the
   checkpoint write in try/except that logs and re-raises. The narrow
   try/except around `synthesize` (lines ~280-296) covers
   `_review_results_to_vendor_results → synthesize → to_dict`. Is the
   except clause too narrow? Too broad? Does it swallow anything it
   shouldn't?

4. **Manifest schema versioning**: `MANIFEST_SCHEMA_VERSION = 1` is a
   constant. If we ship v2, how do existing tools handle it? The
   proposal docs say "readers must refuse unknown versions" but I don't
   see version-rejection code in `read_manifest`.

5. **`_safe_log_error` masking**: catches bare `Exception`. Does this
   mask programmer errors during development? Is there a way to opt out
   for tests? The test `test_safe_log_error_swallows_handler_exception`
   covers handler failure but not, e.g., logger misconfiguration.

6. **`datetime.now(timezone.utc)`**: Python 3.12+ prefers
   `datetime.now(UTC)`. Does the project's lint config enforce one
   style? Check `pyproject.toml` and ruff rules.

7. **Backward-compat shim**: `ReviewOrchestrator.write_manifest` still
   takes `(results, output_path, review_type, target)` but internally
   delegates to `_cf_write_manifest(out_dir=output_path.parent, ...)`.
   Is the `output_path.parent` derivation safe when callers pass a
   bare filename or a path with no parent?

8. **Test gaps**: 66 new tests claimed. Are any obvious scenarios
   missing? (e.g. write to read-only filesystem, disk-full simulation,
   concurrent writers, manifest schema v0 / v2 forward-compat).

## Output format

Return STRICT JSON:

```json
{
  "findings": [
    {
      "id": "F1",
      "type": "security|correctness|robustness|spec_gap|style|test_gap",
      "criticality": "low|medium|high|critical",
      "description": "One paragraph, concrete. Cite file:line.",
      "disposition": "fix|accept|escalate|regenerate",
      "file_path": "path/to/file.py",
      "line_range": "12-34"
    }
  ]
}
```

If you find nothing blocking, return `{"findings": []}`. Do not pad with
low-criticality nits when nothing significant is wrong.
