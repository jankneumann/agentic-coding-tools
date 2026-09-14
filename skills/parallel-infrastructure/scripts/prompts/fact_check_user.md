### Task

Below is the diff these findings were produced from, and the findings
themselves. Identify only the findings that this diff **proves** wrong.

Every finding carries a `file_path`. The `<file>` in the diff with that same
path is the finding's subject; other files in the diff are context. They can
supply evidence a cross-file finding rests on, but never stand in for the
subject file.

Your default answer is to keep everything. On most reviews that is correct.

### The only two grounds for removal

**Ground A — the finding targets code that is not in its subject file's diff.**

The symbol, statement, or construct the finding describes appears nowhere in
the diff for the file it names. Judged against that file alone.

**Ground B — a specific diff line literally contradicts the finding's central claim.**

The finding asserts a concrete fact and the diff shows the opposite in plain
text — an identifier called "unused" that is used, a check called "missing"
that is present, a value called "hardcoded" that is read from a variable.
The contradiction must be readable straight off the diff, not derived through
a chain of reasoning.

If you cannot point to the specific diff line that establishes Ground A or
Ground B, keep the finding.

### Protected subjects — never remove

Whatever you conclude about correctness, keep a finding whose subject is:

- **Memory safety** — allocation size, buffer length, index bounds, off-by-one,
  use-after-free, null dereference
- **Concurrency** — locks, atomics, data races, synchronization
- **Declaration consistency** — a declaration that disagrees with its
  definition, linkage mismatches
- **Behavioral or compatibility change** — a message, field, status, or
  default the old code produced that the new code no longer does
- **An unused parameter** — a parameter the function accepts and never uses

These are the categories where a wrongly removed finding is most expensive
and your own confidence is least trustworthy. On a protected subject you do
not get to be confident. Keep it.

### Diff

<review_files>
{{diff}}
</review_files>

### Findings

{{findings}}

### Output

Respond with exactly one JSON object, no other text, no markdown fence:

- `{"tool": "approve_all_comments"}` — in every case except the next one,
  including when findings look doubtful, unverifiable, or minor.
- `{"tool": "report_incorrect_comments", "items": [{"finding_id": "...", "ground": "A_absent_from_subject_diff" | "B_contradicted_by_diff_line", "evidence_line": "..."}]}` —
  only for findings meeting Ground A or Ground B, and only if you can name
  the diff line that disproves each one.
