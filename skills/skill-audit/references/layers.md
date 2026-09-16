# Layer rules (design D2)

This table is the single source for `scripts/classifier.py` (`prepass()`) and
for the legend printed in every report. A rule name in a ledger's `layers[].rule`
is one of the names in the second column.

| Layer | Rule name | Shape that decides it | Why the model cannot derive it |
|---|---|---|---|
| `contract` | `frontmatter` | The YAML block between the leading `---` fences | Another agent depends on it; cannot be inferred |
| `contract` | `fenced_command` | Any fenced block except prose fences (`markdown`, `md`, `mermaid`, `diff`) | Verbatim commands, schemas, prompts another agent runs or injects |
| `contract` | `contract_table` | A table whose header row names exit codes, schemas, paths, flags, files, options, arguments, fields, env variables, endpoints or commands | Same |
| `contract` | `skill_base_dir` | A paragraph containing a `<skill-base-dir>` invocation | Same |
| `constraint` | `constraint` | A paragraph with a prohibition (`never`, `must not`, `SHALL NOT`, `do not`, `don't`, `cannot`) **and** a reason (`because`, `so that`, `otherwise`, or a parenthetical of 12+ characters) | Operator intent; a strong model given the reason generalises, given only the rule it argues |
| `constraint` | `prohibition_without_reason` | A paragraph with a prohibition and no reason clause | Still operator intent; it is labelled `constraint` and produces a `constraint_without_reason` finding (`add_reason`) |
| `procedure` | `procedure` | An ordered list where at least half of the items begin with an imperative verb from the classifier's verb list | The lever that varies by tier |
| `teaching` | — (model only) | Undecided prose the model labels `teaching` | Generic competence a frontier model already holds |
| `unclassified` | — | Undecided by the pre-pass and the model output was invalid or no backend was configured | Never guessed |

Rule precedence inside one section is top-down: `frontmatter`, then
`fenced_command`, `contract_table`, `skill_base_dir`, then the constraint rules,
then `procedure`. A section with numbered steps *and* a fenced command is
`contract`, because the command is what another agent copies.

## Sections

A section is the frontmatter block, the text before the first heading
(`preamble`), or one heading with its body up to the next heading of any level.
`SKILL.md` and every `.md` file directly under `references/` are parsed; deeper
files are not (the rightsizing convention forbids them).

Section ids are `<file>#<NN>-<heading-slug>`, numbered in document order, so a
finding's `section_id` is stable across runs of the same file.

## Findings the layers produce

| Finding kind | Trigger | Remediation |
|---|---|---|
| `teaching_inferable` | A `teaching` section | `move_to_reference`, or `keep` when the section cites a repo-specific path, command, script, slash command, or decision id (recorded in `evidence.repo_specific_tokens`) |
| `procedure_without_probe` | A `procedure` section with no fenced block, table, or verify/assert/expect/exit-code sentence | `add_probe` |
| `constraint_without_reason` | Rule `prohibition_without_reason` fired | `add_reason` |
| `contract_unpinned` | A `contract` section whose heading or backticked tokens appear in no test under `skills/tests/<skill>/`, `<skill>/tests/`, or `<skill>/scripts/tests/` | `add_probe` |
| `missing_deviation_protocol` | The skill has `procedure` sections but no text mentions deviations | `add_probe` on the first procedure section |
| `tier_concentrated_failure` | One tier holds ≥ 60 % of the skill's failures across ≥ 3 sessions (see `evidence_join.py`) | `add_probe`, with the tier and `count` in evidence |
| `convention_drift` | A rule of the selected `--convention` failed (see `conventions.py`) | Per rule: `move_to_reference` for size and depth, `add_probe` for the tail block, `keep` otherwise |

A `contract` finding can never carry `delete`: `findings.py` raises before
writing and the schema's `if/then` rejects the file.
