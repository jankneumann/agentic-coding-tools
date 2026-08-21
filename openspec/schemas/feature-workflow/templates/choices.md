# Choices Ledger: {{change_id}}

<!-- GENERATED from choices.json by the audit-choices skill. Do not hand-edit —
     edits made here are discarded the next time the ledger is rendered.
     choices.json is the source of truth; this file is a rendering of it.
     Produced by an independent, read-only auditor pass — never hand-authored
     during planning or implementation. -->

**Generated**: {{generated_at}}
**Audited range**: {{base_sha}}..{{head_sha}}

<!-- Entries are ordered least-confident first (low, then medium, then high);
     within equal confidence, needs-user before unsound before sound. This is
     a rendering invariant enforced by the renderer, not editable here. -->

## Entries

### {{choice}}

**Confidence**: {{confidence}} · **Verdict**: {{verdict}}

<!-- One entry block per ledger entry below. Each entry must stand alone —
     readable without the diff or transcript it was audited from. -->

#### The choice

{{choice}}

#### Scenario

{{scenario}}

#### The gap

{{gap}}

#### The reach

{{reach}}

#### Verdict

{{verdict}} — {{verdict_rationale}}

#### Confidence

{{confidence}}

#### Provenance

- **Commits**: {{commits}}
- **Files**: {{files}}

#### Self-reported

<!-- Present the cross-reference when self_reported is true, otherwise the
     explicit "not self-reported" marker. -->

{{session_log_ref}}
<!-- or, when self_reported is false: -->
Not self-reported — the auditor found this decision without a matching
`Decisions` entry in `session-log.md`.

---

<!-- Repeat the entry block above for each item in choices.json's entries
     array, in the ranked order described above. -->
