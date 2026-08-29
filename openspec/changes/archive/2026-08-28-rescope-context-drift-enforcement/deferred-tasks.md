# Deferred tasks — rescope-context-drift-enforcement

Both entries below are repository-settings operations. A pull request cannot perform them,
so they are deferred out of `tasks.md` rather than left unchecked. They are the remaining
steps between this change and actual enforcement.

## 7.2 Apply the branch-protection promotion — **XS**

**Requires the repository owner.** Branch protection cannot be changed by a pull request.

Precondition: the gate must be **green on `main`**, which this change landing on a branch
does not establish. `main` carries its own inherited drift; a gate that attributes inherited
drift to `main` exits 2 on `push: main` until that is remediated.

```bash
gh api -X POST \
  /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks/contexts \
  -f 'contexts[]=context-drift-gate'
```

The endpoint is additive — the six existing contexts are preserved.

## 7.3 Verify seven required contexts — **XS**

```bash
gh api /repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks \
  --jq '.contexts'
```

Must list all seven. Verified at implementation time as **six** —
`test`, `test-infra-skills`, `test-skills`, `validate-specs`, `check-docker-imports`,
`secret-scan` — so `context-drift-gate` is not yet required and a red gate does not
mechanically block a merge.

Afterwards, replace the status line in `docs/guides/session-completion.md` with
`**Status: APPLIED <date>.**`. **Do not delete the section** — `specs/fitness-functions/spec.md:115-116`
requires the coverage-ratchet promotion note to sit alongside it.
