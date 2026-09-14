# OCR adapter contract

## Command

`ocr_adapter.py` is invoked by the dispatcher as the `ocr-local` agent's
review-mode command. Its stdin (the review packet body, since `ocr-local`
declares `prompt_via_stdin: true` for the generic `CliVendorAdapter` command
shape) is read and discarded: OCR reads the diff itself via `git diff` and
does not consume our pre-built packet.

```
ocr review --format json --audience agent --output <tmpfile>
```

Workspace mode (no `--from`/`--to`) reviews the same staged/unstaged/
untracked diff every other vendor reviews from the packet, since OCR runs in
the same worktree, before any round's fix commit. When the environment
variables `REVIEW_BASE_REF` and `REVIEW_HEAD_REF` are both set, the adapter
adds `--from <REVIEW_BASE_REF> --to <REVIEW_HEAD_REF>` instead (range mode) —
an escape hatch for callers that already resolved explicit refs; nothing in
this change sets these variables yet.

If the `ocr` binary is not on PATH, or no LLM endpoint is configured
(`OCR_LLM_URL`/`OCR_LLM_TOKEN` unset and no `~/.opencodereview/config.json`),
the adapter exits 2 with the reason on stderr so discovery classifies the
vendor as unavailable — the standard Tier-3 skip line, no other change to
dispatch.

## Output rewrite

| OCR comment field | review-findings field | Note |
|---|---|---|
| `path` | `file_path` | verbatim |
| `content` | `description` | verbatim |
| `existing_code` | `existing_code` | verbatim, when present |
| `start_line`, `end_line` | `line_range {start,end}` | omitted when both are 0 |
| `category` | `type` | via coercion sidecar |
| `category` | `axis` | via coercion sidecar (same source key as `type`) |
| `severity` | `criticality` | identity — OCR's four severities (`critical`,
  `high`, `medium`, `low`) are spelled identically to our `criticality` enum,
  so the adapter copies the value directly; no alias needed |
| `suggestion_code` | `resolution` | prefixed `Suggested change:`, when present |
| (none) | `severity` | left absent; filled from `criticality` by the
  existing `severity_from_criticality` coercion map |
| (none) | `disposition` | `fix` |
| (none) | `id` | 1-indexed integer per response (the schema requires `id: integer`) |

The payload carries `review_type` and `target` from CLI arguments the
dispatcher passes (`--change-id`, `--review-type`), and `reviewer_vendor:
ocr`. A `coverage` block is not produced by this package — OCR does not
report per-file coverage in `--format json` output; wp-coverage's default
(`coverage: unreported`, full quorum eligibility) applies.

## Coercion aliases added to `finding-coercion.json`

OCR's eight categories (`bug`, `security`, `performance`, `maintainability`,
`test`, `style`, `documentation`, `other`) become the same string in both
`type` and `axis` before coercion. `bug`, `security`, `performance`, and
`style` (as a `type`) already resolve through the existing table. This
change adds:

| Source key | From | To |
|---|---|---|
| `type_aliases` | `maintainability` | `architecture` |
| `type_aliases` | `test` | `correctness` |
| `type_aliases` | `documentation` | `style` |
| `type_aliases` | `other` | `style` |
| `axis_aliases` | `maintainability` | `architecture` |
| `axis_aliases` | `documentation` | `readability` |
| `axis_aliases` | `test` | `correctness` |
| `axis_aliases` | `other` | `correctness` |

`security` and `performance` are already valid `type` **and** `axis` enum
values verbatim, so neither table needs an entry for them.
